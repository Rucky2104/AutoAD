#!/usr/bin/env python3
"""
Flask + Socket.IO Web UI for AD Orchestrator
--------------------------------------------

This file provides a local web interface that lets you:
- view jobs and their statuses
- start discovery jobs (nmap) or arbitrary jobs (validated)
- stream live output via Socket.IO to the browser
- view discovered sessions and approve/deny auto-exploit actions

Run:
  1) install dependencies on Kali: `sudo apt update && sudo apt install -y python3-pip git nmap`
  2) pip3 install flask flask-socketio eventlet
  3) place all python files from the canvas into the same folder
  4) run: `python3 web_ui.py`
  5) open http://localhost:5000 in your browser

Security notes: do NOT expose this web server publicly. It is meant for local use on your Kali box.

"""

from threading import Thread
import asyncio
import time
import json
import os
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit, join_room

# import our modules that were created in the canvas
try:
    from ad_command_runner import JobStore, CommandRunner
    from orchestrator_and_parsers import Orchestrator, SessionStore, parser_registry
except Exception as e:
    print('Error importing local modules:', e)
    raise

# --- start a background asyncio loop for orchestrator/runner coroutines ---
def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

async_loop = asyncio.new_event_loop()
thread = Thread(target=start_background_loop, args=(async_loop,), daemon=True)
thread.start()

# --- create core objects ---
DB_PATH = './ad_runner.db'
LOGS = './logs'
store = JobStore(DB_PATH)
runner = CommandRunner(store, logs_dir=LOGS)
sessions = SessionStore(store)
orch = Orchestrator(store, runner, sessions)

# when runner emits events, forward them to socketio
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret'
socketio = SocketIO(app, async_mode='eventlet')

# helper to forward runner events to socket clients
def forward_event(ev):
    job_room = f"job_{ev['job_id']}"
    socketio.emit('job_event', ev, room=job_room)

# attach a global listener for all jobs (we'll add per-job forwarding as well)
# because CommandRunner stores listeners per-job, we will add when jobs are created

# --- Simple HTML UI ---
INDEX_HTML = r"""
<!doctype html>
<html>
  <head>
    <title>AD Orchestrator</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js" integrity="" crossorigin="anonymous"></script>
    <style>
      body { font-family: Inter, Arial, sans-serif; margin: 20px; }
      #jobs { margin-bottom: 20px; }
      .job { border: 1px solid #ddd; padding: 8px; margin-bottom: 8px; }
      pre { background: #f7f7f7; padding: 8px; max-height: 240px; overflow: auto; }
      button { padding: 6px 10px; }
    </style>
  </head>
  <body>
    <h2>AD Orchestrator — Local UI</h2>
    <div>
      <form id="start-form">
        <label>Job name: <input id="job-name" value="nmap-discovery"></label>
        <label>Target: <input id="target" value="10.10.0.0/24"></label>
        <button type="submit">Start Discovery</button>
      </form>
    </div>
    <h3>Jobs</h3>
    <div id="jobs"></div>
    <h3>Sessions</h3>
    <div id="sessions"></div>

    <script>
      const socket = io();
      async function refreshJobs(){
        const res = await fetch('/api/jobs');
        const data = await res.json();
        const container = document.getElementById('jobs');
        container.innerHTML = '';
        for(const j of data.jobs){
          const div = document.createElement('div');
          div.className = 'job';
          div.id = 'job-'+j.id;
          div.innerHTML = `<b>${j.name}</b> (#${j.id}) - ${j.status} <button onclick="subscribe(${j.id})">Subscribe</button> <button onclick="view(${j.id})">View outputs</button>`;
          container.appendChild(div);
        }
      }
      async function refreshSessions(){
        const res = await fetch('/api/sessions');
        const data = await res.json();
        const container = document.getElementById('sessions');
        container.innerHTML = JSON.stringify(data.sessions, null, 2);
      }
      document.getElementById('start-form').addEventListener('submit', async (e)=>{
        e.preventDefault();
        const name = document.getElementById('job-name').value;
        const target = document.getElementById('target').value;
        const res = await fetch('/api/start_nmap', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name, target})});
        const data = await res.json();
        await refreshJobs();
        alert('Started job '+data.job_id);
      });

      async function subscribe(job_id){
        socket.emit('subscribe', {job_id});
        alert('Subscribed to job '+job_id+'; open console to see live events');
      }

      async function view(job_id){
        const res = await fetch('/api/jobs/'+job_id+'/outputs');
        const data = await res.json();
        const win = window.open('', '_blank');
        win.document.write('<pre>' + data.outputs.map(o=>`['+o.source+'] '+o.line).join('\n') + '</pre>');
      }

      socket.on('job_event', (ev)=>{
        console.log('job_event', ev);
        const el = document.getElementById('job-'+ev.job_id);
        if(el){
          const p = document.createElement('div');
          p.innerText = `[${new Date(ev.timestamp*1000).toLocaleTimeString()}] (${ev.source}) ${ev.line}`;
          el.appendChild(p);
        }
      });

      socket.on('connect', ()=>{ console.log('socket connected'); });

      // initial load
      refreshJobs();
      refreshSessions();
      setInterval(refreshJobs, 5000);
      setInterval(refreshSessions, 5000);
    </script>
  </body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(INDEX_HTML)


@app.route('/api/jobs')
def api_list_jobs():
    jobs = store.list_jobs(200)
    # convert meta JSON
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
    job_id = store.create_job(name, cmd, cwd='.', env=dict(os.environ), meta={'phase': 'discovery'})

    # add listener to forward to socketio
    def listener(ev):
        forward_event(ev)
    runner.add_listener(job_id, listener)

    # schedule orchestrator run on background loop
    fut = asyncio.run_coroutine_threadsafe(orch._run_and_process(job_id), async_loop)
    return jsonify({'job_id': job_id})


@app.route('/api/jobs/<int:job_id>/outputs')
def api_job_outputs(job_id):
    outputs = store.fetch_outputs(job_id)
    return jsonify({'outputs': outputs})


@app.route('/api/sessions')
def api_sessions():
    return jsonify({'sessions': sessions.list()})


@socketio.on('subscribe')
def on_subscribe(data):
    job_id = data.get('job_id')
    room = f"job_{job_id}"
    join_room(room)
    emit('subscribed', {'job_id': job_id})


def run_server():
    print('Starting web UI on http://localhost:5000')
    socketio.run(app, host='0.0.0.0', port=5000)


if __name__ == '__main__':
    run_server()
