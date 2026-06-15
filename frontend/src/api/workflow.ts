import { get, post } from '@/lib/api-client'

/** Trạng thái build của agent trong kiến trúc A→B→C→D + Orchestrator. */
export type AgentBuildStatus = 'built' | 'planned'

export interface AgentTool {
  name: string
  description: string
}

export interface Agent {
  key: string
  code: string
  name: string
  role: string
  build_status: AgentBuildStatus
  import_error: string | null
  tools: AgentTool[]
}

export type RunStatus =
  | 'running'
  | 'awaiting_idea'
  | 'awaiting_script'
  | 'awaiting_approval'
  | 'completed'
  | 'failed'
  | 'rejected'

export type StepStatus =
  | 'pending'
  | 'running'
  | 'ok'
  | 'failed'
  | 'stub'
  | 'awaiting'
  | 'rejected'
  | 'skipped'
  | 'scheduled'

/** Nguồn data của step: real = chạy thật (LLM/render/đăng/metric);
 *  sample = phân tích trên dataset seed (Scout); stub = agent chưa build/wire. */
export type StepDataSource = 'real' | 'sample' | 'stub'

export interface RunStep {
  id: string
  agent: string
  code: string
  tool: string
  title: string
  status: StepStatus
  started_at: string | null
  ended_at: string | null
  summary: string | null
  output: unknown
  error: string | null
  data_source: StepDataSource | null
  /** Producer job 6 bước có progress % thật; step khác = null. */
  progress: number | null
}

export interface WorkflowRun {
  id: string
  topic: string | null
  library: string
  subtitles: boolean
  /** Chế độ đăng chốt lúc start — gate đọc field này để hiện đúng nút (đăng ngay / lên lịch). */
  publish_mode: PublishMode
  status: RunStatus
  created_at: string
  updated_at: string
  gate: {
    decision: 'now' | 'schedule' | 'reject' | 'approved' | 'rejected' | null
    scheduled_for: string | null
    decided_at: string | null
  }
  steps: RunStep[]
}

/** Quyết định tại human gate: đăng ngay / lên lịch / từ chối. */
export interface GateDecisionBody {
  decision: 'now' | 'schedule' | 'reject'
  /** ISO UTC — chỉ dùng khi decision='schedule'. */
  scheduled_for?: string | null
}

/**
 * Chế độ đăng chọn từ đầu (mục Publisher) — quyết định bước gate hiện gì:
 *  review_publish = kiểm duyệt rồi đăng ngay · schedule = lên lịch đăng.
 */
export type PublishMode = 'review_publish' | 'schedule'

export interface RunSummary {
  id: string
  topic: string | null
  status: RunStatus
  created_at: string
  updated_at: string
  steps: Pick<RunStep, 'id' | 'agent' | 'code' | 'title' | 'status'>[]
}

export interface StartRunBody {
  topic?: string | null
  library: string
  subtitles?: boolean
  n_ideas?: number
  music_track_id?: string | null
  beat_sync?: boolean
  music_volume?: number // 0.05 - 1.0
  review_script?: boolean // dừng gate cho human duyệt/sửa kịch bản (Chat tab)
  publish_mode?: PublishMode // review_publish (đăng ngay) | schedule (lên lịch)
}

export const fetchAgents = () => get<{ agents: Agent[] }>('/workflow/agents')

export const fetchRuns = () => get<{ runs: RunSummary[] }>('/workflow/runs')

export const fetchRun = (runId: string) => get<WorkflowRun>(`/workflow/runs/${runId}`)

export const startRun = (body: StartRunBody) => post<WorkflowRun>('/workflow/runs', body)

export const decideGate = (runId: string, body: GateDecisionBody) =>
  post<WorkflowRun>(`/workflow/runs/${runId}/approval`, body)

export const decideIdea = (runId: string, approve: boolean, ideaIndex?: number) =>
  post<WorkflowRun>(`/workflow/runs/${runId}/idea`, { approve, idea_index: ideaIndex })

export const decideScript = (
  runId: string,
  approve: boolean,
  script?: string,
  caption?: string,
  hashtags?: string[],
) => post<WorkflowRun>(`/workflow/runs/${runId}/script`, { approve, script, caption, hashtags })
