import type { components } from './schema.d.ts'

export type TranscribeResponse = components['schemas']['TranscribeResponse']

/**
 * Upload an audio blob to POST /api/transcribe and return the transcript.
 * Uses multipart/form-data (matches the backend UploadFile + Form route).
 */
export async function transcribeAudio(
  blob: Blob,
  mimeType = 'audio/webm',
): Promise<TranscribeResponse> {
  const form = new FormData()
  form.append('file', blob, 'recording.webm')
  form.append('mime_type', mimeType)

  const res = await fetch('/api/transcribe', { method: 'POST', body: form })

  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: string }
      if (body?.detail) message = String(body.detail)
    } catch { /* ignore parse error */ }
    throw new Error(message)
  }

  return res.json() as Promise<TranscribeResponse>
}
