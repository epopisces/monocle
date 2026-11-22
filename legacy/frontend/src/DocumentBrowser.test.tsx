import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor, within } from '@testing-library/react'
import { BrowserRouter, MemoryRouter } from 'react-router-dom'

// ── Mock CodeMirror ───────────────────────────────────────────────
// CodeMirror uses DOM APIs not available in jsdom; mock to a simple div
let mockEditorDocText = '---\ntitle: Test Note\n---\n\nBody text'
const mockPosAtCoords = vi.fn(() => null)

vi.mock('@codemirror/view', () => ({
  EditorView: class EditorView {
    dom = document.createElement('div')
    state = {
      doc: { toString: () => mockEditorDocText },
      selection: { main: { from: 0, to: 0 } },
    }
    constructor(config: { parent?: Element; state?: unknown }) {
      if (config.state) {
        this.state = config.state as typeof this.state
      }
      if (config.parent) config.parent.appendChild(this.dom)
    }
    posAtCoords(coords: { x: number; y: number }) {
      return mockPosAtCoords(coords)
    }
    dispatch() {}
    destroy() {}
    static updateListener = { of: vi.fn(() => ({})) }
    static theme = vi.fn(() => ({}))
    static lineWrapping = {}
  },
  keymap: { of: vi.fn(() => ({})) },
}))

vi.mock('@codemirror/state', () => ({
  EditorState: {
    create: vi.fn((config: { doc?: string }) => ({
      doc: { toString: () => String(config.doc ?? mockEditorDocText) },
      selection: { main: { from: 0, to: 0 } },
    })),
  },
}))

vi.mock('@codemirror/commands', () => ({
  defaultKeymap: [],
  indentWithTab: {},
}))

vi.mock('@codemirror/lang-markdown', () => ({ markdown: vi.fn(() => ({})) }))
vi.mock('@codemirror/lang-yaml', () => ({ yaml: vi.fn(() => ({})) }))

// ── Mock API calls ────────────────────────────────────────────────

const mockListNotes = vi.fn()
const mockGetNote = vi.fn()
const mockPutNote = vi.fn()
const mockPatchNote = vi.fn()
const mockDeleteNote = vi.fn()
const mockListTemplates = vi.fn()
const mockGetNoteBacklinks = vi.fn()
const mockListNoteHistory = vi.fn()
const mockGetNoteHistoryVersion = vi.fn()
const mockGetNoteHistoryDiff = vi.fn()
const mockRestoreNoteHistoryVersion = vi.fn()
const mockListArchivedSources = vi.fn()
const mockGetArchivedSource = vi.fn()
const mockGetArchivedSourceContent = vi.fn()

vi.mock('./api/notes', () => ({
  listNotes: (...args: unknown[]) => mockListNotes(...args),
  getNote: (...args: unknown[]) => mockGetNote(...args),
  putNote: (...args: unknown[]) => mockPutNote(...args),
  patchNote: (...args: unknown[]) => mockPatchNote(...args),
  deleteNote: (...args: unknown[]) => mockDeleteNote(...args),
  listTemplates: (...args: unknown[]) => mockListTemplates(...args),
  getNoteBacklinks: (...args: unknown[]) => mockGetNoteBacklinks(...args),
  listNoteHistory: (...args: unknown[]) => mockListNoteHistory(...args),
  getNoteHistoryVersion: (...args: unknown[]) => mockGetNoteHistoryVersion(...args),
  getNoteHistoryDiff: (...args: unknown[]) => mockGetNoteHistoryDiff(...args),
  restoreNoteHistoryVersion: (...args: unknown[]) => mockRestoreNoteHistoryVersion(...args),
}))

vi.mock('./api/ingest', () => ({
  listArchivedSources: (...args: unknown[]) => mockListArchivedSources(...args),
  getArchivedSource: (...args: unknown[]) => mockGetArchivedSource(...args),
  getArchivedSourceContent: (...args: unknown[]) => mockGetArchivedSourceContent(...args),
  getArchivedSourceDownloadUrl: (sourceId: string) => `/api/ingest/sources/${encodeURIComponent(sourceId)}/download`,
  isTextSourceRecord: (source: { kind: string; mime_type?: string | null }) => source.kind === 'text' || (source.mime_type ?? '').startsWith('text/'),
}))

vi.mock('./api/review', () => ({
  approveNote: vi.fn().mockResolvedValue({ file_path: 'people/alice.md', review_status: 'approved' }),
}))

// ── Test data ─────────────────────────────────────────────────────

const MOCK_NOTES = [
  {
    file_path: 'people/alice.md',
    title: 'Alice Smith',
    type: 'person_note',
    domain: 'work',
    confidence: 0.9,
    review_status: 'approved',
  },
  {
    file_path: 'people/bob.md',
    title: 'Bob Jones',
    type: 'person_note',
    domain: 'work',
    confidence: 0.8,
    review_status: 'pending',
  },
  {
    file_path: 'work/decision.md',
    title: 'Team size decision',
    type: 'decision',
    domain: 'work',
    confidence: 0.85,
    review_status: 'approved',
  },
]

