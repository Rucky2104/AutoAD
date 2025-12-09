import React from 'react'
export default function SummaryCards({summary}){
  const domain = summary.domain || {}
  return (
    <div className="panel">
      <h3>Domain Overview</h3>
      <div className="card">
        <div><b>Domain:</b> {domain.name || '—'}</div>
        <div><b>Forest:</b> {domain.forest || '—'}</div>
        <div><b>DC Count:</b> {domain.dc_count || 0}</div>
        <div><b>DNS:</b> {domain.dns || '—'}</div>
      </div>
      <h4>Quick Stats</h4>
      <div className="card">Hosts: {summary.host_count || 0}</div>
      <div className="card">Users: {summary.user_count || 0}</div>
      <div className="card">Creds: {summary.cred_count || 0}</div>
    </div>
  )
}
