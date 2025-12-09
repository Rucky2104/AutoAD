import React from 'react'
import ActivityFeed from '../components/ActivityFeed'
import SummaryCards from '../components/SummaryCards'
import JobsTable from '../components/JobsTable'
import DependencyGraph from '../components/DependencyGraph'
export default function Dashboard({events,jobs,summary,nodes,links,onView}){
  return (
    <div style={{display:'grid',gridTemplateColumns:'1fr',gap:12}}>
      <SummaryCards summary={summary} />
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
        <ActivityFeed events={events} />
        <JobsTable jobs={jobs} onView={onView} />
      </div>
      <div className="panel"><h3>Dependency Graph</h3><DependencyGraph nodes={nodes} links={links} /></div>
    </div>
  )
}
