import { useEffect, useState } from 'react'
import { Timer } from 'lucide-react'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import type { QcVerdict, RunStep } from '@/api/workflow'
import type { AnalyzeResult, InsightDigest } from '@/api/analyst'
import { AnalystStepOutput } from '@/components/workflow/analyst-step-output'
import { InsightBlock } from '@/components/workflow/analyst-insight-block'
import { QcVerdictCard } from '@/components/workflow/qc-verdict-card'
import { StepOutput } from '@/components/workflow/step-output'
import { StepStatusChip } from '@/components/workflow/step-status-chip'

/** Body output 1 step: [E] dùng bảng graded riêng; [★] QC dùng card verdict; [B] hiện insight đã nạp. */
function StepBody({ step }: { step: RunStep }) {
  const out = step.output
  if (step.tool === 'analyze_batch' && Array.isArray((out as AnalyzeResult)?.videos)) {
    return <AnalystStepOutput output={out as AnalyzeResult} />
  }
  if (step.tool === 'qc_script') {
    return <QcVerdictCard verdict={(out as { qc_verdict?: QcVerdict })?.qc_verdict} />
  }
  const usedInsight =
    step.tool === 'generate_ideas'
      ? (out as { used_insight?: InsightDigest })?.used_insight
      : undefined
  return (
    <div className="space-y-3">
      {usedInsight && (
        <InsightBlock
          digest={usedInsight}
          title={`Creative đã học từ Analyst — batch ${usedInsight.batch}`}
        />
      )}
      <StepOutput tool={step.tool} output={out} />
    </div>
  )
}

function fmtElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const sec = ms / 1000
  if (sec < 60) return `${sec.toFixed(1)}s`
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}m ${s.toString().padStart(2, '0')}s`
}

/**
 * Stopwatch theo step: đang chạy thì đếm live từ started_at → now (tick 100ms);
 * step xong thì chốt ở khoảng started_at → ended_at.
 */
function StepTimer({ step }: { step: RunStep }) {
  const live = !!step.started_at && !step.ended_at
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!live) return
    const id = setInterval(() => setNow(Date.now()), 100)
    return () => clearInterval(id)
  }, [live])

  if (!step.started_at) return null
  const end = step.ended_at ? new Date(step.ended_at).getTime() : now
  const ms = Math.max(0, end - new Date(step.started_at).getTime())

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 text-xs tabular-nums',
        live ? 'text-primary' : 'text-muted-foreground',
      )}
    >
      {live ? (
        <span className="size-1.5 animate-pulse rounded-full bg-primary" />
      ) : (
        <Timer className="size-3" />
      )}
      {fmtElapsed(ms)}
    </span>
  )
}

// Thứ tự chuẩn của pipeline — sort phòng hờ data về không đúng thứ tự.
const STEP_ORDER = [
  'scan_trends', 'generate_ideas', 'idea_approval', 'generate_script', 'qc_script', 'script_approval',
  'produce_video', 'human_approval', 'publish_video', 'get_video_metrics', 'analyze_batch',
]
const HIDDEN_STEPS = new Set(['idea_approval', 'human_approval', 'script_approval'])
const stepRank = (id: string) => {
  const i = STEP_ORDER.indexOf(id)
  return i === -1 ? 999 : i
}

/**
 * Timeline step của 1 run — mỗi step expand được để xem output (bảng / JSON).
 * Step đang chạy hiển thị stopwatch live; Producer kèm progress bar % từ job 6 bước.
 * `ordinal`: badge đánh số 1→N theo thứ tự (thay code agent lặp A/B/B/C/D/D).
 */
export function RunStepList({ steps, ordinal }: { steps: RunStep[]; ordinal?: boolean }) {
  // Ẩn 2 gate khỏi timeline — gate có UI riêng (ScriptGate / ApprovalGate card).
  // Sort theo thứ tự chuẩn để luôn A→B→C→D dù data về lệch.
  const visibleSteps = steps
    .filter((s) => !HIDDEN_STEPS.has(s.id))
    .slice()
    .sort((a, b) => stepRank(a.id) - stepRank(b.id))

  // Tự bung bước [E] Analyst khi chạy xong để show ngay bảng + insight + đề xuất SCALE
  // (vẫn giữ các toggle thủ công của user).
  const [open, setOpen] = useState<string[]>([])
  const analystDone = steps.some((s) => s.id === 'analyze_batch' && s.status === 'ok')
  useEffect(() => {
    if (analystDone) setOpen((prev) => (prev.includes('analyze_batch') ? prev : [...prev, 'analyze_batch']))
  }, [analystDone])

  return (
    <Accordion type="multiple" value={open} onValueChange={setOpen} className="w-full">
      {visibleSteps.map((step, i) => {
        const expandable = step.output != null || step.error != null
        const showProgress = step.status === 'running' && step.progress != null
        return (
          <AccordionItem key={step.id} value={step.id} disabled={!expandable}>
            <AccordionTrigger className="py-3 min-w-0">
              <div className="flex flex-1 items-center gap-3 min-w-0 pr-2">
                <span className="inline-flex items-center justify-center size-7 rounded-md bg-primary/10 text-primary text-xs font-semibold shrink-0">
                  {ordinal ? i + 1 : step.code}
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
                  <StepTimer step={step} />
                  <StepStatusChip status={step.status} />
                </div>
              </div>
            </AccordionTrigger>
            {expandable && (
              <AccordionContent>
                <div className="space-y-2">
                  {step.error && <p className="text-sm text-destructive">Lỗi: {step.error}</p>}
                  {step.output != null && <StepBody step={step} />}
                </div>
              </AccordionContent>
            )}
          </AccordionItem>
        )
      })}
    </Accordion>
  )
}
