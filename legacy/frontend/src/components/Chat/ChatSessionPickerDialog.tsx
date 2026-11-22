import type { Session } from './sessionStore'
import './ChatSessionPickerDialog.css'

interface Props {
  open: boolean
  sessions: Session[]
  title: string
  onClose: () => void
  onCreateNew: () => void
  onSelectSession: (sessionId: string) => void
}

export default function ChatSessionPickerDialog({
  open,
  sessions,
  title,
  onClose,
  onCreateNew,
  onSelectSession,
}: Props) {
  if (!open) return null

  return (
    <div className="chat-session-picker" role="dialog" aria-modal="true" aria-label={title} data-testid="chat-session-picker">
      <div className="chat-session-picker__backdrop" onClick={onClose} aria-hidden="true" />
      <div className="chat-session-picker__panel">
        <div className="chat-session-picker__header">
          <div>
            <h2>{title}</h2>
            <p>Choose an existing chat session or start a new one.</p>
          </div>
          <button type="button" className="chat-session-picker__close" onClick={onClose} aria-label="Close add-to-chat dialog">✕</button>
        </div>
        <button type="button" className="chat-session-picker__new" onClick={onCreateNew} data-testid="chat-session-picker-new">
          Start new chat session
        </button>
        {sessions.length === 0 ? (
          <p className="chat-session-picker__empty">No saved chat sessions yet.</p>
        ) : (
          <ul className="chat-session-picker__list" data-testid="chat-session-picker-list">
            {sessions.map(session => (
              <li key={session.id}>
                <button
                  type="button"
                  className="chat-session-picker__item"
                  onClick={() => onSelectSession(session.id)}
                  data-testid={`chat-session-picker-item-${session.id}`}
                >
                  <strong>{session.title}</strong>
                  <span>{new Date(session.createdAt).toLocaleDateString()} · {session.messages.length} item{session.messages.length === 1 ? '' : 's'}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}