const MOCK_NOTE_FULL = {
  file_path: 'people/alice.md',
  title: 'Alice Smith',
  body: 'I met Alice today.',
  mtime: 1234567890,
  metadata: {
    type: 'person_note',
    template: 'person',
    domain: 'work',
    source: 'web',
    confidence: 0.9,
    review_status: 'approved',
    people: ['Alice Smith'],
    tags: [],
    action_items: [],
    links: [],
  },
}

const MOCK_BACKLINKS = [
  { source: 'work/decision.md', relation: 'mentioned-in', context: 'Alice was mentioned here.' },
]

const MOCK_ARCHIVED_SOURCE = {
  source_id: 'src_1',
  session_id: 'ing_1',
  kind: 'text',
  status: 'ready',
  source_name: 'capture.txt',
  mime_type: 'text/plain',
  archive_path: 'src_1/payload',
  checksum_sha256: 'abc',
  captured_at: '2026-04-24T00:00:00Z',
  byte_size: 12,
  provenance: {},
}

const MOCK_HISTORY_TIMESTAMP = '2026-04-23T00-00-00.000Z'
const MOCK_HISTORY_ENTRIES = [
  {
    timestamp: MOCK_HISTORY_TIMESTAMP,
    title: 'Alice Smith',
    updated: '2026-04-23T00:00:00Z',
    body_excerpt: 'Historical body',
    byte_size: 42,
  },
]

const mockOnAddGroundingNew = vi.fn()
const mockOnAddGroundingExisting = vi.fn()

beforeEach(() => {
  mockEditorDocText = '---\ntitle: Test Note\n---\n\nBody text'
  mockPosAtCoords.mockReset()
  mockPosAtCoords.mockReturnValue(null)
  mockListNoteHistory.mockResolvedValue(MOCK_HISTORY_ENTRIES)
  mockGetNoteHistoryVersion.mockResolvedValue({
    timestamp: MOCK_HISTORY_TIMESTAMP,
    note: { ...MOCK_NOTE_FULL, body: 'Historical body' },
  })
  mockGetNoteHistoryDiff.mockResolvedValue({
    file_path: 'people/alice.md',
    base_timestamp: MOCK_HISTORY_TIMESTAMP,
    compare_timestamp: null,
    base_label: MOCK_HISTORY_TIMESTAMP,
    compare_label: 'Current',
    diff_preview: {
      kind: 'history',
      before_excerpt: 'Historical body',
      after_excerpt: 'I met Alice today.',
      hunks: [{ section: 'body', before: 'Historical body', after: 'I met Alice today.' }],
    },
  })
  mockRestoreNoteHistoryVersion.mockResolvedValue({ ...MOCK_NOTE_FULL, body: 'Historical body', mtime: 7777 })
})

// ── DocumentBrowserScreen tests ───────────────────────────────────

import DocumentBrowserScreen from './components/DocumentBrowser/DocumentBrowserScreen'
import FileTree from './components/DocumentBrowser/FileTree'
import BacklinksPanel from './components/DocumentBrowser/BacklinksPanel'

describe('FileTree', () => {
  it('renders empty state when no notes', () => {
    render(<FileTree notes={[]} selectedPath={null} onSelect={vi.fn()} />)
    expect(screen.getByTestId('file-tree')).toBeInTheDocument()
    expect(screen.getByText('No notes found')).toBeInTheDocument()
  })

  it('renders folder groups and files', () => {
    render(
      <FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />,
    )
    // Should have folder nodes for 'people' and 'work'
    const folders = screen.getAllByTestId('tree-folder')
    expect(folders.length).toBeGreaterThan(0)
    // Should have file nodes
    const files = screen.getAllByTestId('tree-file')
    expect(files.length).toBe(3)
  })

  it('calls onSelect when a file is clicked', () => {
    const onSelect = vi.fn()
    render(
      <FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={onSelect} />,
    )
    const files = screen.getAllByTestId('tree-file')
    fireEvent.click(files[0])
    expect(onSelect).toHaveBeenCalledWith(expect.stringContaining('.md'))
  })

  it('marks active file with aria-current', () => {
    render(
      <FileTree
        notes={MOCK_NOTES as never}
        selectedPath="people/alice.md"
        onSelect={vi.fn()}
      />,
    )
    const active = screen.getByRole('button', { current: 'page' })
    expect(active).toBeInTheDocument()
  })

  it('marks file rows as draggable for chat context drag-and-drop', () => {
    render(
      <FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />,
    )
    const files = screen.getAllByTestId('tree-file')
    expect(files[0]).toHaveAttribute('draggable', 'true')
  })

  it('shows pending badge on notes with pending review_status', () => {
    render(
      <FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />,
    )
    const badges = screen.getAllByLabelText('pending review')
    expect(badges.length).toBe(1)
  })

  it('expand/collapse folder on click', () => {
    render(
      <FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />,
    )
    const folderBtn = screen.getAllByTestId('tree-folder')[0].querySelector('button')!
    // Folder starts expanded (depth 0 = open by default)
    expect(folderBtn.getAttribute('aria-expanded')).toBe('true')
    fireEvent.click(folderBtn)
    expect(folderBtn.getAttribute('aria-expanded')).toBe('false')
  })
})

