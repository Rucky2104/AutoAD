import axios from 'axios'
const api = axios.create({ baseURL: '/api' })
export async function listJobs(){ const r = await api.get('/jobs'); return r.data }
export async function startNmap(name,target){ const r = await api.post('/start_nmap',{name,target}); return r.data }
export async function jobOutputs(job_id){ const r = await api.get(`/jobs/${job_id}/outputs`); return r.data }
export async function sessions(){ const r = await api.get('/sessions'); return r.data }
export async function enableAutoExploit(enable){ const r = await api.post('/auto_exploit',{enable}); return r.data }
export default api
