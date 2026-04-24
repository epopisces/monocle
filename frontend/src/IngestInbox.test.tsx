import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import IngestInbox from './components/IngestInbox/IngestInbox'
import {
  countIngestNotifications,
  dismissIngestNotification,
  getIngestSession,
  listIngestNotifications,
  markIngestNotificationRead,
  trueUpIngestSession,
} from './api/ingest'

vi.mock('./api/ingest', () => ({
  countIngestNotifications: vi.fn().mockResolvedValue({ count: 0 }),
  dismissIngestNotification: vi.fn().mockResolvedValue(undefined),
  getIngestSession: vi.fn().mockResolvedValue({
    session: {
      session_id: 'ing_1',
      origin: 'api',
      state: 'dormant_ready',
      source_ids: ['src_1'],
      title: 'Alice sync',
      digest: 'Prepared digest',
      open_questions: [{ id: 'oq_1', question: 'Need more context?' }],
      related_notes: [{ file_path: 'people/alice.md', title: 'Alice' }],
      contradictions: [],
      proposed_actions: [{ action_id: 'act_1', action_type: 'create_note', rationale: 'Create note' }],
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
  }),
  listIngestNotifications: vi.fn().mockResolvedValue([
    {
      notification_id: 'notif_1',
      session_id: 'ing_1',
      kind: 'ingest_ready',
      status: 'unread',
      created_at: '2026-04-24T00:00:00Z',
      session_state: 'dormant_ready',
      session_title: 'Alice sync',
      session_digest: 'Prepared digest',
      source_names: ['capture.txt'],
      open_questions_count: 1,
      contradictions_count: 0,
      proposed_actions_count: 1,
    },
  ]),
  markIngestNotificationRead: vi.fn().mockResolvedValue(undefined),
  trueUpIngestSession: vi.fn().mockResolvedValue({
    session_id: 'ing_1',
    job_id: 'job_1',
    state: 'queued',
    last_true_up_at: '2026-04-24T00:00:00Z',
  }),
}))

function renderInRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('IngestInbox', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when closed', () => {
    renderInRouter(<IngestInbox open={false} onClose={vi.fn()} />)
    expect(screen.queryByTestId('ingest-inbox')).toBeNull()
  })

  it('loads notifications and shows session detail', async () => {
    renderInRouter(<IngestInbox open={true} onClose={vi.fn()} onCountUpdate={vi.fn()} />)

    expect(await screen.findByTestId('ingest-inbox')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('ingest-inbox-detail')).toBeInTheDocument())
    expect(markIngestNotificationRead).toHaveBeenCalledWith('notif_1')
  })

  it('dismisses a notification', async () => {
    renderInRouter(<IngestInbox open={true} onClose={vi.fn()} onCountUpdate={vi.fn()} />)
    const dismiss = await screen.findByRole('button', { name: /Dismiss Alice sync/i })
    fireEvent.click(dismiss)
    await waitFor(() => expect(dismissIngestNotification).toHaveBeenCalledWith('notif_1'))
    expect(countIngestNotifications).toHaveBeenCalled()
  })

  it('requeues a prepared session with true-up', async () => {
    renderInRouter(<IngestInbox open={true} onClose={vi.fn()} onCountUpdate={vi.fn()} />)
    const button = await screen.findByRole('button', { name: /True-up Preparation/i })
    fireEvent.click(button)
    await waitFor(() => expect(trueUpIngestSession).toHaveBeenCalledWith('ing_1'))
  })
})