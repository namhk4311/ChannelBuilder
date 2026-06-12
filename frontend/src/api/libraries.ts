import { del, get, patch, post } from '@/lib/api-client'
import type { Library } from '@/api/types'

export const fetchLibraries = () => get<Library[]>('/libraries')

export const createLibrary = (body: { name: string; label?: string; description?: string }) =>
  post<{ ok: boolean; name: string }>('/libraries', body)

export const updateLibrary = (name: string, body: { label?: string; description?: string }) =>
  patch<{ ok: boolean }>(`/libraries/${encodeURIComponent(name)}`, body)

export const deleteLibrary = (name: string) =>
  del<{ ok: boolean }>(`/libraries/${encodeURIComponent(name)}`)
