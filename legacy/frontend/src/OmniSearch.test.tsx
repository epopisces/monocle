import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OmniSearch from './components/layout/OmniSearch'

// ── Module mocks ───────────────────────────────────────────────────────────────────────────────────────────────

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const mockOmniSearch = vi.fn()
vi.mock('./api/search', () => ({
  omniSearch: (...args: unknown[]) => mockOmniSearch(...args),
  semanticSearch: vi.fn(),
  keywordSearch: vi.fn(),
}))

// ── Test data ──────────────────────────────────────────────────────────────────────────────────────────────────

const FILENAME_RESULT = {
  file_path: 'work/search_test_note.md',
  title: 'Search Test Note',
  excerpt: 'search_test_note',
  match_location: 'filename' as const,
}

const FRONTMATTER_RESULT = {
  file_path: 'work/some_note.md',
  title: 'Important Tag Note',
  excerpt: 'Important Tag Note | work',
  match_location: 'frontmatter' as const,
}

const BODY_RESULT = {
  file_path: 'work/body_note.md',
  title: 'Body Note',
  excerpt: '…contains the query in the text…',
  match_location: 'body' as const,
}

// ── Helpers ─────────────────────────────────────────────────────────────────────────────────────────────────────

function renderOmniSearch() {
  return render(
    <MemoryRouter>
      <OmniSearch />
    </MemoryRouter>,
  )
}

/** Advance fake timers past the debounce, then flush resulting microtasks. */
async function flushDebounce() {
  await act(async () => {
    vi.runAllTimers()
  })
  // Flush promise resolution from mockResolvedValue
  await act(async () => {})
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => {
    resolve = res
  })
  return { promise, resolve }
}

// ── Tests ──────────────────────────────────────────────────────────────────────────────────────────────────────

describe('OmniSearch — render', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders the search input', () => {
    renderOmniSearch()
    expect(screen.getByTestId('omni-search-input')).toBeInTheDocument()
  })

  it('dropdown is not visible initially', () => {
    renderOmniSearch()
    expect(screen.queryByTestId('omni-search-dropdown')).toBeNull()
  })
})

describe('OmniSearch — Ctrl+E shortcut', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('focuses the input when Ctrl+E is pressed', () => {
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.keyDown(window, { key: 'e', ctrlKey: true })
    expect(document.activeElement).toBe(input)
  })
})

describe('OmniSearch — search behaviour', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not call omniSearch for fewer than 3 characters', async () => {
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: 'ab' } })
    await flushDebounce()
    expect(mockOmniSearch).not.toHaveBeenCalled()
  })

  it('calls omniSearch after debounce for ≥3 chars', async () => {
    mockOmniSearch.mockResolvedValue([FILENAME_RESULT])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: 'abc' } })
    // Before debounce fires
    expect(mockOmniSearch).not.toHaveBeenCalled()
    await flushDebounce()
    expect(mockOmniSearch).toHaveBeenCalledWith({ q: 'abc', limit: 20 })
  })

  it('trims the query before the 3-character trigger and request', async () => {
    mockOmniSearch.mockResolvedValue([FILENAME_RESULT])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: '  ab  ' } })
    await flushDebounce()
    expect(mockOmniSearch).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: '  abc  ' } })
    await flushDebounce()
    expect(mockOmniSearch).toHaveBeenCalledWith({ q: 'abc', limit: 20 })
  })

  it('shows results in dropdown after search', async () => {
    mockOmniSearch.mockResolvedValue([FILENAME_RESULT])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: 'search' } })
    await flushDebounce()
    expect(screen.getByTestId('omni-search-dropdown')).toBeInTheDocument()
    expect(screen.getAllByTestId('omni-result').length).toBeGreaterThan(0)
  })

  it('always shows semantic option when query ≥ 3 chars', async () => {
    mockOmniSearch.mockResolvedValue([])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: 'xyz' } })
    await flushDebounce()
    expect(screen.getByTestId('omni-search-dropdown')).toBeInTheDocument()
    expect(screen.getByTestId('omni-semantic-btn')).toBeInTheDocument()
  })
})

