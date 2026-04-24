import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import IngestReviewScreen from './components/IngestReview/IngestReviewScreen'
import {
  answerIngestQuestion,
  approveAllIngestActions,
  approveIngestAction,
  getIngestSession,
  listIngestSessions,
  patchIngestAction,
  rejectIngestAction,
  startIngestReview,
} from './api/ingest'

const { initialDetail, secondDetail } = vi.hoisted(() => ({
  initialDetail: {
    session: {
      session_id: 'ing_1',
      origin: 'api',
      state: 'dormant_ready',
      source_ids: ['src_1'],
      title: 'Alice sync',
      digest: 'Prepared digest',
      open_questions: [{ id: 'oq_1', question: 'Need more context?', reason: 'Clarify the update.' }],
      related_notes: [{ file_path: 'people/alice.md', title: 'Alice', excerpt: 'Existing summary' }],
      contradictions: [{ file_path: 'people/alice.md', title: 'Alice', summary: 'Existing note may be stale.' }],
      proposed_actions: [{
        action_id: 'act_1',
        action_type: 'update_note',
        approval_state: 'draft',
        target_file_path: 'people/alice.md',
        target_note_type: 'person_note',
        rationale: 'Refresh the note.',
        diff_preview: {
          kind: 'update',
          before_excerpt: 'Original meeting notes.',
          after_excerpt: 'Updated meeting notes.',
          hunks: [{ section: 'body', before: 'Original meeting notes.', after: 'Updated meeting notes.' }],
        },
        proposed_content: { title: 'Alice', body: 'Updated meeting notes.' },
      }],
      created_at: '2026-04-24T00:00:00Z',
      updated_at: '2026-04-24T00:00:00Z',
      prepared_at: '2026-04-24T00:00:00Z',
      last_true_up_at: null,
    },
    sources: [{
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
    }],
  },
  secondDetail: {
    session: {
      session_id: 'ing_2',
      origin: 'api',
      state: 'dormant_ready',
      source_ids: ['src_2'],
      title: 'Bob sync',
      digest: 'Second prepared digest',
      open_questions: [],
      related_notes: [],
      contradictions: [],
      proposed_actions: [{
        action_id: 'act_2',
        action_type: 'update_note',
        approval_state: 'draft',
        target_file_path: 'people/bob.md',
        target_note_type: 'person_note',
        rationale: 'Refresh Bob note.',
        diff_preview: {
          kind: 'update',
          before_excerpt: 'Old Bob notes.',
          after_excerpt: 'New Bob notes.',
          hunks: [{ section: 'body', before: 'Old Bob notes.', after: 'New Bob notes.' }],
        },
        proposed_content: { title: 'Bob', body: 'New Bob notes.' },
      }],
      created_at: '2026-04-24T00:00:00Z',
      updated_at: '2026-04-24T00:00:00Z',
      prepared_at: '2026-04-24T00:00:00Z',
      last_true_up_at: null,
    },
    sources: [{
      source_id: 'src_2',
      session_id: 'ing_2',
      kind: 'text',
      status: 'ready',
      source_name: 'capture-2.txt',
      mime_type: 'text/plain',
      archive_path: 'src_2/payload',
      checksum_sha256: 'def',
      captured_at: '2026-04-24T00:00:00Z',
      byte_size: 14,
      provenance: {},
    }],
  },
}))

vi.mock('./api/ingest', () => ({
  listIngestSessions: vi.fn().mockResolvedValue([initialDetail.session]),
  getIngestSession: vi.fn().mockResolvedValue(initialDetail),
  startIngestReview: vi.fn().mockResolvedValue({
    ...initialDetail,
    session: { ...initialDetail.session, state: 'in_review' },
  }),
  answerIngestQuestion: vi.fn().mockResolvedValue({
    ...initialDetail,
    session: {
      ...initialDetail.session,
      state: 'proposal_ready',
      open_questions: [{ ...initialDetail.session.open_questions[0], answer: 'Clarified answer' }],
    },
  }),
  patchIngestAction: vi.fn().mockResolvedValue({
    ...initialDetail,
    session: {
      ...initialDetail.session,
      proposed_actions: [{
        ...initialDetail.session.proposed_actions[0],
        approval_state: 'edited',
        rationale: 'Refresh the note with clarified details.',
        diff_preview: {
          kind: 'update',
          before_excerpt: 'Original meeting notes.',
          after_excerpt: 'Edited meeting notes.',
          hunks: [{ section: 'body', before: 'Original meeting notes.', after: 'Edited meeting notes.' }],
        },
        proposed_content: { title: 'Alice', body: 'Edited meeting notes.' },
      }],
    },
  }),
  approveIngestAction: vi.fn().mockResolvedValue({
    ...initialDetail,
    session: {
      ...initialDetail.session,
      state: 'approved_pending_execution',
      proposed_actions: [{ ...initialDetail.session.proposed_actions[0], approval_state: 'approved' }],
    },
  }),
  rejectIngestAction: vi.fn().mockResolvedValue({
    ...initialDetail,
    session: {
      ...initialDetail.session,
      state: 'proposal_ready',
      proposed_actions: [{ ...initialDetail.session.proposed_actions[0], approval_state: 'rejected' }],
    },
  }),
  approveAllIngestActions: vi.fn().mockResolvedValue({
    ...initialDetail,
    session: {
      ...initialDetail.session,
      state: 'approved_pending_execution',
      proposed_actions: [{ ...initialDetail.session.proposed_actions[0], approval_state: 'approved' }],
    },
  }),
  trueUpIngestSession: vi.fn(),
}))

