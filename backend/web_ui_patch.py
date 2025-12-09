#!/usr/bin/env python3
# Patched web_ui to support React frontend (CORS, auto_exploit endpoint, static serve)
from flask import Flask, render_template_string, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
import asyncio, os, json
from pathlib import Path

# Import your existing modules
try:
    from ad_command_runner import JobStore, CommandRunner
    from orchestrator_and_parsers import Orchestrator, SessionStore, parser_registry
except Exception as e:
    print('Warning: local modules import failed:', e)

app = Flask(__name__, static_folder=None)
CORS(app, origins=['http://localhost:3000','http://127.0.0.1:3000','http://localhost:5173'])
socketio = SocketIO(app, cors_allowed_origins='*')

# minimal in-memory placeholders if modules not imported
store = JobStore('./ad_runner.db') if 'JobStore' in globals() else None
runner = CommandRunner(store, logs_dir='./logs') if 'CommandRunner' in globals() else None
sessions = SessionStore(store) if 'SessionStore' in globals() else None
orch = Orchestrator(store, runner, sessions) if 'Orchestrator' in globals() else None

def forward_event(ev):
    job_room = f"job_{ev['job_id']}"
    socketio.emit('job_event', ev, room=job_room)
    socketio.emit('job_event', ev)

@app.route('/api/jobs')
def api_list_jobs():
    jobs = store.list_jobs(200)
    for j in jobs:
        try:
            j['meta'] = json.loads(j.get('meta') or '{}')
        except Exception:
            j['meta'] = {}
    return jsonify({'jobs': jobs})

@app.route('/api/start_nmap', methods=['POST'])
def api_start_nmap():
    data = request.get_json() or {}
    name = data.get('name') or 'nmap-discovery'
    target = data.get('target') or '10.10.0.0/24'
    cmd = ['nmap', '-oX', '-', '-p', '88,389,445,636,3268', target]
    job_id = store.create_job(name, cmd, cwd='.', env=dict(os.environ), meta={'phase':'discovery'})
    # add listener
    def listener(ev):
        forward_event(ev)
    runner.add_listener(job_id, listener)
    # schedule orchestrator.run
    if orch:
        asyncio.run_coroutine_threadsafe(orch._run_and_process(job_id), asyncio.get_event_loop())
    return jsonify({'job_id': job_id})

@app.route('/api/jobs/<int:job_id>/outputs')
def api_job_outputs(job_id):
    outputs = store.fetch_outputs(job_id)
    return jsonify({'outputs': outputs})

@app.route('/api/sessions')
def api_sessions():
    return jsonify({'sessions': sessions.list() if sessions else []})

@app.route('/api/auto_exploit', methods=['POST'])
def api_auto_exploit():
    data = request.get_json() or {}
    enable = bool(data.get('enable'))
    if orch:
        orch.set_auto_exploit(enable)
    return jsonify({'ok': True, 'auto_exploit': orch.auto_exploit.allow if orch else enable})

# Serve frontend build if present
FRONTEND_DIST = Path(__file__).parent.parent / 'frontend' / 'dist'
if FRONTEND_DIST.exists():
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_frontend(path):
        if path != '' and (FRONTEND_DIST / path).exists():
            return send_from_directory(str(FRONTEND_DIST), path)
        else:
            return send_from_directory(str(FRONTEND_DIST), 'index.html')

if __name__ == '__main__':
    print('Starting patched web_ui on http://localhost:5000')
    socketio.run(app, host='0.0.0.0', port=5000)
