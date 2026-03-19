import { useCallback, useRef, useState } from 'react'
import { streamChat, type ChatMessage } from '../api/chat'

const STORAGE_KEY = 'monocle-sessions'
const MAX_SESSIONS = 10

export interface ToolCallEntry {
  name: string
  resultCount?: number
  error?: string
}

export interface NoteCardEntry {
  filePath: string
  type: string
}

export interface ThreadMessage {
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCallEntry[]
  noteCreated?: NoteCardEntry
  isStreaming?: boolean
}

export interface Session {
  id: string
  title: string
  createdAt: string
  messages: ThreadMessage[]
}

function loadSessions(): Session[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Session[]) : []
  } catch {
    return []
  }
}

function persistSession(session: Session, prev: Session[]): Session[] {
  const filtered = prev.filter(s => s.id !== session.id)
  const updated = [session, ...filtered].slice(0, MAX_SESSIONS)
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
  } catch {
    // localStorage quota exceeded — silently ignore
  }
  return updated
}

function generateId(): string {
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function useChat() {
  const [thread, setThread] = useState<ThreadMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessions, setSessions] = useState<Session[]>(loadSessions)
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)
  // Refs for stable closure access without stale values
  const threadRef = useRef<ThreadMessage[]>(thread)
  const sessionIdRef = useRef<string | null>(currentSessionId)
  threadRef.current = thread
  sessionIdRef.current = currentSessionId

  // send is stable (empty deps) — reads latest values via refs
  const send = useCallback(async (content: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    const sessionId = sessionIdRef.current ?? generateId()
    setCurrentSessionId(sessionId)

    // Build API message list from current thread + new user turn
    const messagesForApi: ChatMessage[] = [
      ...threadRef.current.map(m => ({ role: m.role as 'user' | 'assistant', content: m.content })),
      { role: 'user', content },
    ]

    setThread(prev => [
      ...prev,
      { role: 'user', content },
      { role: 'assistant', content: '', toolCalls: [], isStreaming: true },
    ])
    setIsStreaming(true)

    try {
      for await (const evt of streamChat({ messages: messagesForApi, session_id: sessionId }, controller.signal)) {
        if (controller.signal.aborted) break

        switch (evt.event) {
          case 'token':
            setThread(prev => {
              const next = [...prev]
              const last = { ...next[next.length - 1] }
              last.content += evt.data.delta
              next[next.length - 1] = last
              return next
            })
            break

          case 'tool_call':
            setThread(prev => {
              const next = [...prev]
              const last = { ...next[next.length - 1] }
              last.toolCalls = [
                ...(last.toolCalls ?? []),
                { name: evt.data.name, resultCount: evt.data.result_count },
              ]
              next[next.length - 1] = last
              return next
            })
            break

          case 'tool_error':
            setThread(prev => {
              const next = [...prev]
              const last = { ...next[next.length - 1] }
              const calls = [...(last.toolCalls ?? [])]
              // Update the last tool call matching the name
              for (let i = calls.length - 1; i >= 0; i--) {
                if (calls[i].name === evt.data.name) {
                  calls[i] = { ...calls[i], error: evt.data.error }
                  break
                }
              }
              last.toolCalls = calls
              next[next.length - 1] = last
              return next
            })
            break

          case 'note_created':
            setThread(prev => {
              const next = [...prev]
              const last = { ...next[next.length - 1] }
              last.noteCreated = { filePath: evt.data.file_path, type: evt.data.type }
              next[next.length - 1] = last
              return next
            })
            break

          case 'done': {
            const finalSessionId = evt.data.session_id ?? sessionId
            setCurrentSessionId(finalSessionId)
            setThread(prev => {
              const next = [...prev]
              next[next.length - 1] = { ...next[next.length - 1], isStreaming: false }
              const title = content.slice(0, 60)
              const session: Session = {
                id: finalSessionId,
                title,
                createdAt: new Date().toISOString(),
                messages: next,
              }
              setSessions(prevSessions => persistSession(session, prevSessions))
              return next
            })
            setIsStreaming(false)
            break
          }

          case 'error':
            setThread(prev => {
              const next = [...prev]
              next[next.length - 1] = {
                ...next[next.length - 1],
                isStreaming: false,
                content: evt.data.message || 'An error occurred.',
              }
              return next
            })
            setIsStreaming(false)
            break
        }
      }
    } catch {
      if (controller.signal.aborted) return
      setThread(prev => {
        const next = [...prev]
        next[next.length - 1] = {
          ...next[next.length - 1],
          isStreaming: false,
          content: 'Connection error — please try again.',
        }
        return next
      })
      setIsStreaming(false)
    }
  }, []) // stable — reads thread/sessionId via refs

  const selectSession = useCallback((id: string) => {
    const session = sessions.find(s => s.id === id)
    if (!session) return
    abortRef.current?.abort()
    setThread(session.messages.map(m => ({ ...m, isStreaming: false })))
    setCurrentSessionId(id)
    setIsStreaming(false)
  }, [sessions])

  const newSession = useCallback(() => {
    abortRef.current?.abort()
    setThread([])
    setCurrentSessionId(null)
    setIsStreaming(false)
  }, [])

  return { thread, isStreaming, sessions, currentSessionId, send, selectSession, newSession }
}