function renderScreen() {
  return render(
    <MemoryRouter initialEntries={['/ingest-review?session=ing_1']}>
      <IngestReviewScreen />
    </MemoryRouter>,
  )
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => {
    resolve = res
  })
  return { promise, resolve }
}

describe('IngestReviewScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listIngestSessions).mockResolvedValue([initialDetail.session])
    vi.mocked(getIngestSession).mockResolvedValue(initialDetail)
  })

  it('loads the review workspace and supports core M36 actions', async () => {
    renderScreen()

    expect(await screen.findByTestId('ingest-review-screen')).toBeInTheDocument()
    expect(await screen.findByTestId('ingest-review-detail')).toBeInTheDocument()
    expect(screen.getByText('Existing note may be stale.')).toBeInTheDocument()
    expect(screen.getByTestId('review-diff')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Start review/i }))
    await waitFor(() => expect(startIngestReview).toHaveBeenCalledWith('ing_1'))

    const answerBox = screen.getByPlaceholderText('Add the missing context')
    fireEvent.change(answerBox, { target: { value: 'Clarified answer' } })
    fireEvent.click(screen.getByRole('button', { name: /Save answer/i }))
    await waitFor(() => expect(answerIngestQuestion).toHaveBeenCalledWith('ing_1', 'oq_1', { answer: 'Clarified answer' }))

    const rationaleBoxes = screen.getAllByLabelText('Rationale')
    fireEvent.change(rationaleBoxes[0], { target: { value: 'Refresh the note with clarified details.' } })
    const bodyBoxes = screen.getAllByLabelText('Body')
    fireEvent.change(bodyBoxes[0], { target: { value: 'Edited meeting notes.' } })
    fireEvent.click(screen.getByRole('button', { name: /Save draft/i }))
    await waitFor(() => expect(patchIngestAction).toHaveBeenCalledWith('ing_1', 'act_1', {
      rationale: 'Refresh the note with clarified details.',
      proposed_content: { title: 'Alice', body: 'Edited meeting notes.' },
    }))

    fireEvent.click(screen.getByRole('button', { name: /^Approve$/i }))
    await waitFor(() => expect(approveIngestAction).toHaveBeenCalledWith('ing_1', 'act_1'))

    fireEvent.click(screen.getByRole('button', { name: /Reject/i }))
    await waitFor(() => expect(rejectIngestAction).toHaveBeenCalledWith('ing_1', 'act_1'))

    fireEvent.click(screen.getByRole('button', { name: /Approve all/i }))
    await waitFor(() => expect(approveAllIngestActions).toHaveBeenCalledWith('ing_1'))
  })

  it('ignores stale detail responses when switching sessions quickly', async () => {
    const firstRequest = deferred<typeof initialDetail>()
    const secondRequest = deferred<typeof secondDetail>()

    vi.mocked(listIngestSessions).mockResolvedValue([initialDetail.session, secondDetail.session])
    vi.mocked(getIngestSession).mockImplementation((sessionId: string) => {
      if (sessionId === 'ing_1') {
        return firstRequest.promise
      }
      return secondRequest.promise
    })

    render(
      <MemoryRouter initialEntries={['/ingest-review']}>
        <IngestReviewScreen />
      </MemoryRouter>,
    )

    expect(await screen.findByTestId('ingest-review-screen')).toBeInTheDocument()
    await waitFor(() => expect(listIngestSessions).toHaveBeenCalledTimes(1))
    fireEvent.click(await screen.findByRole('button', { name: /Bob sync/i }))
    await waitFor(() => expect(listIngestSessions).toHaveBeenCalledTimes(1))

    secondRequest.resolve(secondDetail)
    await waitFor(() => {
      const detail = screen.getByTestId('ingest-review-detail')
      expect(within(detail).getByRole('heading', { name: 'Bob sync' })).toBeInTheDocument()
    })

    firstRequest.resolve(initialDetail)
    await waitFor(() => {
      const detail = screen.getByTestId('ingest-review-detail')
      expect(within(detail).getByRole('heading', { name: 'Bob sync' })).toBeInTheDocument()
      expect(within(detail).queryByRole('heading', { name: 'Alice sync' })).toBeNull()
    })
  })
})
