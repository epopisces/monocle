import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import SettingsModal from './components/SettingsModal'
import { getSettings, patchSettings, rotateMcpKey } from './api/settings'
import { getModelStatus } from './api/health'

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('./api/settings', () => ({
  getSettings: vi.fn(),
  patchSettings: vi.fn(),
  rotateMcpKey: vi.fn(),
}))

vi.mock('./api/health', () => ({
  getHealth: vi.fn(),
  // Default: never resolves — prevents state-update errors in tests that don't care
  getModelStatus: vi.fn(() => new Promise(() => undefined)),
}))

// Replace useTheme with a controlled mock so tests don't need ThemeContext wiring
const mockSetTheme = vi.fn()
vi.mock('./hooks/useTheme', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./hooks/useTheme')>()
  return {
    ...actual,
    useTheme: () => ({ theme: 'dark' as const, resolvedTheme: 'dark' as const, setTheme: mockSetTheme }),
  }
})

// ── Fixture ───────────────────────────────────────────────────────────────────

const mockSettings = {
  ai: {
    chat_model_key: 'llama3.2',
    embed_model_key: 'nomic-embed',
    stt_key: null,
    embed_dimensions: null,
    transcribe_backend: 'subprocess',
    transcribe_url: null,
    ollama_base_url: 'http://localhost:11434',
    foundry_local_base_url: 'http://localhost:5272',
    models: [
      { key: 'llama3.2', name: 'llama3.2', role: 'chat', provider: 'ollama', base_url: null },
      { key: 'qwen3', name: 'qwen3:9b', role: 'chat', provider: 'ollama', base_url: null },
      { key: 'nomic-embed', name: 'nomic-embed-text', role: 'embed', provider: 'ollama', base_url: null },
    ],
  },
  vault: { path: '/vault', inbox_path: '/vault/inbox', templates_path: '/vault/.templates', watch: true, debounce_ms: 2000 },
  index: { chroma_persist_path: './data/chroma', collection_name: 'monocle' },
  agents: { weekly_summary_cron: '0 9 * * 1', reindex_cron: '0 2 * * *' },
  review: { queue_threshold: 70, auto_approve_threshold_pct: 90, confidence_weights: {} },
  server: { host: '127.0.0.1', port: 8000, dev_mode: false },
  telemetry: { enabled: false, otlp_endpoint: '', log_level: 'INFO', log_format: 'text', trace_filters: ['/api/health'] },
  ui: {},
  mcp_key_last4: 'ab12',
} as const

function renderModal(open = true, onClose = vi.fn()) {
  return render(<SettingsModal open={open} onClose={onClose} />)
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SettingsModal — not open', () => {
  it('renders nothing when open=false', () => {
    renderModal(false)
    expect(screen.queryByTestId('settings-modal')).toBeNull()
  })
})

describe('SettingsModal — loading state', () => {
  it('shows loading indicator while settings are fetching', () => {
    // Never resolves — simulates pending request
    vi.mocked(getSettings).mockReturnValue(new Promise(() => undefined))
    renderModal()
    expect(screen.getByTestId('settings-modal')).toBeInTheDocument()
    expect(screen.getByText(/loading settings/i)).toBeInTheDocument()
  })
})

