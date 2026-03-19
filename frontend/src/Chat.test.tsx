import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import ChatScreen from './components/Chat/ChatScreen'
import ChatMessage from './components/Chat/ChatMessage'
import ChatInput from './components/Chat/ChatInput'
import type { ThreadMessage } from './hooks/useChat'

// ── Module mocks ─────────────────────────────────────────────────

// Mock useChat so ChatScreen tests don't depend on localStorage / SSE
const mockSend = vi.fn()
const mockSelectSession = vi.fn()
const mockNewSession = vi.fn()

vi.mock('./hooks/useChat', () => ({
  useChat: () => ({
    thread: [],
    isStreaming: false,
    sessions: [],
    currentSessionId: null,
    send: mockSend,
    selectSession: mockSelectSession,
    newSession: mockNewSession,
  }),
}))

// Mock streamChat so it doesn't open real connections in ChatMessage/useChat tests
vi.mock('./api/chat', () => ({
  streamChat: vi.fn(),
}))

// ── Helpers ──────────────────────────────────────────────────────

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

// ── ChatInput tests ──────────────────────────────────────────────

describe('ChatInput', () => {
  beforeEach(() => {
    mockSend.mockReset()
  })

  it('renders textarea and send button', () => {
    render(<ChatInput onSend={mockSend} />)
    expect(screen.getByTestId('chat-input-textarea')).toBeInTheDocument()
    expect(screen.getByTestId('send-btn')).toBeInTheDocument()
  })

  it('calls onSend on Enter key', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'hello' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(mockSend).toHaveBeenCalledWith('hello')
  })

  it('does not call onSend on Shift+Enter', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'hello' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })
    expect(mockSend).not.toHaveBeenCalled()
  })

  it('calls onSend when send button clicked', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: 'world' } })
    fireEvent.click(screen.getByTestId('send-btn'))
    expect(mockSend).toHaveBeenCalledWith('world')
  })

  it('does not send empty or whitespace-only input', () => {
    render(<ChatInput onSend={mockSend} />)
    const textarea = screen.getByTestId('chat-input-textarea')
    fireEvent.change(textarea, { target: { value: '   ' } })
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(mockSend).not.toHaveBeenCalled()
  })

  it('send button is disabled while streaming', () => {
    render(<ChatInput onSend={mockSend} disabled />)
    const btn = screen.getByTestId('send-btn')
    expect(btn).toBeDisabled()
  })

  it('renders voice button when onVoiceClick is provided', () => {
    render(<ChatInput onSend={mockSend} onVoiceClick={vi.fn()} />)
    expect(screen.getByTestId('voice-btn')).toBeInTheDocument()
  })

  it('does not render voice button when onVoiceClick is absent', () => {
    render(<ChatInput onSend={mockSend} />)
    expect(screen.queryByTestId('voice-btn')).toBeNull()
  })
})

// ── ChatMessage tests ─────────────────────────────────────────────

describe('ChatMessage', () => {
  it('renders user message text', () => {
    const msg: ThreadMessage = { role: 'user', content: 'Hello there' }
    render(<ChatMessage message={msg} />)
    expect(screen.getByText('Hello there')).toBeInTheDocument()
  })

  it('applies user alignment class', () => {
    const msg: ThreadMessage = { role: 'user', content: 'test' }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message--user')).toBeTruthy()
  })

  it('applies assistant alignment class', () => {
    const msg: ThreadMessage = { role: 'assistant', content: 'response' }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message--assistant')).toBeTruthy()
  })

  it('renders assistant message with markdown wrapper', () => {
    const msg: ThreadMessage = { role: 'assistant', content: '**bold**' }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message__markdown')).toBeTruthy()
  })

  it('renders tool call disclosures', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [{ name: 'search_vault', resultCount: 4 }],
    }
    const { container } = render(<ChatMessage message={msg} />)
    const tools = container.querySelector('[data-testid="tool-calls"]')
    expect(tools).toBeTruthy()
    expect(tools?.textContent).toContain('search_vault')
    expect(tools?.textContent).toContain('4 results')
  })

  it('renders tool call with singular result count', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [{ name: 'read_note', resultCount: 1 }],
    }
    const { container } = render(<ChatMessage message={msg} />)
    const summary = container.querySelector('.tool-call__summary')
    expect(summary?.textContent).toContain('1 result')
  })

  it('renders error tool call with error class', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [{ name: 'search_vault', error: 'timeout' }],
    }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.tool-call--error')).toBeTruthy()
  })

  it('renders note created card', () => {
    const msg: ThreadMessage = {
      role: 'assistant',
      content: 'Done',
      noteCreated: { filePath: 'people/alice.md', type: 'person_note' },
    }
    render(<ChatMessage message={msg} />)
    expect(screen.getByTestId('note-card')).toBeInTheDocument()
    expect(screen.getByTestId('note-card').textContent).toContain('alice.md')
  })

  it('shows blinking cursor when streaming', () => {
    const msg: ThreadMessage = { role: 'assistant', content: '', isStreaming: true }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message__cursor')).toBeTruthy()
  })

  it('does not show cursor when not streaming', () => {
    const msg: ThreadMessage = { role: 'assistant', content: 'done', isStreaming: false }
    const { container } = render(<ChatMessage message={msg} />)
    expect(container.querySelector('.chat-message__cursor')).toBeFalsy()
  })
})

// ── ChatScreen tests ──────────────────────────────────────────────

describe('ChatScreen', () => {
  beforeEach(() => {
    mockSend.mockReset()
    mockNewSession.mockReset()
    mockSelectSession.mockReset()
  })

  it('renders 6 chat starter tiles when thread is empty', () => {
    renderWithRouter(<ChatScreen />)
    const starters = screen.getAllByTestId('chat-starter')
    expect(starters).toHaveLength(6)
  })

  it('renders session picker', () => {
    renderWithRouter(<ChatScreen />)
    expect(screen.getByTestId('session-picker')).toBeInTheDocument()
  })

  it('renders the chat input', () => {
    renderWithRouter(<ChatScreen />)
    expect(screen.getByTestId('chat-input-textarea')).toBeInTheDocument()
  })

  it('clicking a starter with prompt calls send', () => {
    renderWithRouter(<ChatScreen />)
    // "Open action items" starter sends directly
    const starters = screen.getAllByTestId('chat-starter')
    const actionItemsStarter = starters.find(el => el.textContent?.includes('Open action items'))
    expect(actionItemsStarter).toBeTruthy()
    act(() => { fireEvent.click(actionItemsStarter!) })
    expect(mockSend).toHaveBeenCalledWith('Show me all open action items')
  })

  it('session picker shows + New session as default option', () => {
    renderWithRouter(<ChatScreen />)
    const picker = screen.getByTestId('session-picker') as HTMLSelectElement
    expect(picker.options[0].text).toBe('+ New session')
  })

  it('selecting + New session calls newSession', () => {
    renderWithRouter(<ChatScreen />)
    const picker = screen.getByTestId('session-picker')
    fireEvent.change(picker, { target: { value: '' } })
    expect(mockNewSession).toHaveBeenCalled()
  })
})
