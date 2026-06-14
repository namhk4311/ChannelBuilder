import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  decideGate,
  decideScript,
  fetchAgents,
  fetchRun,
  fetchRuns,
  startRun,
  type GateDecisionBody,
  type WorkflowRun,
} from '@/api/workflow'

const ACTIVE_STATUSES = ['running', 'awaiting_script', 'awaiting_approval']

export function useAgents() {
  return useQuery({
    queryKey: ['workflow', 'agents'],
    queryFn: fetchAgents,
    select: (d) => d.agents,
    staleTime: 60_000,
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

/** Script gate: duyệt (kèm bản đã sửa) / huỷ. */
export function useScriptDecision(runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { approve: boolean; script?: string }) =>
      decideScript(runId!, args.approve, args.script),
    onSuccess: (run) => {
      qc.setQueryData(['workflow', 'run', run.id], run)
      qc.invalidateQueries({ queryKey: ['workflow', 'run', run.id] })
      qc.invalidateQueries({ queryKey: ['workflow', 'runs'] })
      // Lên lịch hoặc đăng ngay đều có thể tạo row mới trong calendar.
      qc.invalidateQueries({ queryKey: ['publisher', 'schedule'] })
    },
  })
}
