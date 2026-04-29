import React, { useRef, useState, forwardRef, useMemo } from 'react'
import { mapErrorToUserMessage } from '../../utils/errorMessages'
import './ChatInput.css'

// Detect all http/https URLs in the input text (global flag — finds every match)
const URL_RE_GLOBAL = /https?:\/\/[^\s)>\]"']+/g
const TRAILING_URL_PUNCT_RE = /[.,;:!?]+$/
export const MAX_CAPTURE_URLS = 5


function normalizeDetectedUrl(url: string): string {
  return url.replace(TRAILING_URL_PUNCT_RE, '')
}

interface Props {
  onSend: (content: string, toolHint?: string) => void
  onCaptureUrls?: (urls: string[]) => Promise<void> | void
  onVoiceClick?: () => void
  disabled?: boolean
}

export interface ChatInputHandle {
  populate: (text: string) => void
  focus: () => void
}

const ChatInput = forwardRef<ChatInputHandle, Props>(({ onSend, onCaptureUrls, onVoiceClick, disabled }, ref) => {
  const [value, setValue] = useState('')
  const [isCapturingUrls, setIsCapturingUrls] = useState(false)
  const [captureFeedback, setCaptureFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // History navigation — shell-like ArrowUp/Down through sent messages
  const historyRef = useRef<string[]>([])
  const historyIndexRef = useRef<number>(-1) // -1 = not browsing
  const draftRef = useRef<string>('')       // saved value before browsing started

  // All unique URLs found in the current input value
  const detectedUrls = useMemo<string[]>(() => {
    const matches = [...value.matchAll(URL_RE_GLOBAL)]
    const seen = new Set<string>()
    const result: string[] = []
    for (const m of matches) {
      const normalized = normalizeDetectedUrl(m[0])
      if (!normalized || seen.has(normalized)) {
        continue
      }
      seen.add(normalized)
      result.push(normalized)
    }
    return result
  }, [value])

  // Expose methods for parent to populate the input
  React.useImperativeHandle(ref, () => ({
    populate: (text: string) => {
      setValue(text)
      setCaptureFeedback(null)
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
    setCaptureFeedback(null)
    onSend(trimmed, toolHint)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleCaptureUrls = async () => {
    if (!onCaptureUrls || detectedUrls.length === 0 || disabled || isCapturingUrls) {
      return
    }

    const captureUrls = detectedUrls.slice(0, MAX_CAPTURE_URLS)
    const skippedCount = Math.max(0, detectedUrls.length - captureUrls.length)

    setCaptureFeedback(null)
    setIsCapturingUrls(true)
    try {
      await onCaptureUrls(captureUrls)
      setCaptureFeedback({
        kind: 'success',
        message:
          skippedCount > 0
            ? `Captured ${captureUrls.length} URLs to the capture workbench. Skipped ${skippedCount} additional detected URL${skippedCount === 1 ? '' : 's'} to keep capture bounded.`
            : `Captured ${captureUrls.length} URL${captureUrls.length === 1 ? '' : 's'} to the capture workbench.`,
      })
    } catch (error) {
      setCaptureFeedback({
        kind: 'error',
        message: mapErrorToUserMessage(error),
      })
    } finally {
      setIsCapturingUrls(false)
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
    setCaptureFeedback(null)
    // Auto-grow up to 6 lines (24px line-height × 6)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`
  }

  return (
    <div className="chat-input">
      {detectedUrls.length > 0 && (
        <div className="chat-input__url-pills" data-testid="url-pills">
          <span className="chat-input__url-label">Detected URLs</span>
          {detectedUrls.map(url => {
            let label = url
            try { label = new URL(url).hostname } catch { label = url.slice(0, 40) }
            return (
              <span
                key={url}
                className="chat-input__url-pill"
                title={url}
                data-testid="url-pill"
              >
                🔗 {label}
              </span>
            )
          })}
          <button
            className="chat-input__capture-btn"
            onClick={() => { void handleCaptureUrls() }}
            disabled={disabled || isCapturingUrls || !onCaptureUrls}
            data-testid="capture-urls-btn"
            type="button"
          >
            {isCapturingUrls ? 'Capturing…' : `Capture URLs${detectedUrls.length > 1 ? ` (${detectedUrls.length})` : ''}`}
          </button>
        </div>
      )}
      {captureFeedback && (
        <p
          className={`chat-input__capture-feedback chat-input__capture-feedback--${captureFeedback.kind}`}
          data-testid="url-capture-feedback"
          role={captureFeedback.kind === 'error' ? 'alert' : 'status'}
        >
          {captureFeedback.message}
        </p>
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
              ◎
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
