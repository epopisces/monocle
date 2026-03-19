import type { components, operations } from './schema.d.ts'
import { apiGet, apiPut, apiPatch, apiDelete, apiPost } from './client'

export type Note = components['schemas']['Note']
export type NoteRef = components['schemas']['NoteRef']
export type NoteMetadata = components['schemas']['NoteMetadata']
export type NoteWriteRequest = components['schemas']['NoteWriteRequest']
export type NotePatchRequest = components['schemas']['NotePatchRequest']
export type NoteMoveRequest = components['schemas']['NoteMoveRequest']
export type BacklinkRef = components['schemas']['BacklinkRef']
export type PageNoteRef = components['schemas']['Page_NoteRef_']

export type ListNotesParams = NonNullable<
  operations['list_notes_api_notes_get']['parameters']['query']
>

export function listNotes(params?: ListNotesParams): Promise<PageNoteRef> {
  return apiGet<PageNoteRef>('/api/notes', params as Record<string, string | number | boolean | null | undefined>)
}

export function getNote(path: string): Promise<Note> {
  return apiGet<Note>(`/api/notes/${encodeURIComponent(path)}`)
}

export function putNote(path: string, body: NoteWriteRequest): Promise<Note> {
  return apiPut<Note>(`/api/notes/${encodeURIComponent(path)}`, body)
}

export function patchNote(path: string, body: NotePatchRequest): Promise<Note> {
  return apiPatch<Note>(`/api/notes/${encodeURIComponent(path)}`, body)
}

export function deleteNote(path: string, ifMtime?: number): Promise<void> {
  const q = ifMtime !== undefined ? `?if_mtime=${ifMtime}` : ''
  return apiDelete<void>(`/api/notes/${encodeURIComponent(path)}${q}`)
}

export function moveNote(path: string, body: NoteMoveRequest): Promise<Note> {
  return apiPost<Note>(`/api/notes/${encodeURIComponent(path)}/move`, body)
}

export function getNoteBacklinks(path: string): Promise<BacklinkRef[]> {
  return apiGet<BacklinkRef[]>(`/api/notes/${encodeURIComponent(path)}/backlinks`)
}

export function listTemplates(): Promise<Record<string, unknown>[]> {
  return apiGet<Record<string, unknown>[]>('/api/templates')
}
