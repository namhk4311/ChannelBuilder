import { post } from '@/lib/api-client'
import type { Idea, IdeasResponse, ScriptResponse } from '@/api/types'

/** Cả 2 call đều blocking 30-60s phía backend (streaming MaaS) — timeout phải dài. */
const CREATIVE_TIMEOUT_MS = 180_000

export const generateIdeas = (body: {
  topic: string
  n_ideas?: number
  target_duration_sec?: number
}) => post<IdeasResponse>('/creative/ideas', body, { timeout: CREATIVE_TIMEOUT_MS })

export const generateScript = (body: { idea: Idea; target_duration_sec?: number }) =>
  post<ScriptResponse>('/creative/script', body, { timeout: CREATIVE_TIMEOUT_MS })
