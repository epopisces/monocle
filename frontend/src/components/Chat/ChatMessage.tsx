import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import type { ThreadMessage, ToolCallEntry, NoteCardEntry } from '../../hooks/useChat'
import './ChatMessage.css'

// ── Vault path linkifier ──────────────────────────────────────────
// Converts bare paths like inbox/note.md → markdown links, skipping
// already-linked content and code spans.
const VAULT_PATH_RE = /(?<![\[(`])(\b(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_-]+\.md\b)(?!\))/g

function linkifyVaultPaths(text: string): string {
  return text.replace(VAULT_PATH_RE, (_, p: string) =>
    `[${p}](/docs?path=${encodeURIComponent(p)})`,
  )
}

// ── Custom link component — calls useNavigate only when rendered ──

function VaultLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  const navigate = useNavigate()
  if (href?.startsWith('/docs?path=')) {
    const path = decodeURIComponent(href.slice('/docs?path='.length))
    return (
      <button
        className="chat-vault-link"
        onClick={() => navigate(`/docs?path=${encodeURIComponent(path)}`)}
      >
        {children}
      </button>
    )
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  )
}

const MARKDOWN_COMPONENTS: Components = { a: VaultLink }

function ToolCallDisclosure({ call }: { call: ToolCallEntry }) {
  const hasError = Boolean(call.error)
  const countLabel =
    call.resultCount !== undefined
      ? ` — ${call.resultCount} result${call.resultCount === 1 ? '' : 's'}`
      : ''
  const label = hasError
    ? `⚠ \`${call.name}\` failed`
    : `Used \`${call.name}\`${countLabel}`

  return (
    <details className={`tool-call${hasError ? ' tool-call--error' : ''}`}>
      <summary className="tool-call__summary">{label}</summary>
      {call.error && <pre className="tool-call__error-detail">{call.error}</pre>}
    </details>
  )
}

function NoteCard({ note }: { note: NoteCardEntry }) {
  const navigate = useNavigate()
  return (
    <div
      className="note-card note-card--clickable"
      data-testid="note-card"
      title="Click to open"
      onClick={() => navigate(`/docs?path=${encodeURIComponent(note.filePath)}`)}
    >
      <span className="note-card__icon">📄</span>
      <span className="note-card__info">
        <span className="note-card__type">{note.type}</span>
        <span className="note-card__path">{note.filePath}</span>
      </span>
    </div>
  )
}

interface Props {
  message: ThreadMessage
}

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={`chat-message chat-message--${isUser ? 'user' : 'assistant'}`}>
      <div className="chat-message__bubble">
        {/* Tool calls above content */}
        {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
          <div className="chat-message__tools" data-testid="tool-calls">
            {message.toolCalls.map((call, i) => (
              <ToolCallDisclosure key={i} call={call} />
            ))}
          </div>
        )}

        {/* Message content */}
        {isUser ? (
          <p className="chat-message__text">{message.content}</p>
        ) : message.content ? (
          <div className="chat-message__markdown">
            <ReactMarkdown components={MARKDOWN_COMPONENTS}>
              {linkifyVaultPaths(message.content)}
            </ReactMarkdown>
          </div>
        ) : message.isStreaming ? null : (
          <p className="chat-message__text chat-message__text--empty">(empty response)</p>
        )}

        {/* Blinking cursor while streaming */}
        {message.isStreaming && (
          <span className="chat-message__cursor" aria-hidden="true" />
        )}

        {/* Note created card */}
        {message.noteCreated && (
          <NoteCard note={message.noteCreated} />
        )}
      </div>
    </div>
  )
}
