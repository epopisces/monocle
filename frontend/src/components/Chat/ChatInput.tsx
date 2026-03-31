import React, { useRef, useState, forwardRef, useMemo } from 'react'
import './ChatInput.css'

// Detect http/https URLs in the input text
const URL_RE = /https?:\/\/[^\s)>\]"']+/

interface Props {
  onSend: (content: string, toolHint?: string) => void
  onVoiceClick?: () => void
  disabled?: boolean
}

export interface ChatInputHandle {
  populate: (text: string) => void
  focus: () => void
}

const ChatInput = forwardRef<ChatInputHandle, Props>(({ onSend, onVoiceClick, disabled }, ref) => {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // History navigation — shell-like ArrowUp/Down through sent messages
  const historyRef = useRef<string[]>([])
  const historyIndexRef = useRef<number>(-1) // -1 = not browsing
  const draftRef = useRef<string>('')       // saved value before browsing started

  // Detected URL (null when none present in current value)
  const detectedUrl = useMemo<string | null>(() => {
    const m = URL_RE.exec(value)
    return m ? m[0] : null
  }, [value])

  // Expose methods for parent to populate the input
  React.useImperativeHandle(ref, () => ({
    populate: (text: string) => {
      setValue(text)
      // Focus and position cursor at end
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.focus()
          textareaRef.current.setSelectionRange(text.length, text.length)
          // Adjust height
          textareaRef.current.style.height = 'auto'
          textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 144)}px`
        }
      }, 0)
    },
    focus: () => {
      textareaRef.current?.focus()
    },
  }), [])

  const doSend = (toolHint?: string) => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    // Push to history; ignore duplicates of the most-recent entry
    const hist = historyRef.current
    if (hist.length === 0 || hist[hist.length - 1] !== trimmed) {
      historyRef.current = [...hist, trimmed]
    }
    historyIndexRef.current = -1
    draftRef.current = ''
    onSend(trimmed, toolHint)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const _adjustHeight = (el: HTMLTextAreaElement, newVal: string) => {
    setTimeout(() => {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 144)}px`
      el.setSelectionRange(newVal.length, newVal.length)
    }, 0)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      // Send without tool hint; if a URL is detected, the UI prompt gives user choice
      doSend()
      return
    }

    const el = textareaRef.current
    const cursorPos = el?.selectionStart ?? 0

    if (e.key === 'ArrowUp') {
      // Only hijack when cursor is on the first line (no newline before it)
      const beforeCursor = value.slice(0, cursorPos)
      if (beforeCursor.includes('\n')) return
      const hist = historyRef.current
      if (hist.length === 0) return
      e.preventDefault()
      if (historyIndexRef.current === -1) {
        draftRef.current = value
        historyIndexRef.current = hist.length - 1
      } else if (historyIndexRef.current > 0) {
        historyIndexRef.current -= 1
      }
      const newVal = hist[historyIndexRef.current]
      setValue(newVal)
      if (el) _adjustHeight(el, newVal)
      return
    }

    if (e.key === 'ArrowDown') {
      // Only hijack when cursor is on the last line (no newline after it)
      const afterCursor = value.slice(cursorPos)
      if (afterCursor.includes('\n')) return
      if (historyIndexRef.current === -1) return
      e.preventDefault()
      historyIndexRef.current += 1
      if (historyIndexRef.current >= historyRef.current.length) {
        historyIndexRef.current = -1
        const draft = draftRef.current
        setValue(draft)
        if (el) _adjustHeight(el, draft)
      } else {
        const newVal = historyRef.current[historyIndexRef.current]
        setValue(newVal)
        if (el) _adjustHeight(el, newVal)
      }
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
      {detectedUrl && (
        <div className="chat-input__url-suggestion" data-testid="url-suggestion">
          <span className="chat-input__url-suggestion-text">
            🔗 URL detected — fetch &amp; summarize?
          </span>
          <div className="chat-input__url-suggestion-actions">
            <button
              className="chat-input__url-btn chat-input__url-btn--yes"
              onClick={() => doSend('fetch_and_summarize_url')}
              disabled={disabled}
              data-testid="url-fetch-btn"
              type="button"
            >
              Yes, summarize
            </button>
            <button
              className="chat-input__url-btn chat-input__url-btn--no"
              onClick={() => doSend()}
              disabled={disabled}
              data-testid="url-skip-btn"
              type="button"
            >
              No thanks
            </button>
          </div>
        </div>
      )}
      <div className="chat-input__row">
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
            onClick={() => doSend()}
            disabled={disabled || !value.trim()}
            aria-label="Send message"
            title="Send"
            data-testid="send-btn"
          >
            →
          </button>
        </div>
      </div>
    </div>
  )
})

ChatInput.displayName = 'ChatInput'
export default ChatInput
