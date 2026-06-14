import { get, post } from '@/lib/api-client'
import type { ProduceJob } from '@/api/types'

export interface ProduceBody {
  script: string
  subtitles: boolean
  library: string
  music_track_id?: string | null
  beat_sync?: boolean
  music_volume?: number // 0.05 - 1.0
}

/** Start job nền — trả job_id ngay, FE poll status. */
export const startProduce = (body: ProduceBody) =>
  post<{ job_id: string }>('/produce', body)

export const fetchProduceStatus = (jobId: string) =>
  get<ProduceJob>(`/produce/status/${encodeURIComponent(jobId)}`)