describe('FileTree — context menu', () => {
  beforeEach(() => {
    mockPatchNote.mockResolvedValue({ file_path: 'people/alice.md', title: 'Alice Renamed' })
    mockDeleteNote.mockResolvedValue(undefined)
  })
  afterEach(() => vi.clearAllMocks())

  it('shows context menu on right-click of a file', () => {
    render(<FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />)
    const files = screen.getAllByTestId('tree-file')
    fireEvent.contextMenu(files[0])
    expect(screen.getByTestId('context-menu')).toBeInTheDocument()
    expect(screen.getByTestId('context-edit')).toBeInTheDocument()
    expect(screen.getByTestId('context-rename')).toBeInTheDocument()
    expect(screen.getByTestId('context-delete')).toBeInTheDocument()
  })

  it('Edit calls onSelect and closes menu', () => {
    const onSelect = vi.fn()
    render(<FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={onSelect} />)
    const files = screen.getAllByTestId('tree-file')
    fireEvent.contextMenu(files[0])
    fireEvent.click(screen.getByTestId('context-edit'))
    expect(onSelect).toHaveBeenCalledWith(expect.stringContaining('.md'))
    expect(screen.queryByTestId('context-menu')).toBeNull()
  })

  it('Rename shows inline input pre-filled with note title', () => {
    render(<FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />)
    const files = screen.getAllByTestId('tree-file')
    fireEvent.contextMenu(files[0])
    fireEvent.click(screen.getByTestId('context-rename'))
    const input = screen.getByTestId('rename-input') as HTMLInputElement
    expect(input).toBeInTheDocument()
    expect(input.value).toBeTruthy()
  })

  it('Rename commits on Enter and calls patchNote', async () => {
    const onRenamed = vi.fn()
    render(
      <FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} onRenamed={onRenamed} />,
    )
    const files = screen.getAllByTestId('tree-file')
    fireEvent.contextMenu(files[0])
    fireEvent.click(screen.getByTestId('context-rename'))
    const input = screen.getByTestId('rename-input')
    fireEvent.change(input, { target: { value: 'New Title' } })
    await act(async () => { fireEvent.keyDown(input, { key: 'Enter' }) })
    await waitFor(() => expect(mockPatchNote).toHaveBeenCalledWith(
      expect.stringContaining('.md'),
      { updates: { title: 'New Title' } },
    ))
    expect(onRenamed).toHaveBeenCalledWith(expect.stringContaining('.md'), 'New Title')
  })

  it('Rename cancels on Escape', () => {
    render(<FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />)
    const files = screen.getAllByTestId('tree-file')
    fireEvent.contextMenu(files[0])
    fireEvent.click(screen.getByTestId('context-rename'))
    const input = screen.getByTestId('rename-input')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByTestId('rename-input')).toBeNull()
  })

  it('Delete shows inline confirm', () => {
    render(<FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />)
    const files = screen.getAllByTestId('tree-file')
    fireEvent.contextMenu(files[0])
    fireEvent.click(screen.getByTestId('context-delete'))
    expect(screen.getByTestId('delete-confirm-btn')).toBeInTheDocument()
    expect(screen.getByTestId('delete-cancel-btn')).toBeInTheDocument()
  })

  it('Delete confirms and calls deleteNote', async () => {
    const onDeleted = vi.fn()
    render(
      <FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} onDeleted={onDeleted} />,
    )
    const files = screen.getAllByTestId('tree-file')
    fireEvent.contextMenu(files[0])
    fireEvent.click(screen.getByTestId('context-delete'))
    await act(async () => { fireEvent.click(screen.getByTestId('delete-confirm-btn')) })
    await waitFor(() => expect(mockDeleteNote).toHaveBeenCalledWith(expect.stringContaining('.md')))
    expect(onDeleted).toHaveBeenCalledWith(expect.stringContaining('.md'))
  })

  it('Delete cancel hides confirm row', () => {
    render(<FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />)
    const files = screen.getAllByTestId('tree-file')
    fireEvent.contextMenu(files[0])
    fireEvent.click(screen.getByTestId('context-delete'))
    fireEvent.click(screen.getByTestId('delete-cancel-btn'))
    expect(screen.queryByTestId('delete-confirm-btn')).toBeNull()
  })

  it('menu closes on outside mousedown', () => {
    render(<FileTree notes={MOCK_NOTES as never} selectedPath={null} onSelect={vi.fn()} />)
    const files = screen.getAllByTestId('tree-file')
    fireEvent.contextMenu(files[0])
    expect(screen.getByTestId('context-menu')).toBeInTheDocument()
    fireEvent.mouseDown(document.body)
    expect(screen.queryByTestId('context-menu')).toBeNull()
  })
})

