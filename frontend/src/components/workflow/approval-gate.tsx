import { useState } from 'react'
import { Check, ShieldAlert, X } from 'lucide-react'
import { toast } from 'sonner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import type { WorkflowRun } from '@/api/workflow'
import { useGateDecision } from '@/hooks/use-workflow'

interface GateOutput {
  caption?: string
  text_hook?: string
  video_url?: string | null
  duration_sec?: number
}

/**
 * Human gate — nguyên tắc "AI execute, Human decide": pipeline dừng tại đây
 * cho tới khi human duyệt đăng. Có preview video thật từ MinIO khi chạy live.
 */
export function ApprovalGate({ run }: { run: WorkflowRun }) {
  const [confirmReject, setConfirmReject] = useState(false)
  const decision = useGateDecision(run.id)

  if (run.status !== 'awaiting_approval') return null
  const gateStep = run.steps.find((s) => s.id === 'human_approval')
  const preview = (gateStep?.output ?? {}) as GateOutput
  const videoUrl = preview.video_url && /^https?:/.test(preview.video_url) ? preview.video_url : null

  const decide = (approve: boolean) =>
    decision.mutate(approve, {
      onSuccess: () =>
        approve
          ? toast.success('Đã duyệt — Publisher đang đăng video')
          : toast.info('Đã từ chối đăng video'),
      onError: (e) => toast.error(`Không gửi được quyết định: ${e.message}`),
    })

  return (
    <>
      <Alert variant="warning">
        <ShieldAlert />
        <AlertTitle>Chờ human duyệt đăng TikTok</AlertTitle>
        <AlertDescription>
          <div className="space-y-2">
            {preview.text_hook && (
              <p>
                <span className="text-muted-foreground">Text hook:</span>{' '}
                <span className="font-medium text-foreground">{preview.text_hook}</span>
              </p>
            )}
            {preview.caption && (
              <p>
                <span className="text-muted-foreground">Caption:</span> {preview.caption}
              </p>
            )}
            {videoUrl ? (
              <video
                src={videoUrl}
                controls
                preload="metadata"
                className="max-h-72 rounded-lg border border-border"
              />
            ) : (
              <p className="text-xs text-muted-foreground">Không có link video preview.</p>
            )}
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={() => decide(true)} disabled={decision.isPending}>
                <Check /> Duyệt & đăng
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirmReject(true)}
                disabled={decision.isPending}
              >
                <X /> Từ chối
              </Button>
            </div>
          </div>
        </AlertDescription>
      </Alert>

      <ConfirmDialog
        open={confirmReject}
        onOpenChange={setConfirmReject}
        tone="red"
        title="Từ chối đăng video này?"
        description="Run sẽ dừng tại gate — video không được đăng, các bước sau bị bỏ qua."
        confirmLabel="Từ chối đăng"
        onConfirm={() => decide(false)}
        isPending={decision.isPending}
      />
    </>
  )
}
