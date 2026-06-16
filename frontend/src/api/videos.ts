import { del, get, patch, post, postForm } from '@/lib/api-client'
import type { Clip } from '@/api/types'

export const fetchVideos = (library: string, category?: string) =>
  get<Clip[]>('/videos', { library, ...(category ? { category } : {}) })

export const fetchMoods = () => get<{ moods: string[] }>('/moods')

export interface UploadVideoInput {
  file: File
  library: string
  category: string
  description?: string
  mood?: string
  has_people?: boolean
  notes?: string
}

export function uploadVideo(input: UploadVideoInput) {
  const form = new FormData()
  form.append('file', input.file)
  form.append('library', input.library)
  form.append('category', input.category)
  form.append('description', input.description ?? '')
  form.append('mood', input.mood ?? '')
  form.append('has_people', input.has_people ? 'true' : 'false')
  form.append('notes', input.notes ?? '')
  return postForm<{ id: string; filename: string; duration_sec: number; resolution: string }>(
    '/videos',
    form,
  )
}

export const updateVideo = (
  id: string,
  body: {
    category?: string
    description?: string
    mood?: string
    has_people?: boolean
    notes?: string
  },
) => patch<{ ok: boolean }>(`/videos/${encodeURIComponent(id)}`, body)

export const deleteVideo = (id: string) => del<{ ok: boolean }>(`/videos/${encodeURIComponent(id)}`)

export interface BackfillResult {
  checked: number
  fixed: number
  failed: string[]
}

/** Quét lại thời lượng cho clip đang hiển thị 0.0s (ffprobe lại từ MinIO). */
export const backfillDurations = (library?: string) =>
  post<BackfillResult>('/videos/backfill-durations', library ? { library } : {}, {
    timeout: 0, // tải + ffprobe nhiều clip có thể lâu
  })
