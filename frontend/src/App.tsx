import { useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ThemeContext, useThemeProvider } from './hooks/useTheme'
import AppShell from './components/layout/AppShell'
import SettingsModal from './components/SettingsModal'
import ChatScreen from './components/Chat/ChatScreen'

/* Placeholder screen components — replaced in M17–M20 */
const DocsScreen = () => <div className="screen-placeholder">📄 Document Browser — coming in M17</div>
const SearchScreen = () => <div className="screen-placeholder">🔍 Search — coming in M17</div>
const GraphScreen = () => <div className="screen-placeholder">◉ Graph — coming in M18</div>
const StatsScreen = () => <div className="screen-placeholder">📊 Stats — coming in M20</div>

function App() {
  const themeValue = useThemeProvider()
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <ThemeContext.Provider value={themeValue}>
      <BrowserRouter>
        <AppShell onSettingsOpen={() => setSettingsOpen(true)}>
          <Routes>
            <Route path="/" element={<ChatScreen />} />
            <Route path="/docs" element={<DocsScreen />} />
            <Route path="/search" element={<SearchScreen />} />
            <Route path="/graph" element={<GraphScreen />} />
            <Route path="/stats" element={<StatsScreen />} />
          </Routes>
        </AppShell>
        <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      </BrowserRouter>
    </ThemeContext.Provider>
  )
}

export default App

