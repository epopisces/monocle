const STORAGE_KEY = 'monocle-sessions'
const MAX_SESSIONS = 10

const GROUNDING_TEXT_LIMITS = {
  document: 4000,
  selection: 1600,
  section: 2200,
  sentence: 400,
} as const

export const CHAT_SESSIONS_UPDATED_EVENT = 'monocle:chat-sessions-updated'

export interface ToolCallEntry {
  name: string
  callId?: string
  resultCount?: number
  error?: string
  url?: string
  durationMs?: number
  status?: 'running' | 'success' | 'error'
}

export interface NoteCardEntry {
  filePath: string
  type: string
}

export interface GroundingEntry {
  id: string
  scope: 'document' | 'selection' | 'section' | 'sentence'
  sourcePath: string
  sourceTitle: string
  text: string
  addedAt: string
}

export interface GroundingDraft {
  scope: GroundingEntry['scope']
  sourcePath: string
  sourceTitle: string
  text: string
}

export interface ThreadMessage {
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCallEntry[]
  noteCreated?: NoteCardEntry
  isStreaming?: boolean
  kind?: 'message' | 'grounding'
  grounding?: GroundingEntry
}

export interface Session {
  id: string
  title: string
  createdAt: string
  messages: ThreadMessage[]
}

function isToolCallEntry(value: unknown): value is ToolCallEntry {
  if (!value || typeof value !== 'object') return false
  const entry = value as Partial<ToolCallEntry>
  return typeof entry.name === 'string'
}

function isNoteCardEntry(value: unknown): value is NoteCardEntry {
  if (!value || typeof value !== 'object') return false
  const entry = value as Partial<NoteCardEntry>
  return typeof entry.filePath === 'string' && typeof entry.type === 'string'
}

function isGroundingEntry(value: unknown): value is GroundingEntry {
  if (!value || typeof value !== 'object') return false
  const entry = value as Partial<GroundingEntry>
  return (
    typeof entry.id === 'string'
    && (entry.scope === 'document' || entry.scope === 'selection' || entry.scope === 'section' || entry.scope === 'sentence')
    && typeof entry.sourcePath === 'string'
    && typeof entry.sourceTitle === 'string'
    && typeof entry.text === 'string'
    && typeof entry.addedAt === 'string'
  )
}

function isThreadMessage(value: unknown): value is ThreadMessage {
  if (!value || typeof value !== 'object') return false
  const message = value as Partial<ThreadMessage>
  if (message.role !== 'user' && message.role !== 'assistant') return false
  if (typeof message.content !== 'string') return false
  if (message.toolCalls && (!Array.isArray(message.toolCalls) || !message.toolCalls.every(isToolCallEntry))) return false
  if (message.noteCreated && !isNoteCardEntry(message.noteCreated)) return false
  if (message.kind && message.kind !== 'message' && message.kind !== 'grounding') return false
  if (message.grounding && !isGroundingEntry(message.grounding)) return false
  if (message.grounding && message.kind !== 'grounding') return false
  if (message.kind === 'grounding' && !message.grounding) return false
  if (message.kind === 'message' && message.grounding) return false
  return true
}

function isSession(value: unknown): value is Session {
  if (!value || typeof value !== 'object') return false
  const session = value as Partial<Session>
  return (
    typeof session.id === 'string'
    && typeof session.title === 'string'
    && typeof session.createdAt === 'string'
    && Array.isArray(session.messages)
    && session.messages.every(isThreadMessage)
  )
}

function normalizeGroundingText(scope: GroundingDraft['scope'], text: string): string {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  const maxChars = GROUNDING_TEXT_LIMITS[scope]
  return normalized.length > maxChars ? `${normalized.slice(0, maxChars).trimEnd()}…` : normalized
}

function emitSessionsUpdated() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new Event(CHAT_SESSIONS_UPDATED_EVENT))
}

export function loadSessions(): Session[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? parsed.filter(isSession) : []
  } catch {
    return []
  }
}

export function replaceSessions(next: Session[], emitUpdate = true) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // localStorage quota exceeded — silently ignore
  }
  if (emitUpdate) emitSessionsUpdated()
}

export function persistSession(session: Session, prev: Session[], emitUpdate = true): Session[] {
  const filtered = prev.filter(s => s.id !== session.id)
  const updated = [session, ...filtered].slice(0, MAX_SESSIONS)
  replaceSessions(updated, emitUpdate)
  return updated
}

export function generateSessionId(): string {
  return `sess-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function createGroundingMessage(entry: GroundingEntry): ThreadMessage {
  return {
    role: 'user',
    kind: 'grounding',
    content: entry.text,
    grounding: entry,
  }
}

export function groundingToApiContent(entry: GroundingEntry): string {
  return [
    `[User-added grounding]`,
    `Source: ${entry.sourceTitle} (${entry.sourcePath})`,
    `Scope: ${entry.scope}`,
    '',
    entry.text,
  ].join('\n')
}

export function upsertGroundingSession(sessionId: string | null, entry: GroundingEntry): Session {
  const sessions = loadSessions()
  const existing = sessionId ? sessions.find(s => s.id === sessionId) : undefined
  const nextSession: Session = existing
    ? {
        ...existing,
        messages: [...existing.messages, createGroundingMessage(entry)],
      }
    : {
        id: sessionId ?? generateSessionId(),
        title: entry.sourceTitle.slice(0, 60) || 'Context session',
        createdAt: new Date().toISOString(),
        messages: [createGroundingMessage(entry)],
      }
  persistSession(nextSession, sessions)
  return nextSession
}

export function materializeGroundingEntry(draft: GroundingDraft): GroundingEntry {
  const text = normalizeGroundingText(draft.scope, draft.text)
  return {
    id: `ctx-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    addedAt: new Date().toISOString(),
    ...draft,
    text,
  }
}

export function normalizeGroundingDraft(draft: GroundingDraft): GroundingDraft | null {
  const text = normalizeGroundingText(draft.scope, draft.text)
  if (!text) return null
  return {
    ...draft,
    sourcePath: draft.sourcePath.trim(),
    sourceTitle: draft.sourceTitle.trim(),
    text,
  }
}

export function addGroundingToSession(sessionId: string | null, draft: GroundingDraft): Session {
  const normalized = normalizeGroundingDraft(draft)
  if (!normalized) {
    throw new Error('Cannot add empty grounding to a session')
  }
  return upsertGroundingSession(sessionId, materializeGroundingEntry(normalized))
}