import React from 'react'
import Topbar from './Topbar'
import LeftNav from './LeftNav'
import type { ChatDocumentDragPayload } from '../Chat/chatGroundingDnd'
import './AppShell.css'

interface AppShellProps {
  children: React.ReactNode
  onSettingsOpen?: () => void
  onVoiceOpen?: () => void
  onWorkbenchOpen?: () => void
  onChatDocumentDrop?: (payload: ChatDocumentDragPayload) => void
  workbenchCount?: number
}

export default function AppShell({
  children,
  onSettingsOpen,
  onVoiceOpen,
  onWorkbenchOpen,
  onChatDocumentDrop,
  workbenchCount = 0,
}: AppShellProps) {
  const [navOpen, setNavOpen] = React.useState(true)

  return (
    <div className="app-shell">
      <Topbar
        onMenuToggle={() => setNavOpen(o => !o)}
        onSettingsOpen={onSettingsOpen}
        onVoiceOpen={onVoiceOpen}
        onWorkbenchOpen={onWorkbenchOpen}
        workbenchCount={workbenchCount}
      />
      <div className="app-body">
        <LeftNav collapsed={!navOpen} onChatDocumentDrop={onChatDocumentDrop} />
        <main className="app-main">{children}</main>
      </div>
    </div>
  )
}

