import { useEffect, useRef } from 'react'
import { useChat } from '../../hooks/useChat'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'
import './ChatScreen.css'

interface Starter {
  icon: string
  label: string
  prompt: string | null
  action?: string
}

const CHAT_STARTERS: Starter[] = [
  { icon: '👤', label: 'Notes on a person',  prompt: 'What are my notes on ' },
  { icon: '📋', label: 'Open action items',  prompt: 'Show me all open action items' },
  { icon: '📅', label: 'Weekly review',       prompt: 'Run my weekly review' },
  { icon: '🎤', label: 'Capture voice note',  prompt: null, action: 'voice' },
  { icon: '🔖', label: 'Recent decisions',    prompt: 'Show my recent decisions' },
  { icon: '📁', label: 'Summarize project',   prompt: 'Summarize my notes about ' },
]

export default function ChatScreen() {
  const { thread, isStreaming, sessions, currentSessionId, send, selectSession, newSession } = useChat()
  const threadEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [thread])

  const handleStarterClick = (starter: Starter) => {
    if (starter.action === 'voice') {
      // Voice modal wired in M19
      return
    }
    if (starter.prompt) {
      send(starter.prompt)
    }
  }

  const showStarters = thread.length === 0

  return (
    <div className="chat-screen">
      {/* Session picker */}
      <div className="chat-screen__session-bar">
        <select
          className="chat-screen__session-picker"
          value={currentSessionId ?? ''}
          onChange={e => {
            if (e.target.value === '') newSession()
            else selectSession(e.target.value)
          }}
          aria-label="Session picker"
          data-testid="session-picker"
        >
          <option value="">+ New session</option>
          {sessions.map(s => (
            <option key={s.id} value={s.id}>
              {new Date(s.createdAt).toLocaleDateString()} — {s.title}
            </option>
          ))}
        </select>
      </div>

      {/* Thread or chat starters */}
      <div className="chat-screen__thread" role="log" aria-label="Chat thread">
        {showStarters ? (
          <div className="chat-starters" data-testid="chat-starters">
            <h2 className="chat-starters__heading">How can I help you today?</h2>
            <div className="chat-starters__grid">
              {CHAT_STARTERS.map(starter => (
                <button
                  key={starter.label}
                  className="chat-starter"
                  onClick={() => handleStarterClick(starter)}
                  data-testid="chat-starter"
                >
                  <span className="chat-starter__icon">{starter.icon}</span>
                  <span className="chat-starter__label">{starter.label}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {thread.map((msg, i) => (
              <ChatMessage key={i} message={msg} />
            ))}
            <div ref={threadEndRef} />
          </>
        )}
      </div>

      {/* Input area */}
      <div className="chat-screen__input-area">
        <ChatInput onSend={send} disabled={isStreaming} />
      </div>
    </div>
  )
}
