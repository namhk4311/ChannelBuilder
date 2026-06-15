import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { AnalyzeResult } from '@/api/analyst'
import { GradedTable } from '@/components/workflow/analyst-graded-table'
import { InsightBlock } from '@/components/workflow/analyst-insight-block'
import { useConfirmScale, useInsight } from '@/hooks/use-analyst'

/**
 * Output của bước [E] Analyst trong timeline run — bảng graded + insight + đề xuất SCALE
 * + nút "Xác nhận scale" (đóng vòng học [E]→[B]). Hiển thị inline, không tách card riêng.
 */
export function AnalystStepOutput({ output }: { output: AnalyzeResult }) {
  const confirm = useConfirmScale()
  const insight = useInsight()
  const confirmed = !!output.batch && insight.data?.active_batch === output.batch

  const handleConfirm = () =>
    confirm.mutate(
      { batch: output.batch_name, scaleIds: output.scale_ids },
      {
        onSuccess: () => toast.success('Đã đẩy công thức thắng về Creative cho vòng sau'),
        onError: (e) => toast.error(`Xác nhận lỗi: ${(e as Error).message}`),
      },
    )

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Absolute gate 2 phanh: <b>top 20% lô</b> + <b>ngưỡng tuyệt đối retention_3s</b>. Chỉ ĐỀ
        XUẤT — human bấm “Xác nhận scale” mới đẩy công thức thắng về Creative cho vòng sau.
      </p>
      <div className="text-xs text-muted-foreground">
        Ngưỡng <b>{output.threshold}%</b> · Top lô <b>{output.top_k}</b> video · Tổng{' '}
        <b>{output.videos.length}</b> video
      </div>
      <GradedTable videos={output.videos} />
      <InsightBlock digest={output.insight_digest} />

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-3">
        <div className="text-sm">
          {output.scale_ids.length > 0 ? (
            <>
              Đề xuất <b>SCALE</b>:{' '}
              <span className="font-medium text-emerald-600 dark:text-emerald-400">
                {output.scale_ids.join(', ')}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground">
              Không video nào đạt cả 2 phanh — không nhân gì (chặn best of a bad batch).
            </span>
          )}
        </div>
        {confirmed ? (
          <Badge variant="secondary" className="gap-1 font-normal">
            <Sparkles className="size-3" /> Đã xác nhận — vòng sau đang học
          </Badge>
        ) : (
          <Button
            onClick={handleConfirm}
            disabled={output.scale_ids.length === 0 || confirm.isPending}
          >
            <Sparkles /> {confirm.isPending ? 'Đang đẩy…' : 'Xác nhận scale'}
          </Button>
        )}
      </div>
    </div>
  )
}
