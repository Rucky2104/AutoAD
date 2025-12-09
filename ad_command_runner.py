#!/usr/bin/env python3
"""
AD Command Runner & Output Tracker
----------------------------------

This module implements a robust, resumable command runner suitable for
orchestrating local pentest tools (nmap, enum4linux, impacket scripts, etc.)
while keeping a persistent record of what ran, outputs, and statuses.

Features:
- Async command execution with live stdout/stderr streaming
- Line-buffered capturing and storage to per-job log files and a SQLite DB
- Job metadata persisted to SQLite so runs can be resumed or re-run later
- Simple plugin hook to run parsers on completed outputs (e.g. nmap xml -> hosts)
- Python API + simple CLI example

Note: this code aims to be a secure, maintainable starting point. It does not
perform network scans itself until you call it with specific commands.

Dependencies: only Python stdlib (3.8+ recommended).
"""

import asyncio
import sqlite3
import json
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
import xml.etree.ElementTree as ET

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL,
    updated_at REAL,
    name TEXT,
    command TEXT,
    cwd TEXT,
    env TEXT,
    status TEXT,
    exit_code INTEGER,
    meta TEXT
);

CREATE TABLE IF NOT EXISTS outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    created_at REAL,
    source TEXT,
    line TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);
"""


class JobStore:
    """Simple SQLite-backed job store. Safe to call from asyncio via run_in_executor.

    Stores jobs and line-by-line outputs. Keeps job metadata in JSON in the `meta` field.
    """

    def __init__(self, path: str = "./ad_runner.db"):
        self.path = Path(path)
        self._ensure_dir()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _ensure_dir(self):
        parent = self.path.parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)

    def _init_db(self):
        cur = self._conn.cursor()
        cur.executescript(DB_SCHEMA)
        self._conn.commit()

    def create_job(self, name: str, command: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None, meta: Optional[Dict[str, Any]] = None) -> int:
        now = time.time()
        cmd_text = json.dumps(command)
        env_text = json.dumps(env or {})
        meta_text = json.dumps(meta or {})
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO jobs (created_at, updated_at, name, command, cwd, env, status, exit_code, meta) VALUES (?,?,?,?,?,?,?,?,?)",
            (now, now, name, cmd_text, cwd or '', env_text, 'pending', None, meta_text),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_job_status(self, job_id: int, status: str, exit_code: Optional[int] = None, meta: Optional[Dict[str, Any]] = None):
        now = time.time()
        cur = self._conn.cursor()
        if meta is not None:
            cur.execute("UPDATE jobs SET status=?, exit_code=?, updated_at=?, meta=? WHERE id=?", (status, exit_code, now, json.dumps(meta), job_id))
        else:
            cur.execute("UPDATE jobs SET status=?, exit_code=?, updated_at=? WHERE id=?", (status, exit_code, now, job_id))
        self._conn.commit()

    def append_output(self, job_id: int, source: str, line: str):
        now = time.time()
        cur = self._conn.cursor()
        cur.execute("INSERT INTO outputs (job_id, created_at, source, line) VALUES (?,?,?,?)", (job_id, now, source, line))
        self._conn.commit()

    def get_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    def list_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def fetch_outputs(self, job_id: int, since: Optional[float] = None) -> List[Dict[str, Any]]:
        cur = self._conn.cursor()
        if since:
            cur.execute("SELECT * FROM outputs WHERE job_id=? AND created_at>? ORDER BY id ASC", (job_id, since))
        else:
            cur.execute("SELECT * FROM outputs WHERE job_id=? ORDER BY id ASC", (job_id,))
        return [dict(r) for r in cur.fetchall()]


class CommandRunner:
    """Runs commands asynchronously, streams output to listeners and the JobStore.

    Usage:
        store = JobStore()
        runner = CommandRunner(store)
        job_id = store.create_job('nmap-scan', ['nmap','-oX','-','-p','1-1024','10.10.0.0/24'])
        await runner.run_job(job_id)

    The runner writes each line with a source tag ('stdout' or 'stderr') to the outputs table.
    """

    def __init__(self, store: JobStore, logs_dir: str = './logs'):
        self.store = store
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._listeners: Dict[int, List[Callable[[Dict[str, Any]], None]]] = {}

    def add_listener(self, job_id: int, callback: Callable[[Dict[str, Any]], None]):
        """Callback gets a dict: {job_id, source, line, timestamp}
        Useful for streaming to websockets or printing to console.
        """
        self._listeners.setdefault(job_id, []).append(callback)

    def _notify(self, job_id: int, source: str, line: str):
        event = {'job_id': job_id, 'source': source, 'line': line, 'timestamp': time.time()}
        for cb in self._listeners.get(job_id, []):
            try:
                cb(event)
            except Exception:
                pass

    async def _read_stream(self, stream: asyncio.StreamReader, job_id: int, source: str, logfile):
        """Read stream line by line, store in db and optionally logfile."""
        while True:
            line = await stream.readline()
            if not line:
                break
            try:
                text = line.decode('utf-8', errors='replace').rstrip('\n')
            except Exception:
                text = repr(line)
            # persist
            self.store.append_output(job_id, source, text)
            if logfile:
                logfile.write(f"[{source}] {text}\n")
                logfile.flush()
            self._notify(job_id, source, text)

    async def run_job(self, job_id: int, timeout: Optional[int] = None) -> int:
        job = self.store.get_job(job_id)
        if not job:
            raise ValueError('no such job')

        cmd_list = json.loads(job['command'])
        cwd = job['cwd'] or None
        env = json.loads(job['env'] or '{}') or None

        # Open per-job logfile
        logfile_path = self.logs_dir / f"job_{job_id}.log"
        logfile = open(logfile_path, 'a', encoding='utf-8')

        # mark running
        self.store.update_job_status(job_id, 'running')

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        except FileNotFoundError as e:
            self.store.append_output(job_id, 'system', f'ERROR: command not found: {cmd_list[0]}')
            self.store.update_job_status(job_id, 'failed', exit_code=-1)
            logfile.close()
            return -1

        # read stdout/stderr concurrently
        readers = [
            self._read_stream(proc.stdout, job_id, 'stdout', logfile),
            self._read_stream(proc.stderr, job_id, 'stderr', logfile),
        ]

        # wait with timeout support
        try:
            await asyncio.wait_for(asyncio.gather(*readers), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            self.store.append_output(job_id, 'system', f'ERROR: timeout after {timeout}s, killed process')
            self.store.update_job_status(job_id, 'timeout', exit_code=None)
            logfile.close()
            return -1

        exit_code = await proc.wait()
        self.store.update_job_status(job_id, 'finished' if exit_code == 0 else 'failed', exit_code=exit_code)
        logfile.close()
        return exit_code


# --- Example parser for Nmap XML output (if you run nmap with -oX - to stdout) ---
def parse_nmap_xml_from_job_outputs(outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collect stdout lines, join into an XML string and parse basic host info.

    Returns a list of hosts with ip and open ports.
    """
    stdout_lines = [o['line'] for o in outputs if o['source'] == 'stdout']
    text = '\n'.join(stdout_lines).strip()
    if not text:
        return []
    try:
        root = ET.fromstring(text.encode('utf-8'))
    except ET.ParseError:
        # Not valid XML: return empty
        return []

    ns = ''
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
                ports.append({'port': int(portnum), 'state': state, 'service': service})
        hosts.append({'ip': ip, 'ports': ports})
    return hosts


