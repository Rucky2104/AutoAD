import React from 'react'
export default function JobsTable({jobs, onView}){
  return (
    <div className="panel">
      <h3>Jobs</h3>
      <table className="table">
        <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Meta</th><th>Action</th></tr></thead>
        <tbody>
          {jobs.map(j=> (
            <tr key={j.id}>
              <td>{j.id}</td>
              <td>{j.name}</td>
              <td>{j.status}</td>
              <td style={{maxWidth:200,overflow:'hidden',textOverflow:'ellipsis'}}>{JSON.stringify(j.meta || {})}</td>
              <td><button onClick={()=>onView(j.id)}>View</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
