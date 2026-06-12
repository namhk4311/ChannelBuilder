import { ChevronRight, ShieldCheck } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { Agent, RunStep, StepStatus } from '@/api/workflow'
import { StepStatusChip } from '@/components/workflow/step-status-chip'

const PIPELINE_ORDER = ['scout', 'creative', 'producer', 'orchestrator', 'publisher']

/** Gộp trạng thái các step của 1 agent trong run hiện tại thành 1 trạng thái node. */
function agentRunStatus(steps: RunStep[]): StepStatus | null {
  if (!steps.length) return null
  const statuses = steps.map((s) => s.status)
  for (const active of ['running', 'awaiting'] as const) {
    if (statuses.includes(active)) return active
  }
  for (const terminal of ['failed', 'rejected'] as const) {
    if (statuses.includes(terminal)) return terminal
  }
  if (statuses.every((s) => s === 'pending')) return 'pending'
  if (statuses.every((s) => s === 'skipped')) return 'skipped'
  if (statuses.includes('pending')) return 'pending'
  if (statuses.includes('stub')) return 'stub'
  return 'ok'
}

interface PipelineFlowProps {
  agents: Agent[]
  steps?: RunStep[]
}

/**
 * Rail pipeline A→B→C→★gate→D — human gate đứng giữa Producer và Publisher
 * đúng nguyên tắc "AI execute, Human decide". Mobile: cuộn ngang.
 */
export function PipelineFlow({ agents, steps = [] }: PipelineFlowProps) {
  const byKey = new Map(agents.map((a) => [a.key, a]))

  return (
    <Card>
      <CardContent>
        <div className="flex items-center gap-2 overflow-x-auto pb-2 -mb-2">
          {PIPELINE_ORDER.map((key, i) => {
            const nodeSteps = steps.filter((s) => s.agent === key)
            const status = agentRunStatus(nodeSteps)
            const isActive = status === 'running' || status === 'awaiting'

            // Node ★ gate — không phải agent, render compact.
            if (key === 'orchestrator') {
              return (
                <div key={key} className="flex items-center gap-2 shrink-0">
                  <ChevronRight className="size-4 text-muted-foreground shrink-0" />
                  <div
                    className={cn(
                      'rounded-lg border border-dashed border-border bg-card px-3 py-2.5 space-y-1.5',
                      isActive && 'border-solid border-amber-500 ring-1 ring-amber-500',
                    )}
                  >
                    <div className="flex items-center gap-1.5">
                      <ShieldCheck className="size-4 text-amber-600 dark:text-amber-400 shrink-0" />
                      <span className="text-sm font-medium text-foreground whitespace-nowrap">
                        Human gate
                      </span>
                    </div>
                    {status ? (
                      <StepStatusChip status={status} />
                    ) : (
                      <span className="text-xs text-muted-foreground whitespace-nowrap">
                        duyệt trước khi đăng
                      </span>
                    )}
                  </div>
                </div>
              )
            }

            const agent = byKey.get(key)
            if (!agent) return null
            return (
              <div key={key} className="flex items-center gap-2 shrink-0">
                {i > 0 && <ChevronRight className="size-4 text-muted-foreground shrink-0" />}
                <div
                  className={cn(
                    'min-w-[148px] rounded-lg border border-border bg-card px-3 py-2.5 space-y-1.5',
                    isActive && 'border-blue-500 ring-1 ring-blue-500',
                    status === 'failed' && 'border-destructive',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="inline-flex items-center justify-center size-6 rounded-md bg-primary/10 text-primary text-xs font-semibold shrink-0">
                      {agent.code}
                    </span>
                    {agent.build_status === 'planned' && (
                      <span className="text-[11px] text-amber-600 dark:text-amber-400 whitespace-nowrap">
                        chưa wire
                      </span>
                    )}
                  </div>
                  <div className="text-sm font-medium text-foreground">{agent.name}</div>
                  {status ? (
                    <StepStatusChip status={status} />
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {agent.tools.length} tool{agent.tools.length > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          ★ Orchestrator (backend ChannelBuilder) import trực tiếp tool của từng agent và điều
          phối tuần tự — human quyết định ở gate trước khi đăng.
        </p>
      </CardContent>
    </Card>
  )
}
