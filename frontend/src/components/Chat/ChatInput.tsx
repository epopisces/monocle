import { useRef, useState } from 'react'
import './ChatInput.css'

interface Props {
  onSend: (content: string) => void
  onVoiceClick?: () => void
  disabled?: boolean
}

export default function ChatInput({ onSend, onVoiceClick, disabled }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const doSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      doSend()
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value)
    // Auto-grow up to 6 lines (24px line-height × 6)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`
  }

  return (
    <div className="chat-input">
      <textarea
        ref={textareaRef}
        className="chat-input__textarea"
        placeholder="Message the assistant…"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={1}
        aria-label="Message input"
        data-testid="chat-input-textarea"
      />
      <div className="chat-input__actions">
        {onVoiceClick && (
          <button
            className="chat-input__btn chat-input__btn--voice"
            onClick={onVoiceClick}
            disabled={disabled}
            aria-label="Voice input"
            title="Voice capture"
            data-testid="voice-btn"
          >
            🎤
          </button>
        )}
        <button
          className="chat-input__btn chat-input__btn--send"
          onClick={doSend}
          disabled={disabled || !value.trim()}
          aria-label="Send message"
          title="Send"
          data-testid="send-btn"
        >
          →
        </button>
      </div>
    </div>
  )
}
