import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom'
import { ThemeContext, useThemeProvider } from './hooks/useTheme'
import AppShell from './components/layout/AppShell'
import SettingsModal from './components/SettingsModal'
import ChatScreen from './components/Chat/ChatScreen'
import DocumentBrowserScreen from './components/DocumentBrowser/DocumentBrowserScreen'
import IngestReviewScreen from './components/IngestReview/IngestReviewScreen'
import SearchScreen from './components/Search/SearchScreen'
import GraphScreen from './components/Graph/GraphScreen'
import StatsScreen from './components/Stats/StatsScreen'
import VoiceModal from './components/VoiceModal/VoiceModal'
import ReviewQueue from './components/ReviewQueue/ReviewQueue'
import FailedCaptures from './components/FailedCaptures/FailedCaptures'
import CommandPalette, { type PaletteAction } from './components/CommandPalette/CommandPalette'
import { useHotkeys } from './hooks/useHotkeys'
import { getReviewCount } from './api/review'
import { countIngestNotifications, listIngestFailures } from './api/ingest'
import { getSettings } from './api/settings'
import { triggerWeeklySummary, triggerReindex } from './api/agents'
import { getNote } from './api/notes'
import ChatSessionPickerDialog from './components/Chat/ChatSessionPickerDialog'
import { addGroundingToSession, loadSessions, normalizeGroundingDraft, type GroundingDraft } from './components/Chat/sessionStore'
import type { ChatDocumentDragPayload } from './components/Chat/chatGroundingDnd'

// ── Inner component — must be inside BrowserRouter to use useNavigate ─────────

