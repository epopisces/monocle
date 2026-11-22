export const CHAT_DOCUMENT_DRAG_TYPE = 'application/x-monocle-chat-document'

export interface ChatDocumentDragPayload {
  filePath: string
  title: string
}

export function encodeChatDocumentDragPayload(payload: ChatDocumentDragPayload): string {
  return JSON.stringify(payload)
}

export function decodeChatDocumentDragPayload(raw: string): ChatDocumentDragPayload | null {
  try {
    const parsed = JSON.parse(raw) as Partial<ChatDocumentDragPayload>
    if (typeof parsed.filePath !== 'string' || typeof parsed.title !== 'string') return null
    return { filePath: parsed.filePath, title: parsed.title }
  } catch {
    return null
  }
}