describe('BacklinksPanel', () => {
  beforeEach(() => {
    mockGetNoteBacklinks.mockResolvedValue(MOCK_BACKLINKS)
  })

  it('shows loading state initially', async () => {
    mockGetNoteBacklinks.mockReturnValue(new Promise(() => {})) // never resolves
    render(<BacklinksPanel path="people/alice.md" onNavigate={vi.fn()} />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('renders backlinks after loading', async () => {
    render(<BacklinksPanel path="people/alice.md" onNavigate={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('backlinks-list')).toBeInTheDocument())
    expect(screen.getByText('work/decision.md')).toBeInTheDocument()
    expect(screen.getByText(/mentioned-in/)).toBeInTheDocument()
  })

  it('shows empty message when no backlinks', async () => {
    mockGetNoteBacklinks.mockResolvedValue([])
    render(<BacklinksPanel path="people/alice.md" onNavigate={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('No incoming links')).toBeInTheDocument())
  })

  it('calls onNavigate on double-click', async () => {
    const onNavigate = vi.fn()
    render(<BacklinksPanel path="people/alice.md" onNavigate={onNavigate} />)
    await waitFor(() => expect(screen.getByTestId('backlinks-list')).toBeInTheDocument())
    const item = screen.getByTestId('backlink-item')
    fireEvent.doubleClick(item)
    expect(onNavigate).toHaveBeenCalledWith('work/decision.md')
  })
})

describe('DocumentBrowserScreen', () => {
  beforeEach(() => {
    mockListNotes.mockResolvedValue({ items: MOCK_NOTES, total: 3, offset: 0, limit: 500 })
    mockListTemplates.mockResolvedValue([])
    mockGetNote.mockResolvedValue(MOCK_NOTE_FULL)
    mockGetNoteBacklinks.mockResolvedValue([])
    mockListArchivedSources.mockResolvedValue([MOCK_ARCHIVED_SOURCE])
    mockGetArchivedSource.mockResolvedValue(MOCK_ARCHIVED_SOURCE)
    mockGetArchivedSourceContent.mockResolvedValue({ source: MOCK_ARCHIVED_SOURCE, text: 'Captured source body.', truncated: false })
  })

  it('renders file tree after loading', async () => {
    render(
      <MemoryRouter initialEntries={['/docs']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockListNotes).toHaveBeenCalled())
    expect(screen.getByTestId('doc-browser')).toBeInTheDocument()
  })

  it('shows empty state when no note selected', async () => {
    render(
      <MemoryRouter initialEntries={['/docs']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByTestId('doc-browser-empty')).toBeInTheDocument())
  })

  it('loads and shows note editor when path is in URL', async () => {
    render(
      <MemoryRouter initialEntries={['/docs?path=people/alice.md']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockGetNote).toHaveBeenCalledWith('people/alice.md'))
    await waitFor(() => expect(screen.getByTestId('note-editor')).toBeInTheDocument())
  })

  it('shows error state when listNotes fails', async () => {
    mockListNotes.mockRejectedValue(new Error('API error'))
    render(
      <MemoryRouter initialEntries={['/docs']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByTestId('notes-list-error')).toBeInTheDocument())
    expect(screen.getByText(/Failed to load vault/)).toBeInTheDocument()
  })

  it('shows loading state initially when fetching notes', async () => {
    mockListNotes.mockReturnValue(new Promise(() => {})) // never resolves
    render(
      <MemoryRouter initialEntries={['/docs']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByText('Loading notes…')).toBeInTheDocument())
  })

  it('opens archived text sources in the document browser', async () => {
    render(
      <MemoryRouter initialEntries={['/docs']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )

    const drawer = await screen.findByTestId('archived-sources-drawer')
    fireEvent.click(within(drawer).getByText(/Archived Sources/i))
    fireEvent.click(await within(drawer).findByRole('button', { name: 'capture.txt' }))

    await waitFor(() => expect(mockGetArchivedSource).toHaveBeenCalledWith('src_1'))
    expect(await screen.findByTestId('source-viewer')).toBeInTheDocument()
    expect(await screen.findByTestId('source-viewer-content')).toHaveTextContent('Captured source body.')
  })

  it('opens non-text archived sources in a new window', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    mockListArchivedSources.mockResolvedValue([
      {
        ...MOCK_ARCHIVED_SOURCE,
        source_id: 'src_bin',
        source_name: 'recording.wav',
        kind: 'audio',
        mime_type: 'audio/wav',
      },
    ])

    render(
      <MemoryRouter initialEntries={['/docs']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )

    const drawer = await screen.findByTestId('archived-sources-drawer')
    fireEvent.click(within(drawer).getByText(/Archived Sources/i))
    fireEvent.click(await within(drawer).findByRole('button', { name: 'recording.wav' }))

    expect(openSpy).toHaveBeenCalledWith('/api/ingest/sources/src_bin/download', '_blank', 'noopener,noreferrer')
    expect(mockGetArchivedSource).not.toHaveBeenCalledWith('src_bin')
    openSpy.mockRestore()
  })
})

// Helper to test NoteEditor in isolation
import NoteEditor from './components/DocumentBrowser/NoteEditor'

describe('NoteEditor — isolated', () => {
  beforeEach(() => {
    mockOnAddGroundingNew.mockReset()
    mockOnAddGroundingExisting.mockReset()
  })

  it('renders mode buttons', () => {
    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    expect(screen.getByTestId('mode-btn-yaml')).toBeInTheDocument()
    expect(screen.getByTestId('mode-btn-preview')).toBeInTheDocument()
    expect(screen.getByTestId('mode-btn-form')).toBeInTheDocument()
  })

  it('shows approve button when review_status is pending', () => {
    const pendingNote = {
      ...MOCK_NOTE_FULL,
      metadata: { ...MOCK_NOTE_FULL.metadata, review_status: 'pending' as const },
    }
    render(
      <BrowserRouter>
        <NoteEditor
          note={pendingNote as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    expect(screen.getByTestId('approve-btn')).toBeInTheDocument()
  })

  it('does NOT show approve button when review_status is approved', () => {
    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    expect(screen.queryByTestId('approve-btn')).toBeNull()
  })

  it('renders collapsed sources for notes with provenance links', () => {
    const noteWithSources = {
      ...MOCK_NOTE_FULL,
      metadata: {
        ...MOCK_NOTE_FULL.metadata,
        sources: [{
          source_id: 'src_1',
          source_name: 'capture.txt',
          archive_path: 'src_1/payload',
          kind: 'text',
          mime_type: 'text/plain',
        }],
      },
    }

    const onOpenSource = vi.fn()
    render(
      <BrowserRouter>
        <NoteEditor
          note={noteWithSources as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
          onOpenSource={onOpenSource}
        />
      </BrowserRouter>,
    )

    const sources = screen.getByTestId('note-sources')
    fireEvent.click(within(sources).getByText(/Sources \(1\)/i))
    fireEvent.click(within(sources).getByRole('button', { name: 'capture.txt' }))
    expect(onOpenSource).toHaveBeenCalledWith('src_1')
  })

  it('shows CodeMirror container in YAML mode by default', () => {
    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    const cm = screen.getByTestId('codemirror-container')
    expect(cm).toBeInTheDocument()
    // In YAML mode, cm container is visible
    expect(cm.style.display).not.toBe('none')
  })

  it('switches to preview mode on button click', async () => {
    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    await act(async () => {
      fireEvent.click(screen.getByTestId('mode-btn-preview'))
    })
    expect(screen.getByTestId('preview-content')).toBeInTheDocument()
  })

  it('switches to form mode on button click', async () => {
    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    await act(async () => {
      fireEvent.click(screen.getByTestId('mode-btn-form'))
    })
    expect(screen.getByTestId('form-editor')).toBeInTheDocument()
  })

  it('calls putNote on save', async () => {
    mockPutNote.mockResolvedValue({ ...MOCK_NOTE_FULL, mtime: 9999 })
    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    // Switch to form mode and click Save to trigger a save
    await act(async () => {
      fireEvent.click(screen.getByTestId('mode-btn-form'))
    })
    await act(async () => {
      fireEvent.click(screen.getByTestId('form-save-btn'))
    })
    await waitFor(() => expect(mockPutNote).toHaveBeenCalled())
  })

  it('shows 409 conflict toast on save conflict', async () => {
    const { ApiError } = await import('./api/client')
    mockPutNote.mockRejectedValue(new ApiError(409, 'Conflict'))
    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    await act(async () => {
      fireEvent.click(screen.getByTestId('mode-btn-form'))
    })
    await act(async () => {
      fireEvent.click(screen.getByTestId('form-save-btn'))
    })
    await waitFor(() => expect(screen.getByTestId('editor-toast')).toBeInTheDocument())
    expect(screen.getByTestId('editor-toast').textContent).toMatch(/conflict/i)
  })

  it('loads history details when a retained version is selected', async () => {
    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )

    fireEvent.click(await screen.findByTestId('history-entry-2026-04-23T00-00-00.000Z'))

    await waitFor(() => expect(mockGetNoteHistoryVersion).toHaveBeenCalledWith('people/alice.md', MOCK_HISTORY_TIMESTAMP))
    await waitFor(() => expect(screen.getByTestId('history-diff')).toBeInTheDocument())
    expect(screen.getByTestId('history-version-body')).toHaveTextContent('Historical body')
  })

  it('reverts to the selected retained version', async () => {
    const onSaved = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={onSaved}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )

    fireEvent.click(await screen.findByTestId('history-entry-2026-04-23T00-00-00.000Z'))
    await waitFor(() => expect(screen.getByTestId('history-revert-btn')).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(screen.getByTestId('history-revert-btn'))
    })

    await waitFor(() => expect(mockRestoreNoteHistoryVersion).toHaveBeenCalledWith(
      'people/alice.md',
      MOCK_HISTORY_TIMESTAMP,
      { if_mtime: MOCK_NOTE_FULL.mtime },
    ))
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ body: 'Historical body' }))
    confirmSpy.mockRestore()
  })

  it('ignores stale history list responses after switching notes', async () => {
    let resolveFirst: ((value: typeof MOCK_HISTORY_ENTRIES) => void) | undefined
    const secondEntries = [{
      timestamp: '2026-04-24T00-00-00.000Z',
      title: 'Bob Jones',
      updated: '2026-04-24T00:00:00Z',
      body_excerpt: 'Bob history',
      byte_size: 21,
    }]

    mockListNoteHistory
      .mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve }))
      .mockResolvedValueOnce(secondEntries)

    const { rerender } = render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )

    const bobNote = {
      ...MOCK_NOTE_FULL,
      file_path: 'people/bob.md',
      title: 'Bob Jones',
      body: 'Bob body',
      mtime: 4444,
    }

    rerender(
      <BrowserRouter>
        <NoteEditor
          note={bobNote as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )

    resolveFirst?.(MOCK_HISTORY_ENTRIES)

    await waitFor(() => expect(screen.getByTestId('history-entry-2026-04-24T00-00-00.000Z')).toBeInTheDocument())
    expect(screen.queryByTestId(`history-entry-${MOCK_HISTORY_TIMESTAMP}`)).toBeNull()
    expect(screen.getByText('Bob Jones')).toBeInTheDocument()
  })

  it('opens add-to-chat actions for preview content and sends section context to a new chat', async () => {
    const sectionedNote = {
      ...MOCK_NOTE_FULL,
      body: '# Intro\n\nAlpha sentence.\n\n## Target Section\n\nTarget sentence. Another detail.',
    }

    render(
      <BrowserRouter>
        <NoteEditor
          note={sectionedNote as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
          onAddToNewChat={mockOnAddGroundingNew}
          onAddToExistingChat={mockOnAddGroundingExisting}
        />
      </BrowserRouter>,
    )

    await act(async () => {
      fireEvent.click(screen.getByTestId('mode-btn-preview'))
    })

    fireEvent.contextMenu(screen.getByRole('heading', { level: 2, name: 'Target Section' }))
    expect(screen.getByTestId('note-context-menu')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('note-context-section-new'))
    expect(mockOnAddGroundingNew).toHaveBeenCalledWith(expect.objectContaining({
      scope: 'section',
      text: expect.stringContaining('## Target Section'),
    }))
  })

  it('uses the YAML right-click position instead of a stale editor selection for add-to-chat context', async () => {
    const sectionedNote = {
      ...MOCK_NOTE_FULL,
      body: '# Intro\n\nAlpha sentence.\n\n## Target Section\n\nTarget sentence. Another detail.',
    }
    const rawDoc = [
      '---',
      'title: Alice Smith',
      'type: person_note',
      'template: person',
      'domain: work',
      'source: web',
      'confidence: 0.9',
      'review_status: approved',
      'people:',
      '  - Alice Smith',
      'tags: []',
      'action_items: []',
      'links: []',
      '---',
      '',
      '# Intro',
      '',
      'Alpha sentence.',
      '',
      '## Target Section',
      '',
      'Target sentence. Another detail.',
    ].join('\n')
    mockPosAtCoords.mockReturnValue(rawDoc.indexOf('Target sentence'))

    render(
      <BrowserRouter>
        <NoteEditor
          note={sectionedNote as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
          onAddToNewChat={mockOnAddGroundingNew}
          onAddToExistingChat={mockOnAddGroundingExisting}
        />
      </BrowserRouter>,
    )

    await act(async () => { await Promise.resolve() })

    fireEvent.contextMenu(screen.getByTestId('codemirror-container'), { clientX: 120, clientY: 80 })
    fireEvent.click(screen.getByTestId('note-context-section-new'))

    expect(mockPosAtCoords).toHaveBeenCalledWith({ x: 120, y: 80 })
    expect(mockOnAddGroundingNew).toHaveBeenCalledWith(expect.objectContaining({
      scope: 'section',
      text: expect.stringContaining('## Target Section'),
    }))
  })

  it('does not block the native context menu when add-to-chat handlers are absent', async () => {
    const preventDefaultSpy = vi.spyOn(Event.prototype, 'preventDefault')

    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )

    await act(async () => { await Promise.resolve() })

    fireEvent.contextMenu(screen.getByTestId('codemirror-container'))

    expect(preventDefaultSpy).not.toHaveBeenCalled()
    expect(screen.queryByTestId('note-context-menu')).toBeNull()

    preventDefaultSpy.mockRestore()
  })

  it('shows selection-specific add-to-chat actions in form mode', async () => {
    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
          onAddToNewChat={mockOnAddGroundingNew}
          onAddToExistingChat={mockOnAddGroundingExisting}
        />
      </BrowserRouter>,
    )

    await act(async () => {
      fireEvent.click(screen.getByTestId('mode-btn-form'))
    })

    const titleField = screen.getByTestId('field-title') as HTMLInputElement
    titleField.focus()
    titleField.setSelectionRange(0, 5)
    fireEvent.contextMenu(titleField)

    expect(screen.getByTestId('note-context-selection-existing')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('note-context-selection-existing'))
    expect(mockOnAddGroundingExisting).toHaveBeenCalledWith(expect.objectContaining({ scope: 'selection' }))
  })
})

