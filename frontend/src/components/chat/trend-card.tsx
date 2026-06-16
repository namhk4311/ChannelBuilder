import { TrendingUp } from 'lucide-react'
import type { ChatTrend } from '@/api/chat'
import { StepOutput } from '@/components/workflow/step-output'

/**
 * Bảng xu hướng (Scout) hiển thị trong khung chat khi agent trả lời câu hỏi về trend.
 * Tái dùng StepOutput (renderer của scan_trends ở panel pipeline) để bảng đồng nhất —
 * truyền output dạng scout_result {digest, source}; StepOutput tự ẩn source + render digest.
 */
export function TrendCard({ trend }: { trend: ChatTrend }) {
  const src = trend.source === 'llm' ? 'TikTok thật' : 'dữ liệu mẫu'
  return (
    <div className="rounded-xl border border-border bg-background p-3 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <TrendingUp className="size-4 text-primary" aria-hidden />
        <h4 className="text-sm font-semibold text-foreground">Xu hướng thị trường (Scout)</h4>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          nguồn: {src}
        </span>
      </div>
      <StepOutput tool="scan_trends" output={{ digest: trend.digest, source: trend.source }} />
    </div>
  )
}
