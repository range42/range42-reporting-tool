import { apiDelete, apiGet, apiGetBlob, apiUpload } from '@/services/http'

/** Mirrors the backend `AttachmentOut`. */
export interface Attachment {
  id: string
  report_id: string
  section_id: string
  filename: string
  content_type: string
  size_bytes: number
  classification: string | null
  uploaded_by: string
  created_at: string
}

const base = (exerciseId: string, rid: string): string =>
  `/api/v1/exercises/${exerciseId}/reports/${rid}`

/** Canonical download URL — the form stored inside rich-text `<img src>` (sanitizer-allowlisted). */
export const attachmentUrl = (exerciseId: string, rid: string, aid: string): string =>
  `${base(exerciseId, rid)}/attachments/${aid}/download`

export const listAttachments = (
  token: string,
  exerciseId: string,
  rid: string,
): Promise<Attachment[]> => apiGet<Attachment[]>(`${base(exerciseId, rid)}/attachments`, token)

export const uploadAttachment = (
  token: string,
  exerciseId: string,
  rid: string,
  sectionId: string,
  file: File,
): Promise<Attachment> =>
  apiUpload<Attachment>(`${base(exerciseId, rid)}/sections/${sectionId}/attachments`, file, token)

export const deleteAttachment = (
  token: string,
  exerciseId: string,
  rid: string,
  aid: string,
): Promise<void> => apiDelete(`${base(exerciseId, rid)}/attachments/${aid}`, token)

// Bearer auth means plain <img src>/<a href> cannot load attachments directly;
// binaries are fetched with the token and surfaced as object URLs instead.

const objectUrlCache = new Map<string, string>()

/** Resolve an attachment URL to an authenticated blob object URL (cached per URL). */
export async function resolveAttachmentObjectUrl(url: string, token: string): Promise<string> {
  const cached = objectUrlCache.get(url)
  if (cached) return cached
  const blob = await apiGetBlob(url, token)
  const objectUrl = URL.createObjectURL(blob)
  objectUrlCache.set(url, objectUrl)
  return objectUrl
}

/** Fetch an attachment with auth and trigger a browser download of it. */
export async function downloadAttachment(
  token: string,
  exerciseId: string,
  rid: string,
  attachment: Attachment,
): Promise<void> {
  const blob = await apiGetBlob(attachmentUrl(exerciseId, rid, attachment.id), token)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = attachment.filename
  a.click()
  URL.revokeObjectURL(url)
}
