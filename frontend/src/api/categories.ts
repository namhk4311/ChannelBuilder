import { del, get, patch, post } from '@/lib/api-client'
import type { Category } from '@/api/types'

export const fetchCategories = (library: string) => get<Category[]>('/categories', { library })

export const createCategory = (body: {
  name: string
  library: string
  label?: string
  default_tag?: string
  description?: string
}) => post<{ ok: boolean; library: string; name: string; default_tag: string }>('/categories', body)

export const updateCategory = (
  name: string,
  library: string,
  body: { label?: string; default_tag?: string; description?: string },
) =>
  patch<{ ok: boolean }>(
    `/categories/${encodeURIComponent(name)}?library=${encodeURIComponent(library)}`,
    body,
  )

export const deleteCategory = (name: string, library: string) =>
  del<{ ok: boolean }>(
    `/categories/${encodeURIComponent(name)}?library=${encodeURIComponent(library)}`,
  )
