import { get, post } from '@/lib/api-client'
import type { ProduceJob } from '@/api/types'

/** Start job nền — trả job_id ngay, FE poll status. */
export const startProduce = (body: { script: string; subtitles: boolean; library: string }) =>
  post<{ job_id: string }>('/produce', body)

export const fetchProduceStatus = (jobId: string) =>
  get<ProduceJob>(`/produce/status/${encodeURIComponent(jobId)}`)
