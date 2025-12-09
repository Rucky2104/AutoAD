import React, { useEffect, useState } from 'react'
import { jobOutputs } from '../api'
export default function HostPage({hostIp}){
  const [outputs,setOutputs] = useState([])
  useEffect(()=>{
    async function load(){ if(hostIp){ /* placeholder */ } }
    load()
  },[hostIp])
  return (
    <div className="panel">
      <h3>Host: {hostIp}</h3>
      <div className="card">Host details and attack surface will appear here.</div>
      <h4>Command History</h4>
      <pre>{outputs.map(o=>`[${o.source}] ${o.line}`).join('\n')}</pre>
    </div>
  )
}