// ── Additional BacklinksPanel tests ───────────────────────────────

describe('BacklinksPanel — error state', () => {
  it('shows error message when backlinks fetch fails', async () => {
    mockGetNoteBacklinks.mockRejectedValue(new Error('Network failure'))
    render(<BacklinksPanel path="people/alice.md" onNavigate={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('Network failure')).toBeInTheDocument())
  })
})

// ── Additional FileTree tests ─────────────────────────────────────

describe('FileTree — root-level notes', () => {
  it('renders a note at the vault root without creating a folder node', () => {
    const rootNotes = [
      {
        file_path: 'readme.md',
        title: 'Readme',
        type: 'other' as const,
        domain: 'work',
        confidence: 0.8,
        review_status: 'approved' as const,
      },
    ]
    render(<FileTree notes={rootNotes as never} selectedPath={null} onSelect={vi.fn()} />)
    const files = screen.getAllByTestId('tree-file')
    expect(files).toHaveLength(1)
    expect(screen.queryByTestId('tree-folder')).toBeNull()
  })
})

// ── Additional DocumentBrowserScreen tests ────────────────────────

describe('DocumentBrowserScreen — wikilink resolution', () => {
  beforeEach(() => {
    mockListNotes.mockResolvedValue({ items: MOCK_NOTES, total: 3, offset: 0, limit: 500 })
    mockListTemplates.mockResolvedValue([])
    mockGetNote.mockResolvedValue(MOCK_NOTE_FULL)
    mockGetNoteBacklinks.mockResolvedValue([])
  })

  it('navigates to note when ?wikilink= resolves to a known note', async () => {
    render(
      <MemoryRouter initialEntries={['/docs?wikilink=Alice%20Smith']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockGetNote).toHaveBeenCalledWith('people/alice.md'))
  })

  it('shows toast when ?wikilink= query does not resolve to any note', async () => {
    render(
      <MemoryRouter initialEntries={['/docs?wikilink=NonExistentNote']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockListNotes).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByTestId('wiki-toast')).toBeInTheDocument())
    expect(screen.getByTestId('wiki-toast').textContent).toMatch(/not found/i)
  })

  it('removes unresolved ?wikilink= from URL after showing toast', async () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/docs?wikilink=NonExistentNote']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockListNotes).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByTestId('wiki-toast')).toBeInTheDocument())
    // URL should be cleaned to remove the unresolved wikilink param
    expect(window.location.search).toBe('')
  })

  it('updates file tree title after a note is saved', async () => {
    render(
      <MemoryRouter initialEntries={['/docs?path=people/alice.md']}>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByTestId('note-editor')).toBeInTheDocument())

    // Verify initial title is visible in the file tree
    const initialFiles = screen.getAllByTestId('tree-file').filter(f => f.textContent?.includes('Alice Smith'))
    expect(initialFiles.length).toBeGreaterThan(0)

    // Mock putNote to return an updated title
    mockPutNote.mockResolvedValue({ ...MOCK_NOTE_FULL, title: 'Alice Updated' })

    await act(async () => { fireEvent.click(screen.getByTestId('mode-btn-form')) })
    await act(async () => { fireEvent.click(screen.getByTestId('form-save-btn')) })
    await waitFor(() => expect(mockPutNote).toHaveBeenCalled())

    // File tree should reflect the new title
    await waitFor(() => {
      const updatedFiles = screen.getAllByTestId('tree-file').filter(f => f.textContent?.includes('Alice Updated'))
      expect(updatedFiles.length).toBeGreaterThan(0)
    })
  })
})

