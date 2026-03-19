import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { listNotes, getNote, listTemplates, type Note, type NoteRef } from '../../api/notes'
import type { TemplateSchema } from './FormEditor'
import FileTree from './FileTree'
import NoteEditor from './NoteEditor'
import BacklinksPanel from './BacklinksPanel'
import './DocumentBrowserScreen.css'

export default function DocumentBrowserScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [notes, setNotes] = useState<NoteRef[]>([])
  const [templates, setTemplates] = useState<TemplateSchema[]>([])
  const [selectedPath, setSelectedPath] = useState<string | null>(
    searchParams.get('path'),
  )
  const [openNote, setOpenNote] = useState<Note | null>(null)
  const [loadingNote, setLoadingNote] = useState(false)
  const [noteError, setNoteError] = useState<string | null>(null)
  const [loadingNotes, setLoadingNotes] = useState(true)
  const [notesError, setNotesError] = useState<string | null>(null)
  const [wikiToast, setWikiToast] = useState<string | null>(null)

  // Load note list + templates on mount
  useEffect(() => {
    setLoadingNotes(true)
    setNotesError(null)
    listNotes({ limit: 500 })
      .then(page => setNotes(page.items))
      .catch(err => {
        const errorMsg = String(err?.message ?? 'Failed to load notes')
        console.error('[DocumentBrowser] listNotes error:', err)
        setNotesError(errorMsg)
        setNotes([])
      })
      .finally(() => setLoadingNotes(false))

    listTemplates()
      .then(schemata => setTemplates(schemata as unknown as TemplateSchema[]))
      .catch(err => {
        console.error('[DocumentBrowser] listTemplates error:', err)
        setTemplates([])
      })
  }, [])

  // If URL has ?path= or ?wikilink=, resolve them
  useEffect(() => {
    const pathParam = searchParams.get('path')
    const wikilinkParam = searchParams.get('wikilink')

    if (pathParam) {
      setSelectedPath(pathParam)
    } else if (wikilinkParam && notes.length > 0) {
      const lower = wikilinkParam.toLowerCase()
      const match = notes.find(
        n => n.title.toLowerCase() === lower || n.file_path.toLowerCase().includes(lower),
      )
      if (match) {
        setSelectedPath(match.file_path)
        setSearchParams({ path: match.file_path }, { replace: true })
      } else {
        setWikiToast(`Note not found: "${wikilinkParam}"`)
      }
    }
  }, [searchParams, notes, setSearchParams])

  // Auto-dismiss wikilink resolution toast
  useEffect(() => {
    if (!wikiToast) return
    const t = setTimeout(() => setWikiToast(null), 4000)
    return () => clearTimeout(t)
  }, [wikiToast])

  // Load note content when selectedPath changes
  useEffect(() => {
    if (!selectedPath) {
      setOpenNote(null)
      return
    }
    let cancelled = false
    setLoadingNote(true)
    setNoteError(null)
    getNote(selectedPath)
      .then(n => {
        if (!cancelled) setOpenNote(n)
      })
      .catch(err => {
        if (!cancelled) setNoteError(String(err?.message ?? 'Failed to load note'))
      })
      .finally(() => {
        if (!cancelled) setLoadingNote(false)
      })
    return () => { cancelled = true }
  }, [selectedPath])

  const handleSelectNote = useCallback((path: string) => {
    setSelectedPath(path)
    setSearchParams({ path }, { replace: true })
  }, [setSearchParams])

  const handleNavigate = useCallback((path: string) => {
    handleSelectNote(path)
  }, [handleSelectNote])

  const handleSaved = useCallback((updated: Note) => {
    setOpenNote(updated)
    // Refresh note list entry
    setNotes(prev =>
      prev.map(n =>
        n.file_path === updated.file_path
          ? {
              ...n,
              title: updated.title,
              type: updated.metadata?.type ?? n.type,
              review_status: updated.metadata?.review_status ?? n.review_status,
            }
          : n,
      ),
    )
  }, [])

  return (
    <div className="doc-browser" data-testid="doc-browser">
      {wikiToast && (
        <div className="doc-browser__toast" role="alert" data-testid="wiki-toast">
          {wikiToast}
        </div>
      )}
      {/* ── Left: file tree ─────────────────────────────────── */}
      <aside className="doc-browser__sidebar">
        <div className="doc-browser__sidebar-header">
          <span className="doc-browser__sidebar-title">Vault</span>
        </div>
        {loadingNotes && (
          <div style={{ padding: '1rem', fontSize: '0.875rem', color: '#aaa' }}>
            Loading notes…
          </div>
        )}
        {notesError && (
          <div
            data-testid="notes-list-error"
            style={{
              padding: '1rem',
              fontSize: '0.875rem',
              color: '#ff6b6b',
              borderTop: '1px solid #444',
            }}
          >
            <p style={{ margin: '0 0 0.5rem 0', fontWeight: 500 }}>Failed to load vault</p>
            <p style={{ margin: 0, fontSize: '0.8125rem', opacity: 0.9 }}>{notesError}</p>
          </div>
        )}
        {!loadingNotes && !notesError && (
          <FileTree
            notes={notes}
            selectedPath={selectedPath}
            onSelect={handleSelectNote}
          />
        )}
      </aside>

      {/* ── Right: editor + backlinks ─────────────────────── */}
      <div className="doc-browser__main">
        {!selectedPath && (
          <div className="doc-browser__empty" data-testid="doc-browser-empty">
            <span className="doc-browser__empty-icon">📄</span>
            <p>Select a note from the vault</p>
          </div>
        )}

        {selectedPath && loadingNote && (
          <div className="doc-browser__loading" data-testid="doc-browser-loading">
            Loading…
          </div>
        )}

        {selectedPath && noteError && (
          <div className="doc-browser__error" data-testid="doc-browser-error">
            {noteError}
          </div>
        )}

        {openNote && !loadingNote && !noteError && (
          <div className="doc-browser__editor-pane">
            <NoteEditor
              note={openNote}
              templates={templates}
              onSaved={handleSaved}
              onNavigate={handleNavigate}
              allNotes={notes}
            />
            <BacklinksPanel
              path={openNote.file_path}
              onNavigate={handleNavigate}
            />
          </div>
        )}
      </div>
    </div>
  )
}