describe('SettingsModal — loaded state', () => {
  const mockModelStatus = {
    provider: 'ollama',
    provider_reachable: true,
    models: [
      { name: 'llama3.2', role: 'chat' as const, available: true, loaded: false },
      { name: 'nomic-embed-text', role: 'embed' as const, available: true, loaded: true },
    ],
  }

  beforeEach(() => {
    mockSetTheme.mockReset()
    vi.mocked(getSettings).mockResolvedValue({ ...mockSettings })
    vi.mocked(patchSettings).mockResolvedValue({ ...mockSettings })
    vi.mocked(getModelStatus).mockResolvedValue(mockModelStatus)
  })
  afterEach(() => vi.restoreAllMocks())

  it('renders settings data after load', async () => {
    renderModal()
    const select = await screen.findByTestId('chat-model-select')
    expect(select).toHaveValue('llama3.2')
  })

  it('shows masked MCP key hint', async () => {
    renderModal()
    await screen.findByTestId('chat-model-select')
    expect(screen.getByTestId('mcp-key-hint')).toHaveTextContent('••••ab12')
  })

  it('calls patchSettings when chat model changes', async () => {
    renderModal()
    const select = await screen.findByTestId('chat-model-select')
    fireEvent.change(select, { target: { value: 'qwen3' } })
    await waitFor(() =>
      expect(patchSettings).toHaveBeenCalledWith({ ai: { chat_model_key: 'qwen3' } }),
    )
  })

  it('calls patchSettings after 400ms debounce when threshold slider changes', async () => {
    renderModal()
    const slider = await screen.findByTestId('queue-threshold-slider')
    vi.useFakeTimers()

    fireEvent.change(slider, { target: { value: '80' } })
    expect(patchSettings).not.toHaveBeenCalled()

    act(() => { vi.advanceTimersByTime(400) })
    expect(patchSettings).toHaveBeenCalledWith({ review: { queue_threshold: 80 } })

    vi.useRealTimers()
  })

  it('slider does not call patchSettings before debounce fires', async () => {
    renderModal()
    const slider = await screen.findByTestId('queue-threshold-slider')
    vi.useFakeTimers()

    fireEvent.change(slider, { target: { value: '55' } })
    act(() => { vi.advanceTimersByTime(300) })    // < 400ms
    expect(patchSettings).not.toHaveBeenCalled()

    vi.useRealTimers()
  })

  it('theme radio calls setTheme', async () => {
    renderModal()
    await screen.findByTestId('chat-model-select')
    fireEvent.click(screen.getByTestId('theme-radio-light'))
    expect(mockSetTheme).toHaveBeenCalledWith('light')
  })

  it('shows model status panel when model data loads', async () => {
    renderModal()
    await screen.findByTestId('chat-model-select')
    await waitFor(() => expect(screen.getByTestId('model-status-panel')).toBeInTheDocument())
    expect(screen.getByTestId('model-status-chat')).toBeInTheDocument()
    expect(screen.getByTestId('model-status-embed')).toBeInTheDocument()
  })

  it('shows badge "available" for chat model that is not loaded', async () => {
    renderModal()
    await screen.findByTestId('chat-model-select')
    await waitFor(() => {
      const chatRow = screen.getByTestId('model-status-chat')
      expect(chatRow).toHaveTextContent('available')
    })
  })

  it('shows provider-unreachable message when provider is down', async () => {
    vi.mocked(getModelStatus).mockResolvedValueOnce({
      provider: 'ollama',
      provider_reachable: false,
      models: [],
    })
    renderModal()
    await screen.findByTestId('chat-model-select')
    await waitFor(() =>
      expect(screen.getByTestId('provider-unreachable')).toBeInTheDocument(),
    )
  })
})

describe('SettingsModal — MCP key rotation', () => {
  beforeEach(() => {
    vi.mocked(getSettings).mockResolvedValue({ ...mockSettings })
  })
  afterEach(() => vi.restoreAllMocks())

  it('calls rotateMcpKey and updates hint on success', async () => {
    vi.mocked(rotateMcpKey).mockResolvedValueOnce({ mcp_key_last4: 'zz99' })
    renderModal()
    const btn = await screen.findByTestId('rotate-key-btn')
    fireEvent.click(btn)
    await waitFor(() =>
      expect(screen.getByTestId('mcp-key-hint')).toHaveTextContent('••••zz99'),
    )
  })
})

describe('SettingsModal — error state', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows error message when getSettings rejects', async () => {
    vi.mocked(getSettings).mockRejectedValueOnce(new Error('Network error'))
    renderModal()
    await waitFor(() =>
      expect(screen.getByText(/network error/i)).toBeInTheDocument(),
    )
  })
})

describe('SettingsModal — close behaviour', () => {
  beforeEach(() => {
    vi.mocked(getSettings).mockReturnValue(new Promise(() => undefined))
  })
  afterEach(() => vi.restoreAllMocks())

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn()
    renderModal(true, onClose)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose when backdrop is clicked', () => {
    const onClose = vi.fn()
    renderModal(true, onClose)
    const overlay = screen.getByTestId('settings-modal')
    // Simulate click directly on the overlay element (not on a child)
    fireEvent.click(overlay, { target: overlay })
    expect(onClose).toHaveBeenCalled()
  })
})

