import { del, get, post } from '@/lib/api-client'
import type { GradedVideo, InsightDigest } from './analyst'
import type { SchedulePostStatus } from './publisher'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  /** Mốc pipeline (video dựng xong) → render player ngay trong chat. */
  video_url?: string | null
}

export interface ChatOption {
  value: string | null
  label: string
  hint?: string
}

/** Payload trend (Scout) cho UI bảng xu hướng trong chat. */
export interface ChatTrend {
  digest: Record<string, unknown>
  source: string // 'llm' (TikTok thật) | 'seed' (dữ liệu mẫu)
}

/** Payload Analyst (hiệu suất video đã đăng) — insight + bảng video đã chấm. */
export interface ChatAnalyst {
  insight: InsightDigest
  videos: GradedVideo[]
  batch?: string | null
  scale_ids?: string[]
}

/** 1 dòng lịch đăng rút gọn cho thẻ lịch trong chat (giống tab Lịch đăng). */
export interface ChatSchedulePost {
  id: number
  caption: string
  library: string
  trigger: 'scheduled' | 'on_demand'
  status: SchedulePostStatus
  scheduled_for: string | null
  published_at: string | null
}

/** Payload lịch đăng cho UI bảng video chờ đăng trong chat. */
export interface ChatSchedule {
  posts: ChatSchedulePost[]
  today_only: boolean
  count: number
}

export interface ChatUi {
  /** ask | choices | running | chitchat | trend | analyst | schedule — drive render chips / bảng / progress. */
  kind: string
  field: string | null
  options: ChatOption[]
  /** kind==='trend' → digest Scout để render bảng xu hướng trong chat. */
  trend?: ChatTrend | null
  /** kind==='analyst' → insight + bảng hiệu suất video đã đăng. */
  analyst?: ChatAnalyst | null
  /** kind==='schedule' → danh sách video chờ đăng (bảng giống tab Lịch đăng). */
  schedule?: ChatSchedule | null
}

/** Spec đang gom — mirror PipelineSpec backend. */
export interface ChatSpec {
  topic: string | null
  library: string | null
  n_ideas: number
  subtitles: boolean
  music_track_id: string | null
  beat_sync: boolean
  music_volume: number
  /** Chế độ đăng: 'review_publish' (đăng ngay sau duyệt) | 'schedule' (lên lịch). */
  publish_mode?: string
  /** ISO giờ hẹn khi publish_mode==='schedule'; null → slot mặc định (9h sáng mai). */
  scheduled_for?: string | null
}

export interface ChatSession {
  id: string
  title: string | null
  messages: ChatMessage[]
  spec: ChatSpec
  /** Khi conductor đã start pipeline → poll /api/workflow/runs/{run_id}. */
  run_id: string | null
  ui: ChatUi
  updated_at: string
}

/** 1 dòng trong sidebar lịch sử. */
export interface ChatSessionSummary {
  id: string
  title: string | null
  run_id: string | null
  updated_at: string
}

export const createChatSession = () => post<ChatSession>('/chat/sessions')

export const fetchChatSession = (id: string) => get<ChatSession>(`/chat/sessions/${id}`)

export const listChatSessions = () =>
  get<{ sessions: ChatSessionSummary[] }>('/chat/sessions')

export const deleteChatSession = (id: string) => del<{ ok: boolean }>(`/chat/sessions/${id}`)

/** Ghi mốc pipeline (video / đăng xong / huỷ / lỗi) vào hội thoại — idempotent. */
export const recordRun = (id: string) => post<ChatSession>(`/chat/sessions/${id}/record-run`)

export const sendChatMessage = (id: string, text: string) =>
  post<ChatSession>(`/chat/sessions/${id}/messages`, { text }, { timeout: 0 })
