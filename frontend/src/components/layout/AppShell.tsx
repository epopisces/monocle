import React from 'react'
import Topbar from './Topbar'
import LeftNav from './LeftNav'
import './AppShell.css'

interface AppShellProps {
  children: React.ReactNode
  onSettingsOpen?: () => void
  onVoiceOpen?: () => void
  onReviewOpen?: () => void
  onFailedOpen?: () => void
  reviewCount?: number
  failedCount?: number
}

export default function AppShell({
  children,
  onSettingsOpen,
  onVoiceOpen,
  onReviewOpen,
  onFailedOpen,
  reviewCount = 0,
  failedCount = 0,
}: AppShellProps) {
  const [navOpen, setNavOpen] = React.useState(true)

  return (
    <div className="app-shell">
      <Topbar
        onMenuToggle={() => setNavOpen(o => !o)}
        onSettingsOpen={onSettingsOpen}
        onVoiceOpen={onVoiceOpen}
        onReviewOpen={onReviewOpen}
        onFailedOpen={onFailedOpen}
        reviewCount={reviewCount}
        failedCount={failedCount}
      />
      <div className="app-body">
        <LeftNav collapsed={!navOpen} />
        <main className="app-main">{children}</main>
      </div>
    </div>
  )
}