// ── Additional NoteEditor tests: Ctrl+S ──────────────────────────

import { keymap } from '@codemirror/view'
import { approveNote } from './api/review'

describe('NoteEditor — Ctrl+S save shortcut', () => {
  it('registers a Ctrl-s / Mod-s keymap handler that triggers an immediate save', async () => {
    mockPutNote.mockResolvedValue({ ...MOCK_NOTE_FULL, mtime: 9999 })
    // Clear any call history from previous tests
    ;(keymap.of as unknown as ReturnType<typeof vi.fn>).mockClear()

    render(
      <BrowserRouter>
        <NoteEditor
          note={MOCK_NOTE_FULL as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )

    // Retrieve all handlers that were registered via keymap.of during mount
    const keymapIfSpy = keymap.of as unknown as ReturnType<typeof vi.fn>
    const allHandlers = (keymapIfSpy.mock.calls as Array<Array<Array<{ key: string; run: (v: unknown) => boolean }>>>)
      .flatMap(c => c[0])
    const saveHandler = allHandlers.find(h => h.key === 'Ctrl-s' || h.key === 'Mod-s')
    expect(saveHandler).toBeDefined()

    // Invoke the handler with a mock view (editor content parsed by the handler itself)
    await act(async () => {
      saveHandler!.run({
        state: { doc: { toString: () => '---\ntitle: Test Note\n---\n\nSaved body' } },
      })
    })
    await waitFor(() => expect(mockPutNote).toHaveBeenCalled())
  })
})

// ── Additional NoteEditor tests: wikilink preview navigation ──────

describe('NoteEditor — wikilink navigation in preview mode', () => {
  it('clicking a resolved [[wikilink]] calls onNavigate with the matching file path', async () => {
    const onNavigate = vi.fn()
    render(
      <BrowserRouter>
        <NoteEditor
          note={{ ...MOCK_NOTE_FULL, body: 'See [[Alice Smith]]' } as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={onNavigate}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    await act(async () => { fireEvent.click(screen.getByTestId('mode-btn-preview')) })
    await waitFor(() => expect(screen.getByTestId('wikilink')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('wikilink'))
    expect(onNavigate).toHaveBeenCalledWith('people/alice.md')
  })

  it('clicking an unresolvable [[wikilink]] shows a "not found" toast', async () => {
    render(
      <BrowserRouter>
        <NoteEditor
          note={{ ...MOCK_NOTE_FULL, body: 'See [[Unknown Note]]' } as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    await act(async () => { fireEvent.click(screen.getByTestId('mode-btn-preview')) })
    await waitFor(() => expect(screen.getByTestId('wikilink')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('wikilink'))
    await waitFor(() => expect(screen.getByTestId('editor-toast')).toBeInTheDocument())
    expect(screen.getByTestId('editor-toast').textContent).toMatch(/not found/i)
  })

  it('renders unsafe (non-http) links as non-clickable text without target="_blank"', async () => {
    render(
      <BrowserRouter>
        <NoteEditor
          note={{
            ...MOCK_NOTE_FULL,
            body: 'See [local link](file:///home/user/file.md) and [valid link](https://example.com)',
          } as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    await act(async () => { fireEvent.click(screen.getByTestId('mode-btn-preview')) })
    await waitFor(() => expect(screen.getByTestId('preview-content')).toBeInTheDocument())
    
    // Unsafe link should be a non-clickable span with the unsafe-link class
    const unsafeLink = screen.queryByText('local link')
    expect(unsafeLink?.tagName).toBe('SPAN')
    expect(unsafeLink).toHaveClass('unsafe-link')
    expect(unsafeLink?.getAttribute('href')).toBeNull()
    
    // Safe link should be an anchor with target="_blank"
    const safeLink = screen.getByText('valid link')
    expect(safeLink.tagName).toBe('A')
    expect(safeLink.getAttribute('href')).toBe('https://example.com')
    expect(safeLink.getAttribute('target')).toBe('_blank')
    expect(safeLink.getAttribute('rel')).toBe('noopener noreferrer')
  })
})

// ── Additional NoteEditor tests: approve-while-dirty ─────────────

describe('NoteEditor — approve flushes dirty edits', () => {
  beforeEach(() => {
    vi.mocked(approveNote).mockClear()
    mockPutNote.mockReset()
    mockPutNote.mockResolvedValue({ ...MOCK_NOTE_FULL, mtime: 9999 })
  })

  it('calls putNote before approveNote when the note has unsaved changes', async () => {
    const pendingNote = {
      ...MOCK_NOTE_FULL,
      metadata: { ...MOCK_NOTE_FULL.metadata, review_status: 'pending' as const },
    }
    render(
      <BrowserRouter>
        <NoteEditor
          note={pendingNote as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    // Make the note dirty by changing the title in form mode
    await act(async () => { fireEvent.click(screen.getByTestId('mode-btn-form')) })
    await act(async () => {
      fireEvent.change(screen.getByTestId('field-title'), { target: { value: 'Alice Updated' } })
    })
    // Approve — should save first then approve
    await act(async () => { fireEvent.click(screen.getByTestId('approve-btn')) })

    await waitFor(() => expect(mockPutNote).toHaveBeenCalled())
    await waitFor(() => expect(approveNote).toHaveBeenCalled())
  })

  it('does not call putNote on approve when the note has no unsaved changes', async () => {
    const pendingNote = {
      ...MOCK_NOTE_FULL,
      metadata: { ...MOCK_NOTE_FULL.metadata, review_status: 'pending' as const },
    }
    render(
      <BrowserRouter>
        <NoteEditor
          note={pendingNote as never}
          templates={[]}
          onSaved={vi.fn()}
          onNavigate={vi.fn()}
          allNotes={MOCK_NOTES}
        />
      </BrowserRouter>,
    )
    // Click approve with no changes (isDirty = false)
    await act(async () => { fireEvent.click(screen.getByTestId('approve-btn')) })

    await waitFor(() => expect(approveNote).toHaveBeenCalled())
    expect(mockPutNote).not.toHaveBeenCalled()
  })
})
