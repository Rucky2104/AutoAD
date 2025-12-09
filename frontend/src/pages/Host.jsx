import React from 'react'
import HostPage from '../components/HostPage'
import { useParams } from 'react-router-dom'
export default function Host(){ const { ip } = useParams(); return (<HostPage hostIp={ip} />) }
