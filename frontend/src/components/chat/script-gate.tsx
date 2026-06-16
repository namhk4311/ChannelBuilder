import { useState } from 'react'
import { Check, FileText, Pencil, RefreshCw, X } from 'lucide-react'
import { toast } from 'sonner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import type { QcVerdict, WorkflowRun } from '@/api/workflow'
import { useScriptDecision } from '@/hooks/use-workflow'
import { HashtagInput } from '@/components/chat/hashtag-input'
import { QcVerdictCard } from '@/components/workflow/qc-verdict-card'

interface ScriptOutput {
  script?: string
  text_hook?: string
  caption?: string
  hashtags?: string[]
  title?: string
  qc_verdict?: QcVerdict | null
  /** Còn lượt cho Creative viết lại theo QC (ẩn nút khi hết lượt CREATIVE_QC_MAX_RETRIES). */
  can_regenerate?: boolean
}

/**
 * Script gate — pipeline dừng sau khi sinh kịch bản. User đọc kịch bản, bấm "Sửa"
 * để chỉnh, rồi "Dùng kịch bản này" → producer dựng video từ bản (đã sửa) này.
 */
export function ScriptGate({ run }: { run: WorkflowRun }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [draftCaption, setDraftCaption] = useState('')
  const [draftHashtags, setDraftHashtags] = useState<string[]>([])
  const [confirmCancel, setConfirmCancel] = useState(false)
  const decision = useScriptDecision(run.id)

  if (run.status !== 'awaiting_script') return null
  const step = run.steps.find((s) => s.id === 'script_approval')
  const out = (step?.output ?? {}) as ScriptOutput
  const script = out.script ?? ''

  const startEdit = () => {
    setDraft(script)
    setDraftCaption(out.caption ?? '')
    setDraftHashtags(out.hashtags ?? [])
    setEditing(true)
  }

  const approve = () =>
    decision.mutate(
      {
        approve: true,
        script: editing ? draft : undefined,
        caption: editing ? draftCaption : undefined,
        hashtags: editing ? draftHashtags : undefined,
      },
      {
        onSuccess: () => toast.success('Đã duyệt kịch bản — đang dựng video'),
        onError: (e) => toast.error(`Không gửi được: ${e.message}`),
      },
    )

  const reject = () =>
    decision.mutate(
      { approve: false },
      {
        onSuccess: () => toast.info('Đã huỷ ở bước kịch bản'),
        onError: (e) => toast.error(`Không gửi được: ${e.message}`),
      },
    )

  const regenerate = () =>
    decision.mutate(
      { approve: false, regenerate: true },
      {
        onSuccess: () => toast.success('Đang cho Creative viết lại theo cảnh báo QC…'),
        onError: (e) => toast.error(`Không gửi được: ${e.message}`),
      },
    )

  // Nút "viết lại" chỉ hiện khi QC có cảnh báo VÀ còn lượt viết lại (backend bơm can_regenerate).
  const canRegenerate = !!out.can_regenerate && (out.qc_verdict?.issues?.length ?? 0) > 0

  return (
    <>
      <Alert variant="warning">
        <FileText />
        <AlertTitle>Duyệt kịch bản trước khi dựng video</AlertTitle>
        <AlertDescription>
          <div className="w-full space-y-2.5">
            {/* QC verdict — soi clip/cụt/hook trước khi dựng; human quyết sửa/retry. */}
            <QcVerdictCard verdict={out.qc_verdict} />
            {out.title && (
              <p>
                <span className="text-muted-foreground">Ý tưởng:</span>{' '}
                <span className="font-medium text-foreground">{out.title}</span>
              </p>
            )}
            {out.text_hook && (
              <p>
                <span className="text-muted-foreground">Hook:</span>{' '}
                <span className="font-medium text-foreground">{out.text_hook}</span>
              </p>
            )}

            <div className="space-y-1">
              <span className="text-xs uppercase tracking-wide text-muted-foreground">Lời thoại</span>
              {editing ? (
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={6}
                  className="w-full text-sm"
                  autoFocus
                />
              ) : (
                <p className="whitespace-pre-wrap rounded-lg border border-border bg-background/60 p-3 text-sm text-foreground">
                  {script || '—'}
                </p>
              )}
            </div>

            <div className="space-y-1">
              <span className="text-xs uppercase tracking-wide text-muted-foreground">Caption</span>
              {editing ? (
                <Textarea
                  value={draftCaption}
                  onChange={(e) => setDraftCaption(e.target.value)}
                  rows={3}
                  className="w-full text-sm"
                  placeholder="Caption khi đăng…"
                />
              ) : (
                <p className="text-sm text-foreground">
                  {out.caption || '—'}
                  {out.hashtags?.length ? (
                    <span className="text-primary"> {out.hashtags.join(' ')}</span>
                  ) : null}
                </p>
              )}
            </div>

            {editing && (
              <div className="space-y-1">
                <span className="text-xs uppercase tracking-wide text-muted-foreground">Hashtag</span>
                <HashtagInput value={draftHashtags} onChange={setDraftHashtags} />
              </div>
            )}

            <div className="flex flex-wrap gap-2 pt-1">
              {!editing ? (
                <Button size="sm" variant="outline" onClick={startEdit} disabled={decision.isPending}>
                  <Pencil /> Sửa
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setEditing(false)}
                  disabled={decision.isPending}
                >
                  Huỷ sửa
                </Button>
              )}
              {canRegenerate && !editing && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={regenerate}
                  disabled={decision.isPending}
                >
                  <RefreshCw /> Cho Creative viết lại
                </Button>
              )}
              <Button size="sm" onClick={approve} disabled={decision.isPending}>
                <Check /> Dùng kịch bản này
              </Button>
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
        title="Huỷ ở bước kịch bản?"
        description="Run sẽ dừng — không dựng video, các bước sau bị bỏ qua."
        confirmLabel="Huỷ run"
        onConfirm={reject}
        isPending={decision.isPending}
      />
    </>
  )
}
