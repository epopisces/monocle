import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { BrowserRouter, MemoryRouter } from 'react-router-dom'

// ── Mock CodeMirror ───────────────────────────────────────────────
// CodeMirror uses DOM APIs not available in jsdom; mock to a simple div
vi.mock('@codemirror/view', () => ({
  EditorView: class EditorView {
    dom = document.createElement('div')
    state = { doc: { toString: () => '---\ntitle: Test Note\n---\n\nBody text' } }
    constructor(config: { parent?: Element; state?: unknown }) {
      if (config.parent) config.parent.appendChild(this.dom)
    }
    dispatch() {}
    destroy() {}
    static updateListener = { of: vi.fn(() => ({})) }
    static theme = vi.fn(() => ({}))
  },
  keymap: { of: vi.fn(() => ({})) },
}))

vi.mock('@codemirror/state', () => ({
  EditorState: {
    create: vi.fn(() => ({ doc: { toString: () => '' } })),
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
const mockListTemplates = vi.fn()
const mockGetNoteBacklinks = vi.fn()

vi.mock('./api/notes', () => ({
  listNotes: (...args: unknown[]) => mockListNotes(...args),
  getNote: (...args: unknown[]) => mockGetNote(...args),
  putNote: (...args: unknown[]) => mockPutNote(...args),
  listTemplates: (...args: unknown[]) => mockListTemplates(...args),
  getNoteBacklinks: (...args: unknown[]) => mockGetNoteBacklinks(...args),
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
})

describe('NoteEditor', () => {
  it('shows mode toggle buttons', async () => {
    render(
      <MemoryRouter>
        <DocumentBrowserScreen />
      </MemoryRouter>,
    )
    // Load a note
    mockListNotes.mockResolvedValue({ items: MOCK_NOTES, total: 3 })
    mockGetNote.mockResolvedValue(MOCK_NOTE_FULL)
    mockGetNoteBacklinks.mockResolvedValue([])
    mockListTemplates.mockResolvedValue([])
  })
})

// Helper to test NoteEditor in isolation
import NoteEditor from './components/DocumentBrowser/NoteEditor'

describe('NoteEditor — isolated', () => {
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
})
