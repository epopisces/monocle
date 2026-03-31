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
const mockPatchNote = vi.fn()
const mockDeleteNote = vi.fn()
const mockListTemplates = vi.fn()
const mockGetNoteBacklinks = vi.fn()

vi.mock('./api/notes', () => ({
  listNotes: (...args: unknown[]) => mockListNotes(...args),
  getNote: (...args: unknown[]) => mockGetNote(...args),
  putNote: (...args: unknown[]) => mockPutNote(...args),
  patchNote: (...args: unknown[]) => mockPatchNote(...args),
  deleteNote: (...args: unknown[]) => mockDeleteNote(...args),
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
