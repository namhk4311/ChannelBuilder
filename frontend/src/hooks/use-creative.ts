import { useMutation } from '@tanstack/react-query'
import { generateIdeas, generateScript } from '@/api/creative'
import type { Idea, IdeasResponse, ScriptResponse } from '@/api/types'

/**
 * Backend trả HTTP 200 kể cả khi tool failed (pattern "tool không bao giờ raise")
 * → check status trong body và throw để react-query đi vào onError.
 */
function unwrap<T extends { status: 'ok' | 'failed'; error: string | null }>(res: T): T {
  if (res.status !== 'ok') throw new Error(res.error || 'Tool failed')
  return res
}

export function useGenerateIdeas(onDone: (res: IdeasResponse) => void) {
  return useMutation({
    mutationFn: (body: { topic: string; n_ideas?: number; target_duration_sec?: number }) =>
      generateIdeas(body).then(unwrap),
    onSuccess: onDone,
  })
}

export function useGenerateScript(onDone: (res: ScriptResponse) => void) {
  return useMutation({
    mutationFn: (body: { idea: Idea; target_duration_sec?: number }) =>
      generateScript(body).then(unwrap),
    onSuccess: onDone,
  })
}
