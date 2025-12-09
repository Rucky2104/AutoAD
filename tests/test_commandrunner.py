import asyncio
import os
import tempfile
import pytest
from ad_command_runner import JobStore, CommandRunner


@pytest.mark.asyncio
async def test_run_echo(tmp_path):
  db = tmp_path / "cr.db"
  store = JobStore(str(db))
  runner = CommandRunner(store, logs_dir=str(tmp_path / 'logs'))
  job_id = store.create_job('echo', ['echo', 'hello'])


  events = []
  def listener(e):
    events.append(e)


  runner.add_listener(job_id, listener)
  code = await runner.run_job(job_id)
  assert code == 0
  outs = store.fetch_outputs(job_id)
  assert any('hello' in o['line'] for o in outs)


@pytest.mark.asyncio
async def test_missing_command(tmp_path):
  db = tmp_path / "cr2.db"
  store = JobStore(str(db))
  runner = CommandRunner(store, logs_dir=str(tmp_path / 'logs'))
  job_id = store.create_job('bad', ['nonexistent-command-xyz'])
  code = await runner.run_job(job_id)
  assert code == -1
  outs = store.fetch_outputs(job_id)
  assert any('ERROR: command not found' in o['line'] for o in outs)
