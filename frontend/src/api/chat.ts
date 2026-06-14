import { del, get, post } from '@/lib/api-client'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatOption {
  value: string | null
  label: string
  hint?: string
}

export interface ChatUi {
  /** ask | choices | running | chitchat — drive việc render chips / progress. */
  kind: string
  field: string | null
  options: ChatOption[]
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

export const sendChatMessage = (id: string, text: string) =>
  post<ChatSession>(`/chat/sessions/${id}/messages`, { text }, { timeout: 0 })
