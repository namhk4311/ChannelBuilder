import { del, get, postForm } from '@/lib/api-client'
import type { MusicTrack, MusicUploadResponse } from '@/api/types'

export const fetchMusic = () => get<MusicTrack[]>('/music')

export const uploadMusic = (form: FormData) => postForm<MusicUploadResponse>('/music', form)

export const deleteMusic = (id: string) =>
  del<{ ok: boolean }>(`/music/${encodeURIComponent(id)}`)
