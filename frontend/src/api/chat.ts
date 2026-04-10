import { apiPostSseStream } from './client'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatRequest {
  messages: ChatMessage[]
  session_id?: string
  tool_hint?: string
  fetch_urls?: string[]
}

/** SSE event payloads */
export interface TokenEvent { delta: string }
export interface ToolCallEvent { name: string; result_count?: number }
export interface ToolErrorEvent { name: string; error: string }
export interface NoteCreatedEvent { file_path: string; type: string }
export interface DoneEvent { total_tokens?: number; session_id?: string }
export interface ErrorEvent { message: string }

export type ChatEvent =
  | { event: 'token'; data: TokenEvent }
  | { event: 'tool_call'; data: ToolCallEvent }
  | { event: 'tool_error'; data: ToolErrorEvent }
  | { event: 'note_created'; data: NoteCreatedEvent }
  | { event: 'done'; data: DoneEvent }
  | { event: 'error'; data: ErrorEvent }

export async function* streamChat(
  body: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  for await (const { event, data } of apiPostSseStream('/api/chat', body, signal)) {
    yield { event, data } as ChatEvent
  }
}
