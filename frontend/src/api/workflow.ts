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

export type RunStatus = 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'rejected'

export type StepStatus =
  | 'pending'
  | 'running'
  | 'ok'
  | 'failed'
  | 'stub'
  | 'awaiting'
  | 'rejected'
  | 'skipped'

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
  status: RunStatus
  created_at: string
  updated_at: string
  gate: { decision: 'approved' | 'rejected' | null; decided_at: string | null }
  steps: RunStep[]
}

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
}

export const fetchAgents = () => get<{ agents: Agent[] }>('/workflow/agents')

export const fetchRuns = () => get<{ runs: RunSummary[] }>('/workflow/runs')

export const fetchRun = (runId: string) => get<WorkflowRun>(`/workflow/runs/${runId}`)

export const startRun = (body: StartRunBody) => post<WorkflowRun>('/workflow/runs', body)

export const decideGate = (runId: string, approve: boolean) =>
  post<WorkflowRun>(`/workflow/runs/${runId}/approval`, { approve })
