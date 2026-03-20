import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ThemeContext, useThemeProvider } from './hooks/useTheme'
import AppShell from './components/layout/AppShell'
import SettingsModal from './components/SettingsModal'
import ChatScreen from './components/Chat/ChatScreen'
import DocumentBrowserScreen from './components/DocumentBrowser/DocumentBrowserScreen'
import SearchScreen from './components/Search/SearchScreen'
import GraphScreen from './components/Graph/GraphScreen'
import VoiceModal from './components/VoiceModal/VoiceModal'
import ReviewQueue from './components/ReviewQueue/ReviewQueue'
import FailedCaptures from './components/FailedCaptures/FailedCaptures'
import { getReviewCount } from './api/review'
import { getSettings } from './api/settings'

/* Placeholder screen components — replaced in M20 */
const StatsScreen = () => <div className="screen-placeholder">📊 Stats — coming in M20</div>

function App() {
  const themeValue = useThemeProvider()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [voiceOpen, setVoiceOpen] = useState(false)
  const [reviewOpen, setReviewOpen] = useState(false)
  const [failedOpen, setFailedOpen] = useState(false)
  const [reviewCount, setReviewCount] = useState(0)
  const [failedCount, setFailedCount] = useState(0)
  const [voiceBackend, setVoiceBackend] = useState<'whisper' | 'web_speech'>('whisper')

  // Fetch server settings once on mount to get the voice_input_backend preference
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

  // Poll review count on mount and every 30 s
  useEffect(() => {
    refreshReviewCount()
    const id = setInterval(refreshReviewCount, 30_000)
    return () => clearInterval(id)
  }, [refreshReviewCount])

  const handleVoiceSaved = useCallback(() => {
    refreshReviewCount()
  }, [refreshReviewCount])

  return (
    <ThemeContext.Provider value={themeValue}>
      <BrowserRouter>
        <AppShell
          onSettingsOpen={() => setSettingsOpen(true)}
          onVoiceOpen={() => setVoiceOpen(true)}
          onReviewOpen={() => setReviewOpen(true)}
          onFailedOpen={() => setFailedOpen(true)}
          reviewCount={reviewCount}
          failedCount={failedCount}
        >
          <Routes>
            <Route path="/" element={<ChatScreen onVoiceOpen={() => setVoiceOpen(true)} />} />
            <Route path="/docs" element={<DocumentBrowserScreen />} />
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
      </BrowserRouter>
    </ThemeContext.Provider>
  )
}

export default App