describe('OmniSearch — navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('navigates to /docs when a result is clicked', async () => {
    mockOmniSearch.mockResolvedValue([FILENAME_RESULT])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: 'search' } })
    await flushDebounce()
    fireEvent.click(screen.getAllByTestId('omni-result')[0])
    expect(mockNavigate).toHaveBeenCalledWith(
      `/docs?path=${encodeURIComponent(FILENAME_RESULT.file_path)}`
    )
  })

  it('navigates to /search with semantic mode when semantic option clicked', async () => {
    mockOmniSearch.mockResolvedValue([FILENAME_RESULT])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: '  hello  ' } })
    await flushDebounce()
    fireEvent.click(screen.getByTestId('omni-semantic-btn'))
    expect(mockNavigate).toHaveBeenCalledWith(
      `/search?q=${encodeURIComponent('hello')}&mode=semantic`
    )
  })
})

describe('OmniSearch — keyboard navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('closes dropdown on Escape', async () => {
    mockOmniSearch.mockResolvedValue([FILENAME_RESULT])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: 'search' } })
    await flushDebounce()
    expect(screen.getByTestId('omni-search-dropdown')).toBeInTheDocument()
    input.focus()
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Escape' })
    })
    expect(screen.queryByTestId('omni-search-dropdown')).toBeNull()
    expect(document.activeElement).not.toBe(input)
  })

  it('navigates with Enter on first result', async () => {
    mockOmniSearch.mockResolvedValue([FILENAME_RESULT, BODY_RESULT])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: 'search' } })
    await flushDebounce()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(mockNavigate).toHaveBeenCalledWith(
      `/docs?path=${encodeURIComponent(FILENAME_RESULT.file_path)}`
    )
  })

  it('groups results by match_location with group label headers', async () => {
    mockOmniSearch.mockResolvedValue([FILENAME_RESULT, FRONTMATTER_RESULT, BODY_RESULT])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: 'note' } })
    await flushDebounce()
    // All three results should be present
    expect(screen.getAllByTestId('omni-result').length).toBe(3)
    // Group labels
    expect(screen.getByText('In filename')).toBeInTheDocument()
    expect(screen.getByText('In title / tags')).toBeInTheDocument()
    expect(screen.getByText('In body')).toBeInTheDocument()
  })

  it('uses bucket-local option ids for aria-activedescendant', async () => {
    mockOmniSearch.mockResolvedValue([FILENAME_RESULT, FRONTMATTER_RESULT, BODY_RESULT])
    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')
    fireEvent.change(input, { target: { value: 'note' } })
    await flushDebounce()

    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(input).toHaveAttribute('aria-activedescendant', 'omni-option-frontmatter-0')
  })

  it('ignores stale results from slower older queries', async () => {
    const slow = deferred<typeof FILENAME_RESULT[]>()
    const fast = deferred<typeof BODY_RESULT[]>()
    mockOmniSearch.mockImplementation(({ q }: { q: string }) => {
      if (q === 'alpha') return slow.promise
      if (q === 'beta') return fast.promise
      return Promise.resolve([])
    })

    renderOmniSearch()
    const input = screen.getByTestId('omni-search-input')

    fireEvent.change(input, { target: { value: 'alpha' } })
    await flushDebounce()
    fireEvent.change(input, { target: { value: 'beta' } })
    await flushDebounce()

    await act(async () => {
      fast.resolve([BODY_RESULT])
    })
    expect(screen.getByText('Body Note')).toBeInTheDocument()

    await act(async () => {
      slow.resolve([FILENAME_RESULT])
    })
    expect(screen.queryByText('Search Test Note')).toBeNull()
    expect(screen.getByText('Body Note')).toBeInTheDocument()
  })
})
