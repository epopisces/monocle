import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap } from '@codemirror/view'
import { defaultKeymap, indentWithTab } from '@codemirror/commands'
import { markdown } from '@codemirror/lang-markdown'
import { yaml as yamlLang } from '@codemirror/lang-yaml'

import {
  getNoteHistoryDiff,
  getNoteHistoryVersion,
  listNoteHistory,
  putNote,
  restoreNoteHistoryVersion,
  type Note,
  type NoteHistoryDiffResponse,
  type NoteHistoryEntry,
} from '../../api/notes'
import { getArchivedSourceDownloadUrl, isTextSourceRecord, type SourceLink } from '../../api/ingest'
import { approveNote } from '../../api/review'
import { ApiError } from '../../api/client'
import { useDebouncedCallback } from '../../hooks/useDebounce'
import { buildRawDoc, splitFrontmatter, parseFrontmatter } from '../../utils/yamlUtils'
import FormEditor, { type TemplateSchema } from './FormEditor'
import './NoteEditor.css'

// ── Types ─────────────────────────────────────────────────────────

type EditorMode = 'yaml' | 'preview' | 'form'

interface NoteEditorProps {
  note: Note
  templates: TemplateSchema[]
  onSaved: (updated: Note) => void
  onNavigate: (path: string) => void
  allNotes: { file_path: string; title: string }[]
  onOpenSource?: (sourceId: string) => void
}

// ── Toast utility ─────────────────────────────────────────────────

interface ToastState {
  message: string
  kind: 'error' | 'success'
}

// ── Main component ────────────────────────────────────────────────

