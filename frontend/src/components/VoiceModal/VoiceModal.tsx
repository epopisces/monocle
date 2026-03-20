import React, { useCallback, useEffect, useReducer, useRef } from 'react'
import { ingest } from '../../api/ingest'
import { transcribeAudio } from '../../api/transcribe'
import './VoiceModal.css'

// ── Types ─────────────────────────────────────────────────────────────────────

type RecordingState = 'idle' | 'recording' | 'transcribing' | 'review' | 'saving'

interface State {
  recordingState: RecordingState
  transcript: string
  interimTranscript: string
  template: string
  error: string | null
}

type Action =
  | { type: 'START_RECORDING' }
  | { type: 'INTERIM'; text: string }
  | { type: 'TO_REVIEW'; text: string }
  | { type: 'TRANSCRIBING' }
  | { type: 'SET_TEMPLATE'; template: string }
  | { type: 'SET_TRANSCRIPT'; text: string }
  | { type: 'SAVING' }
  | { type: 'SAVE_ERROR'; message: string }
  | { type: 'IDLE_ERROR'; message: string }
  | { type: 'RESET' }

const INITIAL: State = {
  recordingState: 'idle',
  transcript: '',
  interimTranscript: '',
  template: 'idea',
  error: null,
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'START_RECORDING':
      return { ...state, recordingState: 'recording', transcript: '', interimTranscript: '', error: null }
    case 'INTERIM':
      return { ...state, interimTranscript: action.text }
    case 'TO_REVIEW':
      return { ...state, recordingState: 'review', transcript: action.text, interimTranscript: '' }
    case 'TRANSCRIBING':
      return { ...state, recordingState: 'transcribing', interimTranscript: '' }
    case 'SET_TEMPLATE':
      return { ...state, template: action.template }
    case 'SET_TRANSCRIPT':
      return { ...state, transcript: action.text }
    case 'SAVING':
      return { ...state, recordingState: 'saving', error: null }
    case 'SAVE_ERROR':
      return { ...state, recordingState: 'review', error: action.message }
    case 'IDLE_ERROR':
      return { ...INITIAL, error: action.message }
    case 'RESET':
      return INITIAL
    default:
      return state
  }
}

const TEMPLATES = [
  { value: 'idea',         label: 'Idea' },
  { value: 'observation',  label: 'Observation' },
  { value: 'decision',     label: 'Decision' },
  { value: 'person_note',  label: 'Person Note' },
  { value: 'meeting_note', label: 'Meeting Note' },
  { value: 'action_item',  label: 'Action Item' },
  { value: 'reference',    label: 'Reference' },
  { value: 'project',      label: 'Project' },
]

// ── SpeechRecognition detection ───────────────────────────────────────────────

// Extend Window type for cross-browser SpeechRecognition
declare global {
  interface Window {
    /* eslint-disable @typescript-eslint/no-explicit-any */
    SpeechRecognition?: any
    webkitSpeechRecognition?: any
    /* eslint-enable @typescript-eslint/no-explicit-any */
  }
}

