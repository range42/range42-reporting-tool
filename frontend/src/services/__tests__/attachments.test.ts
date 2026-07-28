import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as http from '@/services/http'
import {
  attachmentUrl,
  deleteAttachment,
  listAttachments,
  resolveAttachmentObjectUrl,
  uploadAttachment,
} from '@/services/attachments'

vi.mock('@/services/http', async (importOriginal) => {
  const mod = await importOriginal<typeof import('@/services/http')>()
  return {
    ...mod,
    apiGet: vi.fn(),
    apiUpload: vi.fn(),
    apiDelete: vi.fn(),
    apiGetBlob: vi.fn(),
  }
})

describe('attachments service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('builds the canonical sanitizer-allowed download URL', () => {
    expect(attachmentUrl('e1', 'r1', 'a1')).toBe(
      '/api/v1/exercises/e1/reports/r1/attachments/a1/download',
    )
  })

  it('lists report attachments', async () => {
    vi.mocked(http.apiGet).mockResolvedValue([])
    await listAttachments('tok', 'e1', 'r1')
    expect(http.apiGet).toHaveBeenCalledWith('/api/v1/exercises/e1/reports/r1/attachments', 'tok')
  })

  it('uploads to the section endpoint', async () => {
    const file = new File([new Uint8Array([1])], 'pic.png')
    vi.mocked(http.apiUpload).mockResolvedValue({ id: 'a1' })
    await uploadAttachment('tok', 'e1', 'r1', 's1', file)
    expect(http.apiUpload).toHaveBeenCalledWith(
      '/api/v1/exercises/e1/reports/r1/sections/s1/attachments',
      file,
      'tok',
    )
  })

  it('deletes by attachment id', async () => {
    vi.mocked(http.apiDelete).mockResolvedValue()
    await deleteAttachment('tok', 'e1', 'r1', 'a1')
    expect(http.apiDelete).toHaveBeenCalledWith(
      '/api/v1/exercises/e1/reports/r1/attachments/a1',
      'tok',
    )
  })

  it('resolves an object URL once per attachment URL (cached)', async () => {
    const createObjectURL = vi.fn(() => 'blob:one')
    vi.stubGlobal('URL', { ...URL, createObjectURL })
    vi.mocked(http.apiGetBlob).mockResolvedValue(new Blob([new Uint8Array([1])]))

    const url = attachmentUrl('e1', 'r1', 'cache-test')
    const first = await resolveAttachmentObjectUrl(url, 'tok')
    const second = await resolveAttachmentObjectUrl(url, 'tok')

    expect(first).toBe('blob:one')
    expect(second).toBe('blob:one')
    expect(http.apiGetBlob).toHaveBeenCalledTimes(1)
    vi.unstubAllGlobals()
  })
})
