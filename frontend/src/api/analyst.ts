import { get, post } from '@/lib/api-client'

/** Nhãn absolute gate: SCALE (nhân) · MONITOR (theo dõi) · KILL (ngừng). */
export type GateLabel = 'SCALE' | 'MONITOR' | 'KILL'

export interface GradedVideo {
  id: string
  chu_de: string
  hook_type: string
  do_dai: number
  views: number
  retention_3s_pct: number
  shares: number
  passA: boolean
  passB: boolean
  label: GateLabel
  reason: string
}

/** insight_digest đẩy về [B] Creative — schema thắng/thua/đề xuất. */
export interface InsightDigest {
  batch: string
  thang: { hook_type: string[]; chu_de: string[]; do_dai: string }
  thua: { hook_type: string[]; chu_de: string[] }
  de_xuat_vong_sau: string
}

export interface AnalyzeResult {
  status: 'ok' | 'failed'
  error?: string | null
  batch: string
  batch_name: string
  threshold: number
  top_k: number
  videos: GradedVideo[]
  insight_digest: InsightDigest
  report: string
  scale_ids: string[]
}

export interface BatchInfo {
  name: string
  label: string
  n_videos: number
}

export interface ConfirmResult {
  status: 'ok' | 'failed'
  error?: string | null
  active_batch: string | null
  scale_ids?: string[]
  insight_digest: InsightDigest | null
}

export interface InsightResult {
  status: 'ok' | 'failed'
  insight_digest: InsightDigest | null
  active_batch: string | null
}

export const fetchBatches = () =>
  get<{ status: string; batches: BatchInfo[] }>('/analyst/batches')

export const analyzeBatch = (batch: string) =>
  post<AnalyzeResult>('/analyst/analyze', { batch })

export const confirmScale = (batch: string, scaleIds?: string[]) =>
  post<ConfirmResult>('/analyst/confirm', { batch, scale_ids: scaleIds })

export const fetchInsight = () => get<InsightResult>('/analyst/insight')
