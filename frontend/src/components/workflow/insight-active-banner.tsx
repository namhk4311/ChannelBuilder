import { Sparkles } from 'lucide-react'
import { useInsight } from '@/hooks/use-analyst'

/**
 * Banner báo TRƯỚC khi chạy: vòng tới Creative sẽ học từ batch nào (insight đã confirm).
 * Ẩn khi chưa có insight active. Đọc chung cache ['analyst','insight'] với bước [E].
 */
export function InsightActiveBanner() {
  const insight = useInsight()
  const d = insight.data?.insight_digest
  if (!d) return null
  const win = d.thang.hook_type.join(', ') || '—'
  const lose = d.thua.hook_type.join(', ') || '—'
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-violet-500/40 bg-violet-500/5 px-4 py-3 text-sm">
      <Sparkles className="size-4 text-violet-500 shrink-0 mt-0.5" />
      <div className="min-w-0">
        <span className="font-medium text-foreground">Vòng tới sẽ học từ batch {d.batch}</span>
        <span className="text-muted-foreground">
          {' '}
          — Creative ưu tiên hook «{win}», tránh «{lose}».
        </span>
      </div>
    </div>
  )
}
