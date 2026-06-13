import { Copy } from 'lucide-react'
import { toast } from 'sonner'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import type { RunStep } from '@/api/workflow'
import { DataSourceChip } from '@/components/workflow/data-source-chip'
import { StepStatusChip } from '@/components/workflow/step-status-chip'

function stepDuration(step: RunStep): string | null {
  if (!step.started_at || !step.ended_at) return null
  const ms = new Date(step.ended_at).getTime() - new Date(step.started_at).getTime()
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

function copyJson(label: string, value: unknown) {
  navigator.clipboard
    .writeText(JSON.stringify(value, null, 2))
    .then(() => toast.success(`Đã copy output ${label}`))
    .catch(() => toast.error('Không copy được — clipboard bị chặn'))
}

/**
 * Timeline step của 1 run — mỗi step expand được để xem JSON output.
 * Step Producer đang chạy hiển thị progress bar % thật từ job 6 bước.
 */
export function RunStepList({ steps }: { steps: RunStep[] }) {
  return (
    <Accordion type="multiple" className="w-full">
      {steps.map((step) => {
        const duration = stepDuration(step)
        const expandable = step.output != null || step.error != null
        const showProgress = step.status === 'running' && step.progress != null
        return (
          <AccordionItem key={step.id} value={step.id} disabled={!expandable}>
            <AccordionTrigger className="py-3 min-w-0">
              <div className="flex flex-1 items-center gap-3 min-w-0 pr-2">
                <span className="inline-flex items-center justify-center size-7 rounded-md bg-primary/10 text-primary text-xs font-semibold shrink-0">
                  {step.code}
                </span>
                <div className="min-w-0 flex-1 text-left">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-foreground">{step.title}</span>
                    <code className="text-xs text-muted-foreground">{step.tool}</code>
                  </div>
                  {step.summary && (
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{step.summary}</p>
                  )}
                  {showProgress && (
                    <div className="flex items-center gap-2 mt-1.5">
                      <Progress value={step.progress} className="h-1.5 max-w-64" />
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {step.progress}%
                      </span>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {duration && (
                    <span className="text-xs text-muted-foreground tabular-nums hidden sm:inline">
                      {duration}
                    </span>
                  )}
                  <DataSourceChip source={step.data_source} />
                  <StepStatusChip status={step.status} />
                </div>
              </div>
            </AccordionTrigger>
            {expandable && (
              <AccordionContent>
                <div className="space-y-2 pl-10">
                  {step.error && <p className="text-sm text-destructive">Lỗi: {step.error}</p>}
                  {step.output != null && (
                    <div className="relative rounded-lg border border-border bg-muted/50">
                      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
                        <code className="text-xs text-muted-foreground">
                          {step.tool} → output
                        </code>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2"
                          onClick={() => copyJson(step.tool, step.output)}
                        >
                          <Copy /> Copy
                        </Button>
                      </div>
                      <pre className="max-h-80 overflow-auto p-3 text-xs leading-relaxed">
                        {JSON.stringify(step.output, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </AccordionContent>
            )}
          </AccordionItem>
        )
      })}
    </Accordion>
  )
}
