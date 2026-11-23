import axios from 'axios'
import { api } from './api'

export type UploadPurpose = 'post-photo' | 'post-video' | 'story-photo' | 'story-video'
export type UploadConfig = { direct: boolean; max_photo_mb: number; max_video_mb: number; max_story_video_mb: number }

const FALLBACK: UploadConfig = { direct: false, max_photo_mb: 15, max_video_mb: 100, max_story_video_mb: 50 }
let configRequest: Promise<UploadConfig> | null = null

/** Whether big files go straight to storage (past the host's request-size limit), and the limits. */
export function getUploadConfig(): Promise<UploadConfig> {
  configRequest ??= api.get<UploadConfig>('/uploads/config/').then(({ data }) => data).catch(() => {
    configRequest = null
    return FALLBACK
  })
  return configRequest
}

const BY_EXTENSION: Record<string, string> = {
  jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', gif: 'image/gif', heic: 'image/heic',
  mp4: 'video/mp4', m4v: 'video/mp4', mov: 'video/quicktime', webm: 'video/webm',
}

export function contentTypeOf(file: Blob & { name?: string }): string {
  if (file.type) return file.type
  const extension = (file.name || '').split('.').pop()?.toLowerCase() || ''
  return BY_EXTENSION[extension] || 'application/octet-stream'
}

/**
 * Upload one file straight to storage and return its key for the create endpoint.
 * The upload URL is single-use and signed by the server; no login token goes to storage.
 */
export async function uploadDirect(file: Blob & { name?: string }, purpose: UploadPurpose, onProgress?: (fraction: number) => void): Promise<string> {
  const contentType = contentTypeOf(file)
  const { data } = await api.post<{ key: string; upload_url: string; headers: Record<string, string> }>('/uploads/', { purpose, content_type: contentType, size: file.size })
  await axios.put(data.upload_url, file, {
    headers: { ...data.headers, 'Content-Type': contentType },
    onUploadProgress: (event) => { if (event.total && onProgress) onProgress(event.loaded / event.total) },
  })
  return data.key
}
