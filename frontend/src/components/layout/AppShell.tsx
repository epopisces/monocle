import React, { useState } from 'react'
import Topbar from './Topbar'
import LeftNav from './LeftNav'
import './AppShell.css'

interface AppShellProps {
  children: React.ReactNode
  onSettingsOpen?: () => void
}

export default function AppShell({ children, onSettingsOpen }: AppShellProps) {
  const [navOpen, setNavOpen] = useState(true)

  return (
    <div className="app-shell">
        <Topbar onMenuToggle={() => setNavOpen(o => !o)} onSettingsOpen={onSettingsOpen} />
      <div className="app-body">
        <LeftNav collapsed={!navOpen} />
        <main className="app-main">{children}</main>
      </div>
    </div>
  )
}
