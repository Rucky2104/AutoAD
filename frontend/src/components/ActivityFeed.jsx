import React from 'react'
export default function ActivityFeed({events}){
  return (
    <div className="panel">
      <div className="header"><h3>Activity Feed</h3></div>
      <div className="feed">
        {events.length===0 && <div className="card">No events yet</div>}
        {events.slice().reverse().map((e,idx)=> (
          <div className="card" key={idx}>
            <div style={{fontSize:12,color:'#9aa4b2'}}>{new Date(e.timestamp*1000).toLocaleString()}</div>
            <div><b>[{e.source}]</b> {e.line}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