function getSpeechRecognitionClass() {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  open: boolean
  onClose: () => void
  onSaved?: () => void
  /** Controls which capture path is used.
   *  'whisper'    — always use MediaRecorder + backend Whisper (default).
   *  'web_speech' — prefer Web Speech API; falls back to MediaRecorder+Whisper
   *                 if SpeechRecognition is not available in the browser.
   */
  voiceBackend?: 'whisper' | 'web_speech'
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function VoiceModal({ open, onClose, onSaved, voiceBackend = 'whisper' }: Props) {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const overlayRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recognitionRef = useRef<any>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  // Accumulator ref avoids stale closures in recognition.onresult
  const accumulatedRef = useRef('')

  // Reset + stop everything when panel is closed
  useEffect(() => {
    if (!open) {
      stopAll()
      dispatch({ type: 'RESET' })
    }
  }, [open])

  // Defined early so the ESC useEffect below can list it as a dependency without
  // hitting a temporal dead zone (deps array is evaluated at call-site, not lazily).
  // stopAll is a function declaration — hoisted — so this reference is safe.
  const handleDiscard = useCallback(() => {
    stopAll()
    onClose()
  }, [onClose])

  // Escape key to discard
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleDiscard()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, handleDiscard])

  function stopAll() {
    if (recognitionRef.current) {
      try { recognitionRef.current.abort() } catch { /* ignore */ }
      recognitionRef.current = null
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try { mediaRecorderRef.current.stop() } catch { /* ignore */ }
    }
  }

  const startRecording = useCallback(async () => {
    dispatch({ type: 'START_RECORDING' })
    accumulatedRef.current = ''

    const SpeechRec = voiceBackend === 'web_speech' ? getSpeechRecognitionClass() : null
    // voiceBackend is intentionally in the deps array below — if the prop changes
    // after mount (App.tsx fetches server settings), the next call to startRecording
    // must use the updated value.
    if (SpeechRec) {
      // ── Web Speech API path ──────────────────────────────────────────────
      const recognition = new SpeechRec()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'
      recognitionRef.current = recognition

      recognition.onresult = (e: SpeechRecognitionEvent) => {
        let accumulated = ''
        let interim = ''
        for (let i = 0; i < e.results.length; i++) {
          const r = e.results[i]
          if (r.isFinal) accumulated += r[0].transcript
          else interim += r[0].transcript
        }
        accumulatedRef.current = accumulated
        // Show confirmed final segments in the live transcript during recording
        if (accumulated) dispatch({ type: 'SET_TRANSCRIPT', text: accumulated })
        dispatch({ type: 'INTERIM', text: interim })
      }

      // Tracks whether onerror already handled state — prevents onend double-dispatch
      let errorHandled = false

      recognition.onerror = (e: SpeechRecognitionErrorEvent) => {
        errorHandled = true
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
          dispatch({ type: 'IDLE_ERROR', message: 'Microphone access denied.' })
        } else if (e.error === 'network') {
          dispatch({ type: 'IDLE_ERROR', message: 'Speech recognition unavailable — check network connectivity.' })
        } else if (e.error === 'audio-capture') {
          dispatch({ type: 'IDLE_ERROR', message: 'No microphone found or audio capture failed.' })
        } else if (e.error !== 'aborted') {
          // no-speech, bad-grammar, language-not-supported, etc. → silently reset to idle
          dispatch({ type: 'RESET' })
        }
        // 'aborted' means stopAll() was called (modal close) — useEffect(!open) already dispatches RESET
      }

      recognition.onend = () => {
        recognitionRef.current = null
        if (!errorHandled) {
          dispatch({ type: 'TO_REVIEW', text: accumulatedRef.current.trim() })
        }
      }

      recognition.start()
    } else {
      // ── MediaRecorder (Whisper fallback) path ────────────────────────────
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        audioChunksRef.current = []

        const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : ''
        const mr = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
        mediaRecorderRef.current = mr

        mr.ondataavailable = (e: BlobEvent) => {
          if (e.data.size > 0) audioChunksRef.current.push(e.data)
        }

        const MAX_AUDIO_BYTES = 25 * 1024 * 1024  // 25 MB — matches backend limit

        mr.onstop = async () => {
          // Stop all tracks to release mic indicator
          stream.getTracks().forEach(t => t.stop())

          const blob = new Blob(audioChunksRef.current, { type: mr.mimeType || 'audio/webm' })
          if (blob.size > MAX_AUDIO_BYTES) {
            dispatch({ type: 'SAVE_ERROR', message: 'Recording too large (max 25 MB). Please try a shorter note.' })
            return
          }
          dispatch({ type: 'TRANSCRIBING' })
          try {
            const result = await transcribeAudio(blob, mr.mimeType || 'audio/webm')
            dispatch({ type: 'TO_REVIEW', text: result.transcript })
          } catch {
            dispatch({ type: 'SAVE_ERROR', message: 'Transcription failed. Please try again.' })
          }
        }

        mr.start()
      } catch {
        dispatch({ type: 'SAVE_ERROR', message: 'Microphone access denied.' })
      }
    }
  }, [voiceBackend])

  const stopRecording = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
    } else if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
  }, [])

  const handleSave = useCallback(async () => {
    if (!state.transcript.trim()) return
    dispatch({ type: 'SAVING' })
    try {
      await ingest({
        content: state.transcript,
        source: 'voice',
        template_hint: state.template,
        allow_duplicate: false,
      })
      onSaved?.()
      onClose()
    } catch {
      dispatch({ type: 'SAVE_ERROR', message: 'Failed to save note. Please try again.' })
    }
  }, [state.transcript, state.template, onSaved, onClose])

  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (e.target === overlayRef.current) handleDiscard()
  }, [handleDiscard])

  if (!open) return null

  const { recordingState, transcript, interimTranscript, template, error } = state
  const isReview = recordingState === 'review' || recordingState === 'saving'

  return (
    <div
      className="voice-overlay"
      ref={overlayRef}
      onClick={handleOverlayClick}
      data-testid="voice-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Voice capture"
    >
      <div className="voice-modal">
        <div className="voice-modal__header">
          <h2 className="voice-modal__title">Voice Capture</h2>
          <button
            className="voice-modal__close"
            onClick={handleDiscard}
            aria-label="Close voice capture"
          >
            ✕
          </button>
        </div>

        <div className="voice-modal__body">
          {/* ── Idle ─────────────────────────────────────────────────────── */}
          {recordingState === 'idle' && (
            <div className="voice-modal__idle">
              <p className="voice-modal__hint">
                Click the microphone to start capturing a voice note.
              </p>
              {error && (
                <p className="voice-modal__error" role="alert" data-testid="voice-error">
                  {error}
                </p>
              )}
              <button
                className="voice-modal__mic-btn"
                onClick={startRecording}
                data-testid="start-recording-btn"
                aria-label="Start recording"
              >
                🎤
              </button>
            </div>
          )}

          {/* ── Recording ────────────────────────────────────────────────── */}
          {recordingState === 'recording' && (
            <div className="voice-modal__recording">
              <div className="voice-modal__pulse" aria-hidden="true" />
              <p className="voice-modal__recording-label">Recording…</p>
              {(transcript || interimTranscript) && (
                <div className="voice-modal__live-transcript" data-testid="live-transcript">
                  {transcript && (
                    <span className="voice-modal__final-text">{transcript}</span>
                  )}
                  {interimTranscript && (
                    <span className="voice-modal__interim-text"> {interimTranscript}</span>
                  )}
                </div>
              )}
              <button
                className="voice-modal__stop-btn"
                onClick={stopRecording}
                data-testid="stop-recording-btn"
                aria-label="Stop recording"
              >
                ■ Stop
              </button>
            </div>
          )}

          {/* ── Transcribing (Whisper fallback) ───────────────────────────── */}
          {recordingState === 'transcribing' && (
            <div className="voice-modal__transcribing" data-testid="transcribing-spinner">
              <div className="voice-modal__spinner" role="status" aria-label="Transcribing" />
              <p className="voice-modal__transcribing-label">Transcribing…</p>
            </div>
          )}

          {/* ── Review / Saving ───────────────────────────────────────────── */}
          {isReview && (
            <div className="voice-modal__review">
              <div className="voice-modal__field">
                <label className="voice-modal__label" htmlFor="voice-template">
                  Note type
                </label>
                <select
                  id="voice-template"
                  className="voice-modal__select"
                  value={template}
                  onChange={e => dispatch({ type: 'SET_TEMPLATE', template: e.target.value })}
                  data-testid="template-select"
                  disabled={recordingState === 'saving'}
                >
                  {TEMPLATES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>

              <div className="voice-modal__field">
                <label className="voice-modal__label" htmlFor="voice-transcript">
                  Transcript
                </label>
                <textarea
                  id="voice-transcript"
                  className="voice-modal__textarea"
                  value={transcript}
                  onChange={e => dispatch({ type: 'SET_TRANSCRIPT', text: e.target.value })}
                  disabled={recordingState === 'saving'}
                  rows={6}
                  placeholder="Your voice transcript will appear here…"
                  data-testid="transcript-textarea"
                />
              </div>

              {error && (
                <p className="voice-modal__error" role="alert" data-testid="voice-error">
                  {error}
                </p>
              )}

              <div className="voice-modal__actions">
                <button
                  className="voice-modal__btn voice-modal__btn--secondary"
                  onClick={handleDiscard}
                  disabled={recordingState === 'saving'}
                  data-testid="discard-btn"
                >
                  Discard
                </button>
                <button
                  className="voice-modal__btn voice-modal__btn--primary"
                  onClick={handleSave}
                  disabled={recordingState === 'saving' || !transcript.trim()}
                  data-testid="save-btn"
                >
                  {recordingState === 'saving' ? 'Saving…' : 'Save Note'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