function AppContent() {
  const navigate = useNavigate()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [voiceOpen, setVoiceOpen] = useState(false)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [failedOpen, setFailedOpen] = useState(false)
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [ingestCount, setIngestCount] = useState(0)
  const [reviewCount, setReviewCount] = useState(0)
  const [failedCount, setFailedCount] = useState(0)
  const [voiceBackend, setVoiceBackend] = useState<'whisper' | 'web_speech'>('whisper')
  const [droppedDraft, setDroppedDraft] = useState<GroundingDraft | null>(null)

  // Fetch server settings once on mount
  useEffect(() => {
    getSettings()
      .then(s => setVoiceBackend(s.ui.voice_input_backend))
      .catch(() => { /* non-fatal: keep default 'whisper' */ })
  }, [])

  const refreshReviewCount = useCallback(async () => {
    try {
      const r = await getReviewCount()
      setReviewCount(r.count)
    } catch { /* non-fatal */ }
  }, [])

  const refreshIngestCount = useCallback(async () => {
    try {
      const r = await countIngestNotifications({ status: 'unread', kind: 'ingest_ready' })
      setIngestCount(r.count)
    } catch { /* non-fatal */ }
  }, [])

  const refreshFailedCount = useCallback(async () => {
    try {
      const items = await listIngestFailures()
      setFailedCount(items.length)
    } catch { /* non-fatal */ }
  }, [])

  // Poll both counts on mount and every 30 s
  useEffect(() => {
    refreshIngestCount()
    refreshReviewCount()
    refreshFailedCount()
    const id = setInterval(() => {
      refreshIngestCount()
      refreshReviewCount()
      refreshFailedCount()
    }, 30_000)
    return () => clearInterval(id)
  }, [refreshIngestCount, refreshReviewCount, refreshFailedCount])

  const handleVoiceSaved = useCallback(() => {
    refreshIngestCount()
    refreshReviewCount()
  }, [refreshIngestCount, refreshReviewCount])

  const closeAllModals = useCallback(() => {
    setSettingsOpen(false)
    setVoiceOpen(false)
    setReviewOpen(false)
    setFailedOpen(false)
    setCommandPaletteOpen(false)
    setDroppedDraft(null)
  }, [])

  const openChatSession = useCallback((sessionId: string) => {
    navigate(`/?session=${encodeURIComponent(sessionId)}`)
  }, [navigate])

  const handleChatDocumentDrop = useCallback(async (payload: ChatDocumentDragPayload) => {
    try {
      const note = await getNote(payload.filePath)
      const draft = normalizeGroundingDraft({
        scope: 'document',
        sourcePath: note.file_path,
        sourceTitle: note.title,
        text: `${note.title}\n\n${note.body}`,
      })
      setDroppedDraft(draft)
    } catch (error) {
      console.error('[App] Failed to load dropped note for chat context:', error)
    }
  }, [])

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  useHotkeys({
    onSearch: () => navigate('/search'),
    onKeywordSearch: () => navigate('/search'),
    onNewNote: () => navigate('/docs'),
    onCommandPalette: () => setCommandPaletteOpen(o => !o),
    onOpenSettings: () => setSettingsOpen(true),
    onToggleSidebar: () => { /* sidebar toggle not yet implemented */ },
    onCloseModal: closeAllModals,
  })

  // ── Command palette extra actions ──────────────────────────────────────────
  const extraActions: PaletteAction[] = [
    {
      id: 'open-settings',
      label: 'Open Settings',
      icon: '⚙️',
      keywords: ['settings', 'config', 'preferences', 'mcp', 'key', 'model'],
      onExecute: () => { setSettingsOpen(true); setCommandPaletteOpen(false) },
    },
    {
      id: 'open-voice',
      label: 'Open Voice Capture',
      icon: '🎤',
      keywords: ['voice', 'capture', 'microphone', 'record', 'audio'],
      onExecute: () => { setVoiceOpen(true); setCommandPaletteOpen(false) },
    },
    {
      id: 'open-ingest-inbox',
      label: 'Open Prepared Ingest Sessions',
      icon: '📥',
      keywords: ['ingest', 'prepared', 'dormant', 'session', 'inbox'],
      onExecute: () => { navigate('/ingest-review'); setCommandPaletteOpen(false) },
    },
    {
      id: 'open-review',
      label: 'Open Review Queue',
      icon: '📋',
      keywords: ['review', 'queue', 'pending', 'approve'],
      onExecute: () => { setReviewOpen(true); setCommandPaletteOpen(false) },
    },
    {
      id: 'run-weekly-summary',
      label: 'Run Weekly Summary',
      icon: '📅',
      keywords: ['weekly', 'summary', 'agent', 'report'],
      onExecute: () => {
        setCommandPaletteOpen(false)
        triggerWeeklySummary().catch(() => { /* non-fatal */ })
      },
    },
    {
      id: 'trigger-reindex',
      label: 'Trigger Reindex',
      icon: '🔄',
      keywords: ['reindex', 'index', 'rebuild', 'refresh'],
      onExecute: () => {
        setCommandPaletteOpen(false)
        triggerReindex().catch(() => { /* non-fatal */ })
      },
    },
  ]

  return (
    <>
      <AppShell
        onSettingsOpen={() => setSettingsOpen(true)}
        onVoiceOpen={() => setVoiceOpen(true)}
        onIngestOpen={() => navigate('/ingest-review')}
        onReviewOpen={() => setReviewOpen(true)}
        onFailedOpen={() => setFailedOpen(true)}
        onChatDocumentDrop={handleChatDocumentDrop}
        ingestCount={ingestCount}
        reviewCount={reviewCount}
        failedCount={failedCount}
      >
        <Routes>
          <Route path="/" element={<ChatScreen onVoiceOpen={() => setVoiceOpen(true)} />} />
          <Route path="/docs" element={<DocumentBrowserScreen />} />
          <Route path="/ingest-review" element={<IngestReviewScreen />} />
          <Route path="/search" element={<SearchScreen />} />
          <Route path="/graph" element={<GraphScreen />} />
          <Route path="/stats" element={<StatsScreen />} />
        </Routes>
      </AppShell>
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <VoiceModal
        open={voiceOpen}
        onClose={() => setVoiceOpen(false)}
        onSaved={handleVoiceSaved}
        voiceBackend={voiceBackend}
      />
      <ReviewQueue
        open={reviewOpen}
        onClose={() => setReviewOpen(false)}
        onApprove={refreshReviewCount}
      />
      <FailedCaptures
        open={failedOpen}
        onClose={() => setFailedOpen(false)}
        onCountUpdate={setFailedCount}
      />
      <CommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        extraActions={extraActions}
      />
      <ChatSessionPickerDialog
        open={droppedDraft !== null}
        sessions={loadSessions()}
        title="Add dropped document to chat"
        onClose={() => setDroppedDraft(null)}
        onCreateNew={() => {
          if (!droppedDraft) return
          const session = addGroundingToSession(null, droppedDraft)
          setDroppedDraft(null)
          openChatSession(session.id)
        }}
        onSelectSession={sessionId => {
          if (!droppedDraft) return
          const session = addGroundingToSession(sessionId, droppedDraft)
          setDroppedDraft(null)
          openChatSession(session.id)
        }}
      />
    </>
  )
}

// ── Root component ─────────────────────────────────────────────────────────────

function App() {
  const themeValue = useThemeProvider()

  return (
    <ThemeContext.Provider value={themeValue}>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </ThemeContext.Provider>
  )
}

export default App

