import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import SearchScreen from './components/Search/SearchScreen'

// ── Mock API ──────────────────────────────────────────────────────

const mockSemanticSearch = vi.fn()
const mockKeywordSearch = vi.fn()
const mockApproveNote = vi.fn()

vi.mock('./api/search', () => ({
  semanticSearch: (...args: unknown[]) => mockSemanticSearch(...args),
  keywordSearch: (...args: unknown[]) => mockKeywordSearch(...args),
}))

vi.mock('./api/review', () => ({
  approveNote: (...args: unknown[]) => mockApproveNote(...args),
}))

// Reset call counts between tests so `not.toHaveBeenCalled()` only checks the current test
beforeEach(() => { vi.clearAllMocks() })

// ── Test data ─────────────────────────────────────────────────────

const SEMANTIC_RESULTS = [
  {
    chunk_id: 'abc-1',
    file_path: 'people/alice.md',
    score: 0.87,
    text: 'Alice is a software engineer at Acme.',
    metadata: {},
  },
  {
    chunk_id: 'abc-2',
    file_path: 'work/meeting.md',
    score: 0.72,
    text: 'We discussed the roadmap in the meeting.',
    metadata: {},
  },
]

const KEYWORD_RESULTS = [
  { file_path: 'people/alice.md', title: 'Alice Smith', excerpt: 'Alice is a software engineer.' },
  { file_path: 'work/notes.md', title: 'Work notes', excerpt: 'Notes about work.' },
]

function renderSearch() {
  return render(
    <MemoryRouter>
      <SearchScreen />
    </MemoryRouter>,
  )
}

// ── Tests ─────────────────────────────────────────────────────────

describe('SearchScreen — layout', () => {
  it('renders search input and submit button', () => {
    renderSearch()
    expect(screen.getByTestId('search-input')).toBeInTheDocument()
    expect(screen.getByTestId('search-btn')).toBeInTheDocument()
  })

  it('renders mode toggle with Semantic and Keyword buttons', () => {
    renderSearch()
    expect(screen.getByTestId('mode-btn-semantic')).toBeInTheDocument()
    expect(screen.getByTestId('mode-btn-keyword')).toBeInTheDocument()
  })

  it('defaults to Semantic mode with threshold slider visible', () => {
    renderSearch()
    expect(screen.getByTestId('threshold-control')).toBeInTheDocument()
    expect(screen.getByTestId('threshold-slider')).toBeInTheDocument()
  })

  it('hides threshold slider in keyword mode', () => {
    renderSearch()
    fireEvent.click(screen.getByTestId('mode-btn-keyword'))
    expect(screen.queryByTestId('threshold-control')).toBeNull()
  })
})

describe('SearchScreen — semantic search', () => {
  beforeEach(() => {
    mockSemanticSearch.mockResolvedValue(SEMANTIC_RESULTS)
  })

  it('calls semanticSearch when form is submitted', async () => {
    renderSearch()
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'Alice' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(mockSemanticSearch).toHaveBeenCalledWith(
      expect.objectContaining({ q: 'Alice' }),
    ))
  })

  it('renders semantic result cards with score percentages', async () => {
    renderSearch()
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'Alice' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(screen.getAllByTestId('search-result')).toHaveLength(2))
    const scores = screen.getAllByTestId('result-score')
    expect(scores[0].textContent).toBe('87%')
    expect(scores[1].textContent).toBe('72%')
  })

  it('renders open and approve buttons on each result card', async () => {
    renderSearch()
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'Alice' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(screen.getAllByTestId('result-open-btn')).toHaveLength(2))
    expect(screen.getAllByTestId('result-approve-btn')).toHaveLength(2)
  })

  it('shows empty state when no results', async () => {
    mockSemanticSearch.mockResolvedValue([])
    renderSearch()
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'xyz' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(screen.getByTestId('search-empty')).toBeInTheDocument())
  })
})

describe('SearchScreen — keyword search', () => {
  beforeEach(() => {
    mockKeywordSearch.mockResolvedValue(KEYWORD_RESULTS)
  })

  it('calls keywordSearch when in keyword mode', async () => {
    renderSearch()
    fireEvent.click(screen.getByTestId('mode-btn-keyword'))
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'notes' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(mockKeywordSearch).toHaveBeenCalledWith(
      expect.objectContaining({ q: 'notes' }),
    ))
  })

  it('renders keyword result cards', async () => {
    renderSearch()
    fireEvent.click(screen.getByTestId('mode-btn-keyword'))
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'notes' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(screen.getAllByTestId('search-result')).toHaveLength(2))
    expect(screen.getByText('Alice Smith')).toBeInTheDocument()
  })
})

describe('SearchScreen — actions', () => {
  beforeEach(() => {
    mockSemanticSearch.mockResolvedValue(SEMANTIC_RESULTS)
    mockApproveNote.mockResolvedValue({ file_path: 'people/alice.md', review_status: 'approved' })
  })

  it('approve action calls approveNote and shows toast', async () => {
    renderSearch()
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'Alice' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(screen.getAllByTestId('result-approve-btn')).toHaveLength(2))
    fireEvent.click(screen.getAllByTestId('result-approve-btn')[0])
    await waitFor(() => expect(mockApproveNote).toHaveBeenCalledWith('people/alice.md'))
    await waitFor(() => expect(screen.getByTestId('search-toast')).toBeInTheDocument())
  })

  it('does not submit with empty query', async () => {
    renderSearch()
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    expect(mockSemanticSearch).not.toHaveBeenCalled()
  })

  it('shows error when search API fails', async () => {
    mockSemanticSearch.mockRejectedValue(new Error('Network error'))
    renderSearch()
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'test' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(screen.getByTestId('search-error')).toBeInTheDocument())
    expect(screen.getByTestId('search-error').textContent).toMatch(/Network error/)
  })

  it('result count shown after search', async () => {
    renderSearch()
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'Alice' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(screen.getByText(/2 results/)).toBeInTheDocument())
  })

  it('approve button disappears after successful approval', async () => {
    renderSearch()
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'Alice' } })
    fireEvent.submit(screen.getByTestId('search-input').closest('form')!)
    await waitFor(() => expect(screen.getAllByTestId('result-approve-btn')).toHaveLength(2))

    // Approve the first result (alice.md)
    fireEvent.click(screen.getAllByTestId('result-approve-btn')[0])
    await waitFor(() => expect(mockApproveNote).toHaveBeenCalledWith('people/alice.md'))

    // Button for alice.md should be gone; meeting.md still has one
    await waitFor(() => expect(screen.getAllByTestId('result-approve-btn')).toHaveLength(1))
  })
})
