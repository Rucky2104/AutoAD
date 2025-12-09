import React, { useRef, useEffect } from 'react'
import * as d3 from 'd3'
export default function DependencyGraph({nodes, links}){
  const ref = useRef()
  useEffect(()=>{
    const svg = d3.select(ref.current)
    svg.selectAll('*').remove()
    const width = ref.current.clientWidth || 800, height = 320
    const g = svg.append('g')
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d=>d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width/2, height/2))
    const link = g.selectAll('.link').data(links).enter().append('line').attr('stroke','#333')
    const node = g.selectAll('.node').data(nodes).enter().append('g')
    node.append('circle').attr('r',12).attr('fill','#1e40af')
    node.append('text').attr('x',16).attr('y',4).text(d=>d.name)
    simulation.on('tick', ()=>{ link.attr('x1', d=>d.source.x).attr('y1', d=>d.source.y).attr('x2', d=>d.target.x).attr('y2', d=>d.target.y); node.attr('transform', d=>`translate(${d.x},${d.y})`) })
    return ()=> simulation.stop()
  },[nodes,links])
  return (<svg ref={ref} width='100%' height='320'></svg>)
}