# --- Simple CLI demonstration ---
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='AD Command Runner demo')
    parser.add_argument('--db', default='./ad_runner.db', help='path to sqlite db')
    parser.add_argument('--logs', default='./logs', help='path to logs dir')
    parser.add_argument('--name', help='job name')
    parser.add_argument('--cmd', help='command to run (quoted)')
    parser.add_argument('--shell', action='store_true', help='pass command string to shell')
    args = parser.parse_args()

    if not args.cmd:
        print('Example usage:')
        print("  ./ad_command_runner.py --name nmap1 --cmd \"nmap -oX - -p 88,389,445 10.10.0.0/24\"")
        sys.exit(1)

    # Prepare
    store = JobStore(args.db)
    runner = CommandRunner(store, logs_dir=args.logs)

    if args.shell:
        # WARNING: using shell=True may be dangerous; better to pass a list
        cmd_list = ["/bin/sh", "-c", args.cmd]
    else:
        cmd_list = shlex.split(args.cmd)

    job_id = store.create_job(args.name or 'job', cmd_list, cwd=os.getcwd(), env=dict(os.environ), meta={'cli': True})

    # add a simple listener that prints to terminal in realtime
    def print_listener(evt):
        ts = time.strftime('%H:%M:%S', time.localtime(evt['timestamp']))
        print(f"[{ts}] ({evt['source']}) {evt['line']}")

    runner.add_listener(job_id, print_listener)

    async def main():
        code = await runner.run_job(job_id, timeout=None)
        print('\nJob finished with exit code', code)
        outputs = store.fetch_outputs(job_id)
        # try parsing nmap if output looks like XML
        hosts = parse_nmap_xml_from_job_outputs(outputs)
        if hosts:
            print('\nParsed hosts:')
            for h in hosts:
                print(h)

    asyncio.run(main())
