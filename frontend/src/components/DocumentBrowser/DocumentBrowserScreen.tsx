import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { listNotes, getNote, listTemplates, type Note, type NoteRef } from '../../api/notes'
import {
  getArchivedSource,
  getArchivedSourceContent,
  getArchivedSourceDownloadUrl,
  isTextSourceRecord,
  listArchivedSources,
  type ArchivedSourceContentResponse,
  type SourceRecord,
} from '../../api/ingest'
import type { TemplateSchema } from './FormEditor'
import FileTree from './FileTree'
import NoteEditor from './NoteEditor'
import BacklinksPanel from './BacklinksPanel'
import './DocumentBrowserScreen.css'

export default function DocumentBrowserScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [notes, setNotes] = useState<NoteRef[]>([])
  const [sources, setSources] = useState<SourceRecord[]>([])
  const [templates, setTemplates] = useState<TemplateSchema[]>([])
  const [selectedPath, setSelectedPath] = useState<string | null>(searchParams.get('path'))
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(searchParams.get('source'))
  const [openNote, setOpenNote] = useState<Note | null>(null)
  const [openSource, setOpenSource] = useState<SourceRecord | null>(null)
  const [sourceContent, setSourceContent] = useState<ArchivedSourceContentResponse | null>(null)
  const [loadingSource, setLoadingSource] = useState(false)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [loadingNote, setLoadingNote] = useState(false)
  const [noteError, setNoteError] = useState<string | null>(null)
  const [loadingNotes, setLoadingNotes] = useState(true)
  const [notesError, setNotesError] = useState<string | null>(null)
  const [wikiToast, setWikiToast] = useState<string | null>(null)

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

    listArchivedSources({ limit: 200 })
      .then(items => setSources(items))
      .catch(err => {
        console.error('[DocumentBrowser] listArchivedSources error:', err)
        setSources([])
      })
  }, [])

  useEffect(() => {
    const pathParam = searchParams.get('path')
    const sourceParam = searchParams.get('source')
    const wikilinkParam = searchParams.get('wikilink')

    if (sourceParam) {
      setSelectedSourceId(sourceParam)
      setSelectedPath(null)
    } else if (pathParam) {
      setSelectedPath(pathParam)
      setSelectedSourceId(null)
    } else if (wikilinkParam && notes.length > 0) {
      const lower = wikilinkParam.toLowerCase()
      const match = notes.find(
        n => n.title.toLowerCase() === lower || n.file_path.toLowerCase().includes(lower),
      )
      if (match) {
        setSelectedPath(match.file_path)
        setSelectedSourceId(null)
        setSearchParams({ path: match.file_path }, { replace: true })
      } else {
        setWikiToast(`Note not found: "${wikilinkParam}"`)
        setSearchParams({}, { replace: true })
      }
    }
  }, [searchParams, notes, setSearchParams])

  useEffect(() => {
    if (!wikiToast) return
    const t = setTimeout(() => setWikiToast(null), 4000)
    return () => clearTimeout(t)
  }, [wikiToast])

  useEffect(() => {
    if (!selectedPath || selectedSourceId) {
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
  }, [selectedPath, selectedSourceId])

  useEffect(() => {
    if (!selectedSourceId) {
      setOpenSource(null)
      setSourceContent(null)
      setSourceError(null)
      return
    }

    const sourceId: string = selectedSourceId

    let cancelled = false
    async function loadSource() {
      setLoadingSource(true)
      setSourceError(null)
      try {
        const source = await getArchivedSource(sourceId)
        if (cancelled) return
        setOpenSource(source)
        if (isTextSourceRecord(source)) {
          const content = await getArchivedSourceContent(sourceId)
          if (cancelled) return
          setSourceContent(content)
        } else {
          setSourceContent(null)
        }
      } catch (err) {
        if (!cancelled) setSourceError(String((err as Error)?.message ?? 'Failed to load source'))
      } finally {
        if (!cancelled) setLoadingSource(false)
      }
    }

    loadSource()
    return () => { cancelled = true }
  }, [selectedSourceId])

  const handleSelectNote = useCallback((path: string) => {
    setSelectedPath(path)
    setSelectedSourceId(null)
    setSearchParams({ path }, { replace: true })
  }, [setSearchParams])

  const handleOpenSource = useCallback((sourceId: string) => {
    const source = sources.find(item => item.source_id === sourceId)
    if (source && !isTextSourceRecord(source)) {
      window.open(getArchivedSourceDownloadUrl(sourceId), '_blank', 'noopener,noreferrer')
      return
    }
    setSelectedSourceId(sourceId)
    setSelectedPath(null)
    setSearchParams({ source: sourceId }, { replace: true })
  }, [setSearchParams, sources])

  const handleNavigate = useCallback((path: string) => {
    handleSelectNote(path)
  }, [handleSelectNote])

  const handleSaved = useCallback((updated: Note) => {
    setOpenNote(updated)
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

  const handleDeleted = useCallback((path: string) => {
    setNotes(prev => prev.filter(n => n.file_path !== path))
    if (selectedPath === path) {
      setSelectedPath(null)
      setOpenNote(null)
      setSearchParams({}, { replace: true })
    }
  }, [selectedPath, setSearchParams])

  const handleRenamed = useCallback((path: string, newTitle: string) => {
    setNotes(prev => prev.map(n => n.file_path === path ? { ...n, title: newTitle } : n))
    setOpenNote(prev => prev?.file_path === path ? { ...prev, title: newTitle } : prev)
  }, [])

  return (
    <div className="doc-browser" data-testid="doc-browser">
      {wikiToast && (
        <div className="doc-browser__toast" role="alert" data-testid="wiki-toast">
          {wikiToast}
        </div>
      )}
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
          <>
            <FileTree
              notes={notes}
              selectedPath={selectedPath}
              onSelect={handleSelectNote}
              onDeleted={handleDeleted}
              onRenamed={handleRenamed}
            />
            {sources.length > 0 && (
              <details className="doc-browser__sources-drawer" data-testid="archived-sources-drawer">
                <summary>Archived Sources ({sources.length})</summary>
                <ul className="doc-browser__sources-list">
                  {sources.map(source => (
                    <li key={source.source_id}>
                      <button type="button" onClick={() => handleOpenSource(source.source_id)}>
                        {source.source_name}
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </aside>

      <div className="doc-browser__main">
        {!selectedPath && !selectedSourceId && (
          <div className="doc-browser__empty" data-testid="doc-browser-empty">
            <span className="doc-browser__empty-icon">📄</span>
            <p>Select a note from the vault</p>
          </div>
        )}

        {selectedSourceId && loadingSource && (
          <div className="doc-browser__loading" data-testid="source-viewer-loading">
            Loading source…
          </div>
        )}

        {selectedSourceId && sourceError && (
          <div className="doc-browser__error" data-testid="source-viewer-error">
            {sourceError}
          </div>
        )}

        {openSource && !loadingSource && !sourceError && (
          <section className="doc-browser__source-viewer" data-testid="source-viewer">
            <div className="doc-browser__source-header">
              <div>
                <h2>{openSource.source_name}</h2>
                <p>{openSource.kind}{openSource.mime_type ? ` · ${openSource.mime_type}` : ''}</p>
              </div>
              <a href={getArchivedSourceDownloadUrl(openSource.source_id)} target="_blank" rel="noreferrer">Open source file</a>
            </div>
            {sourceContent ? (
              <pre className="doc-browser__source-content" data-testid="source-viewer-content">{sourceContent.text}</pre>
            ) : (
              <p className="doc-browser__source-muted">This archived source is not text-previewable in the document browser.</p>
            )}
          </section>
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
              onOpenSource={handleOpenSource}
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