describe('SettingsModal — patchSettings rejection', () => {
  beforeEach(() => {
    vi.mocked(getSettings).mockResolvedValue({ ...mockSettings })
  })
  afterEach(() => vi.restoreAllMocks())

  it('shows an inline error message when patchSettings rejects', async () => {
    vi.mocked(patchSettings).mockRejectedValueOnce(new Error('Save failed'))
    renderModal()
    const select = await screen.findByTestId('chat-model-select')
    fireEvent.change(select, { target: { value: 'qwen3' } })
    await waitFor(() =>
      expect(screen.getByTestId('settings-error')).toHaveTextContent(/save failed/i),
    )
  })

  it('clears the error when a subsequent save succeeds', async () => {
    vi.mocked(patchSettings)
      .mockRejectedValueOnce(new Error('Save failed'))
      .mockResolvedValueOnce({ ...mockSettings, ai: { ...mockSettings.ai, chat_model_key: 'qwen3' } })
    renderModal()
    const select = await screen.findByTestId('chat-model-select')

    // First save — triggers error
    fireEvent.change(select, { target: { value: 'qwen3' } })
    await waitFor(() => expect(screen.getByTestId('settings-error')).toBeInTheDocument())

    // Second save — should clear the error
    fireEvent.change(select, { target: { value: 'qwen3' } })
    await waitFor(() => expect(screen.queryByTestId('settings-error')).toBeNull())
  })
})

describe('SettingsModal — MCP key rotation failure', () => {
  beforeEach(() => {
    vi.mocked(getSettings).mockResolvedValue({ ...mockSettings })
  })
  afterEach(() => vi.restoreAllMocks())

  it('shows an error when rotateMcpKey rejects', async () => {
    vi.mocked(rotateMcpKey).mockRejectedValueOnce(new Error('Key rotation failed'))
    renderModal()
    const btn = await screen.findByTestId('rotate-key-btn')
    fireEvent.click(btn)
    await waitFor(() =>
      expect(screen.getByTestId('settings-error')).toHaveTextContent(/key rotation failed/i),
    )
  })

  it('does not update the key hint when rotation fails', async () => {
    vi.mocked(rotateMcpKey).mockRejectedValueOnce(new Error('Rotation unavailable'))
    renderModal()
    await screen.findByTestId('rotate-key-btn')

    const hintBefore = screen.getByTestId('mcp-key-hint').textContent

    fireEvent.click(screen.getByTestId('rotate-key-btn'))
    // Wait for the error to appear (meaning the rejection was handled)
    await waitFor(() => screen.getByTestId('settings-error'))

    // Hint must still show the original masked key
    expect(screen.getByTestId('mcp-key-hint').textContent).toBe(hintBefore)
  })
})

describe('SettingsModal — Tracing Filters', () => {
  beforeEach(() => {
    vi.mocked(getSettings).mockResolvedValue({ ...mockSettings })
    vi.mocked(patchSettings).mockResolvedValue({ ...mockSettings })
  })
  afterEach(() => vi.restoreAllMocks())

  it('renders tracing filter checkboxes', async () => {
    renderModal()
    await screen.findByTestId('chat-model-select')
    expect(screen.getByTestId('trace-filter-api-health')).toBeInTheDocument()
    expect(screen.getByTestId('trace-filter-api-review-count')).toBeInTheDocument()
    expect(screen.getByTestId('trace-filter-api-ingest-failures')).toBeInTheDocument()
  })

  it('health check filter is checked by default (in mockSettings)', async () => {
    renderModal()
    await screen.findByTestId('chat-model-select')
    const checkbox = screen.getByTestId('trace-filter-api-health').querySelector('input')
    expect(checkbox).toBeChecked()
  })

  it('other filters are unchecked by default', async () => {
    renderModal()
    await screen.findByTestId('chat-model-select')
    const reviewCheckbox = screen.getByTestId('trace-filter-api-review-count').querySelector('input')
    expect(reviewCheckbox).not.toBeChecked()
  })

  it('toggles a filter on and calls patchSettings with updated list', async () => {
    renderModal()
    await screen.findByTestId('chat-model-select')
    const reviewCheckbox = screen.getByTestId('trace-filter-api-review-count').querySelector('input')!
    fireEvent.click(reviewCheckbox)
    await waitFor(() =>
      expect(patchSettings).toHaveBeenCalledWith({
        telemetry: { trace_filters: ['/api/health', '/api/review/count'] },
      }),
    )
  })

  it('toggles a filter off and calls patchSettings with reduced list', async () => {
    renderModal()
    await screen.findByTestId('chat-model-select')
    const healthCheckbox = screen.getByTestId('trace-filter-api-health').querySelector('input')!
    fireEvent.click(healthCheckbox)
    await waitFor(() =>
      expect(patchSettings).toHaveBeenCalledWith({
        telemetry: { trace_filters: [] },
      }),
    )
  })
})
