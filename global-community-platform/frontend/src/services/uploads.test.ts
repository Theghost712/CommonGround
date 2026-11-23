import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const put = vi.hoisted(() => vi.fn())
vi.mock('./api', () => ({ api }))
vi.mock('axios', () => ({ default: { put } }))

describe('direct uploads', () => {
  beforeEach(() => { vi.resetModules(); api.get.mockReset(); api.post.mockReset(); put.mockReset() })

  it('asks for a one-time URL, PUTs the file there with progress, and returns the key', async () => {
    const { uploadDirect } = await import('./uploads')
    api.post.mockResolvedValue({ data: { key: 'incoming/1/abc.mp4', upload_url: 'https://store.example/upload?token=t', headers: { 'x-upsert': 'false', 'Content-Type': 'video/mp4' } } })
    put.mockImplementation(async (_url, _file, options) => { options.onUploadProgress({ loaded: 50, total: 100 }); return { status: 200 } })
    const progress: number[] = []
    const file = new File([new Uint8Array(100)], 'clip.mov', { type: '' })
    const key = await uploadDirect(file, 'post-video', (p) => progress.push(p))
    expect(key).toBe('incoming/1/abc.mp4')
    expect(api.post).toHaveBeenCalledWith('/uploads/', { purpose: 'post-video', content_type: 'video/quicktime', size: 100 })
    expect(put).toHaveBeenCalledWith('https://store.example/upload?token=t', file, expect.objectContaining({ headers: { 'x-upsert': 'false', 'Content-Type': 'video/quicktime' } }))
    expect(progress).toEqual([0.5])
  })

  it('caches the config and falls back to app uploads when it cannot be read', async () => {
    const { getUploadConfig } = await import('./uploads')
    api.get.mockRejectedValueOnce(new Error('offline'))
    expect((await getUploadConfig()).direct).toBe(false)
    api.get.mockResolvedValue({ data: { direct: true, max_photo_mb: 15, max_video_mb: 50, max_story_video_mb: 50 } })
    expect((await getUploadConfig()).max_video_mb).toBe(50)
    await getUploadConfig()
    expect(api.get).toHaveBeenCalledTimes(2)
  })
})
