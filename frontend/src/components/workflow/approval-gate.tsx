import { useState } from 'react'
import { CalendarClock, Check, ShieldAlert, X } from 'lucide-react'
import { toast } from 'sonner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import type { GateDecisionBody, WorkflowRun } from '@/api/workflow'
import { useGateDecision } from '@/hooks/use-workflow'

interface GateOutput {
  caption?: string
  text_hook?: string
  video_url?: string | null
  duration_sec?: number
}

/** datetime-local value (giờ máy) cho 9h sáng ngày KẾ — demo chạy ở Asia/Saigon. */
function defaultSlotLocal(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  d.setHours(9, 0, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * Human gate — "AI execute, Human decide": pipeline dừng tại đây để duyệt.
 * Hành động khớp chế độ đăng đã chốt lúc start (đọc từ `run.publish_mode` — persist
 * trên run nên không reset khi đổi tab/reload):
 *   review_publish → Duyệt & đăng ngay · schedule → chọn giờ + Duyệt & lên lịch.
 * Luôn có "Từ chối". Preview video thật từ MinIO khi chạy live.
 */
export function ApprovalGate({ run }: { run: WorkflowRun }) {
  const [confirmReject, setConfirmReject] = useState(false)
  const [slot, setSlot] = useState(defaultSlotLocal)
  const decision = useGateDecision(run.id)

  if (run.status !== 'awaiting_approval') return null
  const gateStep = run.steps.find((s) => s.id === 'human_approval')
  const preview = (gateStep?.output ?? {}) as GateOutput
  const videoUrl = preview.video_url && /^https?:/.test(preview.video_url) ? preview.video_url : null
  const isSchedule = run.publish_mode === 'schedule'

  const submit = (body: GateDecisionBody, okMsg: string) =>
    decision.mutate(body, {
      onSuccess: () => toast.success(okMsg),
      onError: (e) => toast.error(`Không gửi được quyết định: ${e.message}`),
    })

  return (
    <>
      <Alert variant="warning">
        <ShieldAlert />
        <AlertTitle>Kiểm duyệt trước khi {isSchedule ? 'lên lịch' : 'đăng'}</AlertTitle>
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

            {isSchedule && (
              <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border bg-background/50 p-3">
                <div className="space-y-1">
                  <Label htmlFor="gate-slot" className="text-xs text-muted-foreground">
                    Giờ đăng (giờ Việt Nam)
                  </Label>
                  <Input
                    id="gate-slot"
                    type="datetime-local"
                    value={slot}
                    onChange={(e) => setSlot(e.target.value)}
                    className="w-56"
                  />
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2 pt-1">
              {isSchedule ? (
                <Button
                  size="sm"
                  onClick={() =>
                    submit(
                      { decision: 'schedule', scheduled_for: new Date(slot).toISOString() },
                      'Đã lên lịch đăng video',
                    )
                  }
                  disabled={decision.isPending || !slot}
                >
                  <CalendarClock /> Duyệt &amp; lên lịch
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() => submit({ decision: 'now' }, 'Đã duyệt — Publisher đang đăng video')}
                  disabled={decision.isPending}
                >
                  <Check /> Duyệt &amp; đăng ngay
                </Button>
              )}
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
        onConfirm={() => submit({ decision: 'reject' }, 'Đã từ chối đăng video')}
        isPending={decision.isPending}
      />
    </>
  )
}
