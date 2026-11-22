import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChat, type ChatMessage } from '../api/chat'
import {
  CHAT_SESSIONS_UPDATED_EVENT,
  generateSessionId,
  groundingToApiContent,
  loadSessions,
  persistSession,
  type Session,
  type ThreadMessage,
} from '../components/Chat/sessionStore'

function toApiMessage(message: ThreadMessage): ChatMessage {
  if (message.kind === 'grounding' && message.grounding) {
    return { role: 'user', content: groundingToApiContent(message.grounding) }
  }
  return { role: message.role as 'user' | 'assistant', content: message.content }
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

  const refreshSessions = useCallback(() => {
    setSessions(loadSessions())
  }, [])

  useEffect(() => {
    const handleSessionsUpdated = () => refreshSessions()
    window.addEventListener(CHAT_SESSIONS_UPDATED_EVENT, handleSessionsUpdated)
    return () => window.removeEventListener(CHAT_SESSIONS_UPDATED_EVENT, handleSessionsUpdated)
  }, [refreshSessions])

  // send is stable (empty deps) — reads latest values via refs
  const send = useCallback(async (content: string, toolHint?: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    const sessionId = sessionIdRef.current ?? generateSessionId()
    setCurrentSessionId(sessionId)

    // Build API message list from current thread + new user turn
    const messagesForApi: ChatMessage[] = [
      ...threadRef.current.map(toApiMessage),
      { role: 'user', content },
    ]

    setThread(prev => [
      ...prev,
      { role: 'user', content },
      { role: 'assistant', content: '', toolCalls: [], isStreaming: true },
    ])
    setIsStreaming(true)

    try {
      for await (const evt of streamChat({ messages: messagesForApi, session_id: sessionId, tool_hint: toolHint }, controller.signal)) {
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
                {
                  name: evt.data.name,
                  callId: evt.data.call_id,
                  url: evt.data.url,
                  resultCount: evt.data.result_count,
                  status: 'running',
                },
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
              // Update the matching tool call, preferring call_id when present.
              for (let i = calls.length - 1; i >= 0; i--) {
                if ((evt.data.call_id && calls[i].callId === evt.data.call_id) || calls[i].name === evt.data.name) {
                  calls[i] = { ...calls[i], error: evt.data.error, status: 'error' }
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
            const completedWithError = evt.data.status === 'error'
            const unfinishedToolError = evt.data.error ?? 'Tool execution did not finish before the request ended.'
            setCurrentSessionId(finalSessionId)
            setThread(prev => {
              const next = [...prev]
              const last = { ...next[next.length - 1] }
              last.isStreaming = false
              last.toolCalls = (last.toolCalls ?? []).map(call =>
                call.status === 'running'
                  ? completedWithError
                    ? { ...call, status: 'error', error: call.error ?? unfinishedToolError }
                    : { ...call, status: 'success' }
                  : call,
              )
              next[next.length - 1] = last
              const title = content.slice(0, 60)
              const session: Session = {
                id: finalSessionId,
                title,
                createdAt: new Date().toISOString(),
                messages: next,
              }
              setSessions(prevSessions => persistSession(session, prevSessions, false))
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
    const session = loadSessions().find(s => s.id === id) ?? sessions.find(s => s.id === id)
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

  return { thread, isStreaming, sessions, currentSessionId, send, selectSession, newSession, refreshSessions }
}