export default function NoteEditor({
  note,
  templates,
  onSaved,
  onNavigate,
  allNotes,
  onOpenSource,
}: NoteEditorProps) {
  const [mode, setMode] = useState<EditorMode>('yaml')
  const [localNote, setLocalNote] = useState<Note>(note)
  const [isDirty, setIsDirty] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [toast, setToast] = useState<ToastState | null>(null)
  const [historyEntries, setHistoryEntries] = useState<NoteHistoryEntry[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [selectedHistoryTimestamp, setSelectedHistoryTimestamp] = useState<string | null>(null)
  const [selectedHistoryNote, setSelectedHistoryNote] = useState<Note | null>(null)
  const [historyDiff, setHistoryDiff] = useState<NoteHistoryDiffResponse | null>(null)
  const [isReverting, setIsReverting] = useState(false)

  const editorContainerRef = useRef<HTMLDivElement>(null)
  const editorViewRef = useRef<EditorView | null>(null)
  const historyRequestIdRef = useRef(0)
  // Track if content changes are coming from the editor (not external load)
  const externalUpdateRef = useRef(false)

  // Compute raw document from localNote for YAML mode
  const computeRaw = useCallback((n: Note) => {
    const meta = (n.metadata ?? {}) as Record<string, unknown>
    const { title: _t, ...restMeta } = meta
    return buildRawDoc(n.title, restMeta, n.body)
  }, [])

  // ── Save logic ─────────────────────────────────────────────────

  const saveNote = useCallback(
    async (noteToSave: Note): Promise<boolean> => {
      setIsSaving(true)
      try {
        const saved = await putNote(noteToSave.file_path, {
          title: noteToSave.title,
          body: noteToSave.body,
          metadata: noteToSave.metadata!,
          if_mtime: noteToSave.mtime ?? undefined,
        })
        setLocalNote(saved)
        setIsDirty(false)
        onSaved(saved)
        return true
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          setToast({ message: 'Save conflict — this note was modified elsewhere. Reload to see the latest version.', kind: 'error' })
        } else {
          setToast({ message: `Save failed: ${(err as Error).message}`, kind: 'error' })
        }
        return false
      } finally {
        setIsSaving(false)
      }
    },
    [onSaved],
  )

  const debouncedSave = useDebouncedCallback(saveNote, 2000)

  const loadHistory = useCallback(async (filePath: string) => {
    const requestId = historyRequestIdRef.current + 1
    historyRequestIdRef.current = requestId
    setHistoryLoading(true)
    setHistoryError(null)
    setHistoryEntries([])
    try {
      const entries = await listNoteHistory(filePath)
      if (requestId !== historyRequestIdRef.current) return
      setHistoryEntries(entries)
    } catch (err) {
      if (requestId !== historyRequestIdRef.current) return
      setHistoryError(String((err as Error)?.message ?? 'Failed to load history'))
      setHistoryEntries([])
    } finally {
      if (requestId !== historyRequestIdRef.current) return
      setHistoryLoading(false)
    }
  }, [])

  // Cancel any pending debounced saves on unmount
  useEffect(() => {
    return () => {
      debouncedSave.cancel()
    }
  }, [debouncedSave])

  // ── Re-sync localNote when the note prop changes (new note selected) ──

  useEffect(() => {
    // Cancel any pending auto-save from the previous note
    debouncedSave.cancel()
    setLocalNote(note)
    setIsDirty(false)
    setMode('yaml')
    setSelectedHistoryTimestamp(null)
    setSelectedHistoryNote(null)
    setHistoryDiff(null)
    // Update the CodeMirror editor content
    if (editorViewRef.current) {
      externalUpdateRef.current = true
      const raw = computeRaw(note)
      const view = editorViewRef.current
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: raw },
      })
      externalUpdateRef.current = false
    }
    loadHistory(note.file_path)
  }, [note, computeRaw, debouncedSave])

  useEffect(() => {
    if (!selectedHistoryTimestamp) {
      setSelectedHistoryNote(null)
      setHistoryDiff(null)
      return
    }

    const historyTimestamp = selectedHistoryTimestamp

    let cancelled = false
    async function loadHistoryDetail() {
      try {
        const [version, diff] = await Promise.all([
          getNoteHistoryVersion(localNote.file_path, historyTimestamp),
          getNoteHistoryDiff(localNote.file_path, historyTimestamp),
        ])
        if (cancelled) return
        setSelectedHistoryNote(version.note)
        setHistoryDiff(diff)
      } catch (err) {
        if (cancelled) return
        setToast({ message: `History load failed: ${(err as Error).message}`, kind: 'error' })
        setSelectedHistoryNote(null)
        setHistoryDiff(null)
      }
    }

    loadHistoryDetail()
    return () => { cancelled = true }
  }, [localNote.file_path, selectedHistoryTimestamp])

  // ── CodeMirror setup ──────────────────────────────────────────

  useEffect(() => {
    if (!editorContainerRef.current) return
    if (editorViewRef.current) return

    const raw = computeRaw(note)
    const updateListener = EditorView.updateListener.of(update => {
      if (update.docChanged && !externalUpdateRef.current) {
        const newText = update.state.doc.toString()
        // Parse raw doc back to note
        const { frontmatter, body } = splitFrontmatter(newText)
        const parsedMeta = parseFrontmatter(frontmatter)
        const { title: _t, ...metaWithoutTitle } = parsedMeta

        setLocalNote(prev => {
          const title = typeof parsedMeta.title === 'string' ? parsedMeta.title : prev.title
          const updated: Note = {
            ...prev,
            title,
            body,
            metadata: {
              ...prev.metadata,
              ...metaWithoutTitle,
            } as Note['metadata'],
          }
          setIsDirty(true)
          debouncedSave(updated)
          return updated
        })
      }
    })

    const isMac = navigator.platform.toUpperCase().includes('MAC')
    const saveKey = isMac ? 'Mod-s' : 'Ctrl-s'

    const view = new EditorView({
      parent: editorContainerRef.current,
      state: EditorState.create({
        doc: raw,
        extensions: [
          markdown(),
          yamlLang(),
          keymap.of([
            {
              key: saveKey,
              run: (_v) => {
                // Immediate save — cancel any pending debounced save first
                debouncedSave.cancel()
                const text = _v.state.doc.toString()
                const { frontmatter, body } = splitFrontmatter(text)
                const parsedMeta = parseFrontmatter(frontmatter)
                const { title: _title, ...metaWithoutTitle } = parsedMeta
                setLocalNote(prev => {
                  const title = typeof parsedMeta.title === 'string' ? parsedMeta.title : prev.title
                  const updated: Note = {
                    ...prev,
                    title,
                    body,
                    metadata: { ...prev.metadata, ...metaWithoutTitle } as Note['metadata'],
                  }
                  saveNote(updated)
                  return updated
                })
                return true
              },
            },
            ...defaultKeymap,
            indentWithTab,
          ]),
          updateListener,
          EditorView.theme({
            '&': { height: '100%', fontSize: 'var(--text-sm)' },
            '.cm-scroller': { fontFamily: 'var(--font-mono)', overflow: 'auto' },
            '.cm-content': { padding: '8px 0' },
          }),
        ],
      }),
    })

    editorViewRef.current = view
    return () => {
      view.destroy()
      editorViewRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Approve handler ───────────────────────────────────────────

  const handleApprove = async () => {
    try {
      debouncedSave.cancel()
      // Flush any unsaved edits first so the version on disk is current when approved.
      if (isDirty) {
        const saved = await saveNote(localNote)
        if (!saved) return  // save failed; toast already shown by saveNote
      }
      await approveNote(localNote.file_path)
      const updated: Note = {
        ...localNote,
        metadata: {
          ...localNote.metadata,
          review_status: 'approved' as const,
        } as Note['metadata'],
      }
      setLocalNote(updated)
      onSaved(updated)
      setToast({ message: 'Note approved', kind: 'success' })
    } catch (err) {
      setToast({ message: `Approve failed: ${(err as Error).message}`, kind: 'error' })
    }
  }

  // ── Wikilink handler in preview mode ──────────────────────────

  const handleWikilinkClick = useCallback(
    (linkText: string) => {
      const lower = linkText.toLowerCase()
      const match = allNotes.find(
        n => n.title.toLowerCase() === lower || n.file_path.toLowerCase().includes(lower),
      )
      if (match) {
        onNavigate(match.file_path)
      } else {
        setToast({ message: `Note not found: "${linkText}"`, kind: 'error' })
      }
    },
    [allNotes, onNavigate],
  )

  // Pre-process body to convert [[wikilinks]] to anchor tags
  const processedBody = localNote.body.replace(
    /\[\[([^\]]+)\]\]/g,
    (_, linkText) => `[${linkText}](#wikilink:${encodeURIComponent(linkText)})`,
  )

  // ── Form mode save ─────────────────────────────────────────────

  const handleFormSave = () => {
    // Cancel any pending debounced save
    debouncedSave.cancel()
    saveNote(localNote)
  }

  const handleRevertHistoryVersion = async () => {
    if (!selectedHistoryTimestamp) return

    const message = isDirty
      ? 'You have unsaved changes. Reverting will discard them. Continue?'
      : 'Revert this document to the selected version?'
    if (!window.confirm(message)) return

    setIsReverting(true)
    debouncedSave.cancel()
    try {
      const restored = await restoreNoteHistoryVersion(localNote.file_path, selectedHistoryTimestamp, {
        if_mtime: localNote.mtime ?? undefined,
      })
      setLocalNote(restored)
      setIsDirty(false)
      onSaved(restored)
      setSelectedHistoryTimestamp(null)
      setSelectedHistoryNote(null)
      setHistoryDiff(null)
      await loadHistory(restored.file_path)
      setToast({ message: 'Document reverted to historical version', kind: 'success' })
    } catch (err) {
      const message = err instanceof ApiError && err.status === 409
        ? 'Revert conflict — this note was modified elsewhere. Reload to see the latest version.'
        : `Revert failed: ${(err as Error).message}`
      setToast({ message, kind: 'error' })
    } finally {
      setIsReverting(false)
    }
  }

  // ── Toast auto-dismiss ────────────────────────────────────────

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 5000)
    return () => clearTimeout(t)
  }, [toast])

  // ── Mode switch helpers ───────────────────────────────────────

  const switchMode = (next: EditorMode) => {
    if (next === 'yaml' && editorViewRef.current) {
      // Sync editor from localNote
      externalUpdateRef.current = true
      const raw = computeRaw(localNote)
      const view = editorViewRef.current
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: raw },
      })
      externalUpdateRef.current = false
    }
    setMode(next)
  }

  const isPending = localNote.metadata?.review_status === 'pending'
  const sourceLinks = ((((localNote.metadata ?? {}) as Record<string, unknown>).sources) as SourceLink[] | undefined) ?? []

  return (
    <div className="note-editor" data-testid="note-editor">
      {/* ── Toolbar ─────────────────────────────────────────────── */}
      <div className="note-editor__toolbar">
        <div className="note-editor__mode-toggle" role="group" aria-label="Editor mode">
          {(['yaml', 'preview', 'form'] as const).map(m => (
            <button
              key={m}
              className={`note-editor__mode-btn${mode === m ? ' note-editor__mode-btn--active' : ''}`}
              onClick={() => switchMode(m)}
              data-testid={`mode-btn-${m}`}
              aria-pressed={mode === m}
            >
              {m.charAt(0).toUpperCase() + m.slice(1)}
            </button>
          ))}
        </div>

        <span className="note-editor__path" title={localNote.file_path}>{localNote.file_path}</span>

        <div className="note-editor__toolbar-actions">
          {isSaving && <span className="note-editor__saving" data-testid="saving-indicator">Saving…</span>}
          {isDirty && !isSaving && (
            <button
              className="note-editor__save-now-btn"
              onClick={() => {
                debouncedSave.cancel()
                saveNote(localNote)
              }}
              data-testid="save-now-btn"
            >
              Save
            </button>
          )}
          {isPending && (
            <button
              className="note-editor__approve-btn"
              onClick={handleApprove}
              data-testid="approve-btn"
            >
              ✓ Approve
            </button>
          )}
        </div>
      </div>

      {sourceLinks.length > 0 && (
        <details className="note-editor__sources" data-testid="note-sources">
          <summary>Sources ({sourceLinks.length})</summary>
          <ul className="note-editor__sources-list">
            {sourceLinks.map(source => {
              const label = source.author ? `${source.source_name} - ${source.author}` : source.source_name
              return (
                <li key={source.source_id}>
                  {isTextSourceRecord(source) ? (
                    <button
                      type="button"
                      className="note-editor__source-link"
                      onClick={() => onOpenSource?.(source.source_id)}
                    >
                      {label}
                    </button>
                  ) : (
                    <a
                      className="note-editor__source-link"
                      href={getArchivedSourceDownloadUrl(source.source_id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {label}
                    </a>
                  )}
                </li>
              )
            })}
          </ul>
        </details>
      )}

      <details className="note-editor__history" data-testid="note-history">
        <summary>History ({historyEntries.length})</summary>
        {historyLoading && <p className="note-editor__history-muted">Loading history…</p>}
        {historyError && <p className="note-editor__history-error">{historyError}</p>}
        {!historyLoading && !historyError && historyEntries.length === 0 && (
          <p className="note-editor__history-muted">No previous versions yet.</p>
        )}
        {!historyLoading && historyEntries.length > 0 && (
          <div className="note-editor__history-grid">
            <div className="note-editor__history-list" data-testid="history-list">
              {historyEntries.map(entry => (
                <button
                  key={entry.timestamp}
                  type="button"
                  className={`note-editor__history-entry${selectedHistoryTimestamp === entry.timestamp ? ' note-editor__history-entry--active' : ''}`}
                  onClick={() => setSelectedHistoryTimestamp(entry.timestamp)}
                  data-testid={`history-entry-${entry.timestamp}`}
                >
                  <strong>{entry.timestamp}</strong>
                  <span>{entry.title ?? localNote.title}</span>
                  {entry.body_excerpt && <small>{entry.body_excerpt}</small>}
                </button>
              ))}
            </div>
            {selectedHistoryTimestamp && selectedHistoryNote && historyDiff && (
              <div className="note-editor__history-detail" data-testid="history-detail">
                <div className="note-editor__history-actions">
                  <span className="note-editor__history-label">Comparing {historyDiff.base_label} to {historyDiff.compare_label}</span>
                  <button
                    type="button"
                    className="note-editor__history-revert-btn"
                    onClick={handleRevertHistoryVersion}
                    disabled={isReverting}
                    data-testid="history-revert-btn"
                  >
                    {isReverting ? 'Reverting…' : 'Revert to this version'}
                  </button>
                </div>
                <div className="note-editor__history-diff" data-testid="history-diff">
                  {historyDiff.diff_preview.hunks.map((hunk, index) => (
                    <div key={`${hunk.section ?? index}-${index}`} className="note-editor__history-hunk">
                      <p>{hunk.section ?? 'change'}</p>
                      <div className="note-editor__history-columns">
                        <pre>{hunk.before ?? 'No content'}</pre>
                        <pre>{hunk.after ?? 'No content'}</pre>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="note-editor__history-preview">
                  <h3>{selectedHistoryNote.title}</h3>
                  <pre data-testid="history-version-body">{selectedHistoryNote.body}</pre>
                </div>
              </div>
            )}
          </div>
        )}
      </details>

      {/* ── Toast ───────────────────────────────────────────────── */}
      {toast && (
        <div
          className={`note-editor__toast note-editor__toast--${toast.kind}`}
          role="alert"
          data-testid="editor-toast"
        >
          {toast.message}
          <button onClick={() => setToast(null)} className="note-editor__toast-close" aria-label="Dismiss">✕</button>
        </div>
      )}

      {/* ── Editor area ────────────────────────────────────────── */}
      <div className="note-editor__body">
        {/* CodeMirror container — always mounted so editor state is preserved */}
        <div
          ref={editorContainerRef}
          className="note-editor__cm"
          style={{ display: mode === 'yaml' ? 'flex' : 'none' }}
          data-testid="codemirror-container"
        />

        {/* Preview mode */}
        {mode === 'preview' && (
          <div className="note-editor__preview" data-testid="preview-content">
            <h1 className="note-editor__preview-title">{localNote.title}</h1>
            <ReactMarkdown
              components={{
                a({ href, children }) {
                  if (href?.startsWith('#wikilink:')) {
                    const linkText = decodeURIComponent(href.slice('#wikilink:'.length))
                    return (
                      <a
                        href="#"
                        className="wikilink"
                        data-testid="wikilink"
                        onClick={e => {
                          e.preventDefault()
                          handleWikilinkClick(linkText)
                        }}
                      >
                        {children}
                      </a>
                    )
                  }
                  // Only allow http(s) URLs; render unsafe links as non-navigable text
                  const isAllowedUrl = /^https?:\/\//i.test(href ?? '')
                  if (!isAllowedUrl) {
                    return <span className="unsafe-link" title="Unsafe link (non-http)">{children}</span>
                  }
                return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
                },
              }}
            >
              {processedBody}
            </ReactMarkdown>
          </div>
        )}

        {/* Form mode */}
        {mode === 'form' && (
          <FormEditor
            note={localNote}
            templates={templates}
            onChange={updated => {
              setLocalNote(updated)
              setIsDirty(true)
              debouncedSave(updated)
            }}
            onSave={handleFormSave}
          />
        )}
      </div>
    </div>
  )
}
