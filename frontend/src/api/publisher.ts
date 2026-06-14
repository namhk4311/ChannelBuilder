import { del, get, post } from '@/lib/api-client'

export interface PublisherStatus {
  /** Đủ env TIKTOK_CLIENT_KEY/SECRET/REDIRECT_URI ở backend. */
  configured: boolean
  /** tokens.json đã có refresh_token — publish được, token tự refresh. */
  connected: boolean
  open_id: string | null
  scope: string | null
  redirect_uri: string | null
}

export interface OAuthExchangeResult extends PublisherStatus {
  status: 'ok' | 'failed'
  error: string | null
}

export const fetchPublisherStatus = () => get<PublisherStatus>('/publisher/status')

export const fetchOAuthUrl = () =>
  get<{ status: 'ok' | 'failed'; url: string | null; error: string | null }>(
    '/publisher/oauth/url',
  )

export const exchangeOAuthCode = (code: string) =>
  post<OAuthExchangeResult>('/publisher/oauth/exchange', { code })

// ─── Queue lịch đăng (scheduled_posts) ───────────────────────────────────────

export type SchedulePostStatus =
  | 'pending'
  | 'publishing'
  | 'published'
  | 'failed'
  | 'skipped_dup'
  | 'skipped_limit'
  | 'blocked_guardrail'
  | 'cancelled'

export interface ScheduledPost {
  id: number
  run_id: string | null
  library: string
  video_object: string
  caption: string
  script: string
  text_hook: string | null
  content_hash: string
  trigger: 'scheduled' | 'on_demand'
  actor: string
  status: SchedulePostStatus
  scheduled_for: string | null
  published_at: string | null
  tiktok_publish_id: string | null
  tiktok_video_id: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface ScheduleBody {
  library: string
  video_object: string
  caption: string
  script: string
  text_hook?: string | null
  run_id?: string | null
  /** ISO UTC. Bỏ trống → backend dùng slot mặc định 9h ngày kế. */
  scheduled_for?: string | null
}

export interface RunNowResult {
  status: 'ok' | 'failed'
  error?: string | null
  published?: number
  skipped?: number
  failed?: number
}

export const schedulePost = (body: ScheduleBody) =>
  post<{ status: 'ok' | 'failed'; error: string | null; warnings?: string[]; post: ScheduledPost | null }>(
    '/publisher/schedule',
    body,
  )

export const listSchedule = (status?: string) =>
  get<{ status: 'ok' | 'failed'; error: string | null; posts: ScheduledPost[] }>(
    '/publisher/schedule',
    status ? { status } : undefined,
  )

export const cancelSchedule = (id: number) =>
  del<{ status: 'ok' | 'failed'; error: string | null; post: ScheduledPost | null }>(
    `/publisher/schedule/${id}`,
  )

export const runScheduleNow = () => post<RunNowResult>('/publisher/schedule/run-now')
