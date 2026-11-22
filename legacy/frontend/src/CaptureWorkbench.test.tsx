import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CaptureWorkbench from './components/CaptureWorkbench/CaptureWorkbench'
import { deleteIngestFailure, retryIngestFailure } from './api/ingest'
import { approveNote, rejectNote } from './api/review'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('./api/review', () => ({
  approveNote: vi.fn().mockResolvedValue({}),
  rejectNote: vi.fn().mockResolvedValue({}),
}))

vi.mock('./api/ingest', () => ({
  retryIngestFailure: vi.fn().mockResolvedValue({}),
  deleteIngestFailure: vi.fn().mockResolvedValue(undefined),
}))

const summary = {
  actionable_count: 4,
  queue_threshold: 0.5,
  counts: {
    prepared: 1,
    pending_review: 1,
    failures: 2,
  },
  sections: [
    {
      section: 'prepared',
      count: 1,
      items: [
        {
          item_id: 'session-prepared',
          section: 'prepared',
          item_type: 'ingest_session',
          title: 'Prepared session',
          summary: 'Review this prepared capture.',
          session_id: 'session-prepared',
          state: 'dormant_ready',
          open_questions_count: 2,
          contradictions_count: 1,
          proposed_actions_count: 3,
          retryable: false,
        },
      ],
    },
    {
      section: 'pending_review',
      count: 1,
      items: [
        {
          item_id: 'work/pending-note.md',
          section: 'pending_review',
          item_type: 'pending_note',
          title: 'Pending note',
          file_path: 'work/pending-note.md',
          note_type: 'observation',
          confidence: 0.24,
          open_questions_count: 0,
          contradictions_count: 0,
          proposed_actions_count: 0,
          retryable: false,
        },
      ],
    },
    {
      section: 'failures',
      count: 2,
      items: [
        {
          item_id: 'failure-record',
          section: 'failures',
          item_type: 'failed_ingest',
          title: 'Failed web capture',
          summary: 'https://example.test',
          source: 'web',
          failure_id: 'failure-record',
          error_message: 'summary timed out',
          open_questions_count: 0,
          contradictions_count: 0,
          proposed_actions_count: 0,
          retryable: true,
        },
        {
          item_id: 'session-failed',
          section: 'failures',
          item_type: 'failed_session',
          title: 'Failed session',
          summary: 'The prepared session failed.',
          session_id: 'session-failed',
          state: 'failed',
          open_questions_count: 0,
          contradictions_count: 0,
          proposed_actions_count: 1,
          retryable: false,
        },
      ],
    },
  ],
} as const

function renderWorkbench(props?: Partial<React.ComponentProps<typeof CaptureWorkbench>>) {
  return render(
    <MemoryRouter>
      <CaptureWorkbench
        open={true}
        onClose={vi.fn()}
        summary={summary}
        loading={false}
        error={null}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        {...props}
      />
    </MemoryRouter>,
  )
}

describe('CaptureWorkbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not render when closed', () => {
    renderWorkbench({ open: false })
    expect(screen.queryByTestId('capture-workbench')).not.toBeInTheDocument()
  })

  it('renders prepared items by default and switches tabs', () => {
    renderWorkbench()

    expect(screen.getByText('Prepared session')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('capture-workbench-tab-pending_review'))
    expect(screen.getByText('Pending note')).toBeInTheDocument()
    expect(screen.getByText('Showing notes at or below 50% confidence.')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('capture-workbench-tab-failures'))
    expect(screen.getByText('Failed web capture')).toBeInTheDocument()
    expect(screen.getByText('Failed session')).toBeInTheDocument()
  })

  it('opens pending notes in the docs editor', () => {
    const onClose = vi.fn()
    renderWorkbench({ onClose })

    fireEvent.click(screen.getByTestId('capture-workbench-tab-pending_review'))
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith('/docs?path=work%2Fpending-note.md')
  })

  it('approves pending notes and refreshes the summary', async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined)
    renderWorkbench({ onRefresh })

    fireEvent.click(screen.getByTestId('capture-workbench-tab-pending_review'))
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(vi.mocked(approveNote)).toHaveBeenCalledWith('work/pending-note.md'))
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })

  it('retries failed ingests and refreshes the summary', async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined)
    renderWorkbench({ onRefresh })

    fireEvent.click(screen.getByTestId('capture-workbench-tab-failures'))
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => expect(vi.mocked(retryIngestFailure)).toHaveBeenCalledWith('failure-record'))
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })

  it('opens failed sessions in ingest review', () => {
    const onClose = vi.fn()
    renderWorkbench({ onClose })

    fireEvent.click(screen.getByTestId('capture-workbench-tab-failures'))
    fireEvent.click(screen.getByRole('button', { name: 'Open Session' }))

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(mockNavigate).toHaveBeenCalledWith('/ingest-review?session=session-failed')
  })
})