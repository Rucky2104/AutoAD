import os
import tempfile
import pytest
from ad_command_runner import JobStore




def test_create_and_list_job(tmp_path):
  db = tmp_path / "test.db"
  store = JobStore(str(db))
  job_id = store.create_job('test', ['echo', 'hi'])
  assert job_id > 0
  jobs = store.list_jobs()
  assert any(j['id'] == job_id for j in jobs)




def test_append_and_fetch_outputs(tmp_path):
  db = tmp_path / "test2.db"
  store = JobStore(str(db))
  job_id = store.create_job('test', ['echo', 'hi'])
  store.append_output(job_id, 'stdout', 'line1')
  outs = store.fetch_outputs(job_id)
  assert len(outs) == 1
  assert outs[0]['line'] == 'line1'
