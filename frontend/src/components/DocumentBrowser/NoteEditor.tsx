import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap } from '@codemirror/view'
import { defaultKeymap, indentWithTab } from '@codemirror/commands'
import { markdown } from '@codemirror/lang-markdown'
import { yaml as yamlLang } from '@codemirror/lang-yaml'

import type { Note } from '../../api/notes'
import { putNote } from '../../api/notes'
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
}: NoteEditorProps) {
  const [mode, setMode] = useState<EditorMode>('yaml')
  const [localNote, setLocalNote] = useState<Note>(note)
  const [isDirty, setIsDirty] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [toast, setToast] = useState<ToastState | null>(null)

  const editorContainerRef = useRef<HTMLDivElement>(null)
  const editorViewRef = useRef<EditorView | null>(null)
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
  }, [note, computeRaw, debouncedSave])

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
                  const safe = /^https?:\/\//i.test(href ?? '') ? href : '#'
                return <a href={safe} target="_blank" rel="noopener noreferrer">{children}</a>
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
