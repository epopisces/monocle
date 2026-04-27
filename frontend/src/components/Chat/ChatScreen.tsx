import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useChat } from '../../hooks/useChat'
import ChatMessage from './ChatMessage'
import ChatInput, { type ChatInputHandle } from './ChatInput'
import './ChatScreen.css'

interface Starter {
  icon: string
  label: string
  prompt: string | null
  action?: string
  sendImmediately?: boolean  // true = send immediately, false/undefined = populate input
  toolHint?: string          // optional tool the agent should invoke first
}

const CHAT_STARTERS: Starter[] = [
  { icon: '👤', label: 'Notes on a person',  prompt: 'What are my notes on ', sendImmediately: false, toolHint: 'search_vault' },
  { icon: '📋', label: 'Open action items',  prompt: 'Show me all open action items', sendImmediately: true, toolHint: 'search_vault' },
  { icon: '📅', label: 'Weekly review',       prompt: 'Run my weekly review', sendImmediately: true },
  { icon: '🎤', label: 'Capture voice note',  prompt: null, action: 'voice' },
  { icon: '🔖', label: 'Recent decisions',    prompt: 'Show my recent decisions', sendImmediately: true, toolHint: 'list_notes' },
  { icon: '📁', label: 'Summarize project',   prompt: 'Summarize my notes about ', sendImmediately: false, toolHint: 'search_vault' },
]

interface Props {
  onVoiceOpen?: () => void
}

export default function ChatScreen({ onVoiceOpen }: Props) {
  const { thread, isStreaming, sessions, currentSessionId, send, selectSession, newSession, refreshSessions } = useChat()
  const [searchParams, setSearchParams] = useSearchParams()
  const threadEndRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<ChatInputHandle>(null)

  // Pending tool hint for populate-style starters (user edits before sending)
  const [pendingHint, setPendingHint] = useState<{ prefix: string; tool: string } | null>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [thread])

  useEffect(() => {
    const requestedSessionId = searchParams.get('session')
    if (!requestedSessionId) return
    refreshSessions()
    selectSession(requestedSessionId)
    setSearchParams({}, { replace: true })
  }, [refreshSessions, searchParams, selectSession, setSearchParams])

  const handleStarterClick = (starter: Starter) => {
    if (starter.action === 'voice') {
      onVoiceOpen?.()
      return
    }
    if (starter.prompt) {
      if (starter.sendImmediately) {
        send(starter.prompt, starter.toolHint)
      } else {
        // Store the hint so we can attach it when the user actually sends
        if (starter.toolHint) {
          setPendingHint({ prefix: starter.prompt, tool: starter.toolHint })
        }
        chatInputRef.current?.populate(starter.prompt)
      }
    }
  }

  // Wrap send to resolve pending tool hints for populate-style starters
  const handleSend = useCallback((content: string, inputToolHint?: string, fetchUrls?: string[]) => {
    let toolHint: string | undefined = inputToolHint
    if (!toolHint && pendingHint && content.startsWith(pendingHint.prefix)) {
      toolHint = pendingHint.tool
    }
    setPendingHint(null)
    send(content, toolHint, fetchUrls)
  }, [pendingHint, send])

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
        <button
          className="chat-screen__new-session-btn"
          onClick={() => newSession()}
          title="New session"
          aria-label="Start a new session"
          data-testid="new-session-btn"
        >
          ✨
        </button>
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
        <ChatInput ref={chatInputRef} onSend={handleSend} disabled={isStreaming} onVoiceClick={onVoiceOpen} />
      </div>
    </div>
  )
}
