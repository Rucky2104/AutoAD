import React from 'react'
export default function Modal({children, open, onClose}){
  if(!open) return null
  return (
    <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.5)',display:'flex',alignItems:'center',justifyContent:'center'}} onClick={onClose}>
      <div style={{width:800,background:'#071126',padding:20,borderRadius:8}} onClick={e=>e.stopPropagation()}>{children}</div>
    </div>
  )
}
