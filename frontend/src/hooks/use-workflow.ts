import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  decideGate,
  decideIdea,
  decideScript,
  fetchAgents,
  fetchInfoOptions,
  fetchRun,
  fetchRuns,
  regenerateScript,
  startRun,
  type GateDecisionBody,
  type WorkflowRun,
} from '@/api/workflow'

const ACTIVE_STATUSES = ['running', 'awaiting_idea', 'awaiting_script', 'awaiting_approval']

export function useAgents() {
  return useQuery({
    queryKey: ['workflow', 'agents'],
    queryFn: fetchAgents,
    select: (d) => d.agents,
    staleTime: 60_000,
  })
}

/** Option cho form "Video thông tin" — gần như tĩnh nên staleTime dài. */
export function useInfoOptions() {
  return useQuery({
    queryKey: ['workflow', 'info-options'],
    queryFn: fetchInfoOptions,
    staleTime: 5 * 60_000,
  })
}

export function useRuns() {
  return useQuery({
    queryKey: ['workflow', 'runs'],
    queryFn: fetchRuns,
    select: (d) => d.runs,
  })
}

/** Poll run đang chạy mỗi 1.5s; dừng poll khi run kết thúc. */
export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ['workflow', 'run', runId],
    queryFn: () => fetchRun(runId!),
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && ACTIVE_STATUSES.includes(status) ? 1500 : false
    },
  })
}

export function useStartRun(onStarted: (run: WorkflowRun) => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: startRun,
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ['workflow', 'runs'] })
      onStarted(run)
    },
  })
}

export function useGateDecision(runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: GateDecisionBody) => decideGate(runId!, body),
    onSuccess: (run) => {
      qc.setQueryData(['workflow', 'run', run.id], run)
      qc.invalidateQueries({ queryKey: ['workflow', 'run', run.id] })
      qc.invalidateQueries({ queryKey: ['workflow', 'runs'] })
      // Lên lịch hoặc đăng ngay đều có thể tạo row mới trong calendar.
      qc.invalidateQueries({ queryKey: ['publisher', 'schedule'] })
    },
  })
}

/** Idea gate: chọn 1 ý tưởng (idea_index) / huỷ. */
export function useIdeaDecision(runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { approve: boolean; ideaIndex?: number }) =>
      decideIdea(runId!, args.approve, args.ideaIndex),
    onSuccess: (run) => {
      qc.setQueryData(['workflow', 'run', run.id], run)
      qc.invalidateQueries({ queryKey: ['workflow', 'run', run.id] })
      qc.invalidateQueries({ queryKey: ['workflow', 'runs'] })
    },
  })
}

/** Script gate: duyệt (kèm bản đã sửa) / cho viết lại (regenerate) / huỷ. */
export function useScriptDecision(runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: {
      approve: boolean
      regenerate?: boolean
      script?: string
      caption?: string
      hashtags?: string[]
    }) =>
      args.regenerate
        ? regenerateScript(runId!)
        : decideScript(runId!, args.approve, args.script, args.caption, args.hashtags),
    onSuccess: (run) => {
      qc.setQueryData(['workflow', 'run', run.id], run)
      qc.invalidateQueries({ queryKey: ['workflow', 'run', run.id] })
      qc.invalidateQueries({ queryKey: ['workflow', 'runs'] })
      // Lên lịch hoặc đăng ngay đều có thể tạo row mới trong calendar.
      qc.invalidateQueries({ queryKey: ['publisher', 'schedule'] })
    },
  })
}
