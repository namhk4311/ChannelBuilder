import { useState } from 'react'
import { Lightbulb, X } from 'lucide-react'
import { toast } from 'sonner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { cn } from '@/lib/utils'
import type { WorkflowRun } from '@/api/workflow'
import { useIdeaDecision } from '@/hooks/use-workflow'

interface Idea {
  title?: string
  angle?: string
  pillar?: string
  est_fit?: number
}

/**
 * Idea gate — pipeline dừng sau khi sinh ý tưởng. User bấm chọn 1 ý → Creative
 * viết kịch bản cho ý đó (thay vì auto chọn est_fit cao nhất).
 */
export function IdeaGate({ run }: { run: WorkflowRun }) {
  const [picked, setPicked] = useState<number | null>(null)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const decision = useIdeaDecision(run.id)

  if (run.status !== 'awaiting_idea') return null
  const step = run.steps.find((s) => s.id === 'idea_approval')
  const ideas = ((step?.output as { ideas?: Idea[] } | null)?.ideas ?? []) as Idea[]

  const choose = (i: number) => {
    setPicked(i)
    decision.mutate(
      { approve: true, ideaIndex: i },
      {
        onSuccess: () => toast.success('Đã chọn ý tưởng — đang viết kịch bản'),
        onError: (e) => {
          setPicked(null)
          toast.error(`Không gửi được: ${e.message}`)
        },
      },
    )
  }

  const reject = () =>
    decision.mutate(
      { approve: false },
      {
        onSuccess: () => toast.info('Đã huỷ ở bước chọn ý tưởng'),
        onError: (e) => toast.error(`Không gửi được: ${e.message}`),
      },
    )

  return (
    <>
      <Alert variant="warning">
        <Lightbulb />
        <AlertTitle>Chọn ý tưởng để dựng video</AlertTitle>
        <AlertDescription>
          <div className="w-full space-y-2">
            <p className="text-sm text-muted-foreground">
              Bấm vào ý tưởng bạn thích — mình sẽ viết kịch bản cho ý đó.
            </p>
            <div className="space-y-2">
              {ideas.map((idea, i) => (
                <button
                  key={i}
                  type="button"
                  disabled={decision.isPending}
                  onClick={() => choose(i)}
                  className={cn(
                    'w-full rounded-lg border p-3 text-left transition-colors disabled:opacity-60',
                    picked === i
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/60 hover:bg-muted/50',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-medium text-foreground">
                      {i + 1}. {idea.title ?? 'Ý tưởng'}
                    </span>
                    {typeof idea.est_fit === 'number' && (
                      <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                        fit {idea.est_fit}
                      </span>
                    )}
                  </div>
                  {idea.angle && <p className="mt-0.5 text-xs text-muted-foreground">{idea.angle}</p>}
                  {idea.pillar && (
                    <span className="mt-1 inline-block text-[11px] text-primary">#{idea.pillar}</span>
                  )}
                </button>
              ))}
            </div>
            <div className="pt-1">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirmCancel(true)}
                disabled={decision.isPending}
              >
                <X /> Huỷ
              </Button>
            </div>
          </div>
        </AlertDescription>
      </Alert>

      <ConfirmDialog
        open={confirmCancel}
        onOpenChange={setConfirmCancel}
        tone="red"
        title="Huỷ ở bước chọn ý tưởng?"
        description="Run sẽ dừng — không dựng video."
        confirmLabel="Huỷ run"
        onConfirm={reject}
        isPending={decision.isPending}
      />
    </>
  )
}
