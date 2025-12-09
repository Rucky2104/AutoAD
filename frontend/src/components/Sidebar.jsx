import React, { useEffect, useState } from 'react'
import { startNmap, enableAutoExploit } from '../api'

export default function Sidebar({ onStart }){
  const [interfaces] = useState(['eth0','wlan0','tun0'])
  const [iface,setIface] = useState('eth0')
  const [target,setTarget] = useState('10.10.0.0/24')
  const [autoExploit,setAutoExploit] = useState(false)

  const start = async ()=>{
    const resp = await startNmap('nmap-discovery', target)
    onStart(resp.job_id)
  }
  const toggleExploit = async ()=>{
    const newv = !autoExploit
    setAutoExploit(newv)
    await enableAutoExploit(newv)
  }
  return (
    <div className="sidebar panel">
      <h3>Controls</h3>
      <div style={{marginBottom:10}}>
        <label>Interface<br/>
          <select value={iface} onChange={e=>setIface(e.target.value)}>
            {interfaces.map(i=> <option key={i} value={i}>{i}</option>)}
          </select>
        </label>
      </div>
      <div style={{marginBottom:10}}>
        <label>Target<br/>
          <input value={target} onChange={e=>setTarget(e.target.value)} />
        </label>
      </div>
      <div style={{display:'flex', gap:8}}>
        <button onClick={start}>Start Discovery</button>
        <button onClick={()=>onStart(null)}>Full Scan</button>
      </div>
      <hr style={{margin:'12px 0'}} />
      <div>
        <label>Auto-Exploit<br/></label>
        <button onClick={toggleExploit}>{autoExploit? 'Disable' : 'Enable'}</button>
      </div>
    </div>
  )
}
