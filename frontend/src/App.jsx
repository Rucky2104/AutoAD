import React, { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Host from './pages/Host'
import socket from './socket'
import { listJobs, sessions } from './api'
import { Routes, Route, useNavigate } from 'react-router-dom'

export default function App(){
  const [events,setEvents] = useState([])
  const [jobs,setJobs] = useState([])
  const [summary,setSummary] = useState({})
  const [nodes,setNodes] = useState([])
  const [links,setLinks] = useState([])
  const navigate = useNavigate()

  useEffect(()=>{ async function load(){ const j = await listJobs(); setJobs(j.jobs || []) } ; load()
    const evHandler = (ev)=>{ setEvents(prev=>[...prev,ev]); if(ev.source==='system' && ev.line.includes('Domain')){ setSummary(s=>({...s,domain:{...s.domain,name: ev.line.split(':').pop().trim()}})) } }
    socket.on('job_event', evHandler)
    return ()=> socket.off('job_event', evHandler)
  },[])

  useEffect(()=>{ setNodes(jobs.map(j=>({id:j.id, name:j.name}))); setLinks([]) },[jobs])

  const handleStart = (job_id)=>{ if(job_id){} else{} }
  const handleView = (jobId)=>{ navigate(`/host/${jobId}`) }

  return (
    <div className="app">
      <Sidebar onStart={handleStart} />
      <Routes>
        <Route path='/' element={<Dashboard events={events} jobs={jobs} summary={summary} nodes={nodes} links={links} onView={handleView} />} />
        <Route path='/host/:ip' element={<Host/>} />
      </Routes>
      <div style={{padding:8}} className='panel'>
        <h3>Sessions</h3>
        <pre>{JSON.stringify([], null, 2)}</pre>
      </div>
    </div>
  )
}
