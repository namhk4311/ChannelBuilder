import { BarChart3 } from 'lucide-react'
import type { ChatAnalyst } from '@/api/chat'
import { GradedTable } from '@/components/workflow/analyst-graded-table'
import { InsightBlock } from '@/components/workflow/analyst-insight-block'

/**
 * Thẻ hiệu suất video (Analyst) trong khung chat khi agent trả lời câu hỏi performance.
 * Tái dùng GradedTable + InsightBlock của bước [E] để bảng/insight ĐỒNG NHẤT với tab Workflow —
 * truyền videos đã chấm (SCALE/MONITOR/KILL) + insight digest (thắng/thua/đề xuất).
 */
export function AnalystCard({ analyst }: { analyst: ChatAnalyst }) {
  return (
    <div className="space-y-3 rounded-xl border border-border bg-background p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <BarChart3 className="size-4 text-primary" aria-hidden />
        <h4 className="text-sm font-semibold text-foreground">Hiệu suất video (Analyst)</h4>
        {analyst.batch && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {analyst.batch}
          </span>
        )}
      </div>
      {analyst.videos.length > 0 && <GradedTable videos={analyst.videos} />}
      <InsightBlock digest={analyst.insight} title="Insight từ lô đã đăng" />
    </div>
  )
}
