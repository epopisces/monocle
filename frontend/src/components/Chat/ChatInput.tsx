import React, { useRef, useState, forwardRef, useMemo } from 'react'
import './ChatInput.css'

// Detect all http/https URLs in the input text (global flag — finds every match)
const URL_RE_GLOBAL = /https?:\/\/[^\s)>\]"']+/g
const TRAILING_URL_PUNCT_RE = /[.,;:!?]+$/


function normalizeDetectedUrl(url: string): string {
  return url.replace(TRAILING_URL_PUNCT_RE, '')
}

interface Props {
  onSend: (content: string, toolHint?: string, fetchUrls?: string[]) => void
  onVoiceClick?: () => void
  disabled?: boolean
}

export interface ChatInputHandle {
  populate: (text: string) => void
  focus: () => void
}

const ChatInput = forwardRef<ChatInputHandle, Props>(({ onSend, onVoiceClick, disabled }, ref) => {
  const [value, setValue] = useState('')
  const [optedOutUrls, setOptedOutUrls] = useState<Set<string>>(new Set())
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

  // Prune opted-out set to only URLs still present in the input (removes stale entries)
  const activeOptedOut = useMemo<Set<string>>(() => {
    const urlSet = new Set(detectedUrls)
    const pruned = new Set<string>()
    for (const u of optedOutUrls) {
      if (urlSet.has(u)) pruned.add(u)
    }
    return pruned
  }, [detectedUrls, optedOutUrls])

  const toggleOptOut = (url: string) => {
    setOptedOutUrls(prev => {
      const next = new Set(prev)
      if (next.has(url)) {
        next.delete(url)
      } else {
        next.add(url)
      }
      return next
    })
  }

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
    const fetchUrls = detectedUrls.filter(u => !activeOptedOut.has(u))
    onSend(trimmed, toolHint, fetchUrls.length > 0 ? fetchUrls : undefined)
    setValue('')
    setOptedOutUrls(new Set())
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
      // Send; fetchUrls are computed automatically from opted-in URL pills
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
      {detectedUrls.length > 0 && (
        <div className="chat-input__url-pills" data-testid="url-pills">
          {detectedUrls.map(url => {
            const isOptedOut = activeOptedOut.has(url)
            let label = url
            try { label = new URL(url).hostname } catch { label = url.slice(0, 40) }
            return (
              <button
                key={url}
                className={`chat-input__url-pill${isOptedOut ? ' chat-input__url-pill--opted-out' : ''}`}
                onClick={() => toggleOptOut(url)}
                disabled={disabled}
                title={isOptedOut ? `Skip fetch (click to re-enable): ${url}` : `Will fetch & summarize (click to skip): ${url}`}
                data-testid={isOptedOut ? 'url-pill-opted-out' : 'url-pill-active'}
                type="button"
              >
                🔗 {label}
                <span className="chat-input__url-pill-x" aria-hidden="true">
                  {isOptedOut ? '↩' : '×'}
                </span>
              </button>
            )
          })}
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
