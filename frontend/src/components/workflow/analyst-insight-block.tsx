import { BrainCircuit } from 'lucide-react'
import type { InsightDigest } from '@/api/analyst'

/**
 * Khối insight digest (thắng / thua / đề xuất). Dùng 2 chỗ:
 *  • bước [E] — insight Analyst SINH ra (đẩy về Creative).
 *  • bước [B] — insight Creative ĐÃ NẠP từ vòng trước (đóng vòng học).
 * Đổi `title` cho khớp ngữ cảnh.
 */
export function InsightBlock({ digest, title }: { digest: InsightDigest; title?: string }) {
  const row = (k: string, v: string) => (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <dt className="shrink-0 text-xs font-medium text-muted-foreground">{k}</dt>
      <dd className="min-w-0 flex-1 text-sm text-foreground">{v || '—'}</dd>
    </div>
  )
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2.5">
      <div className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
        <BrainCircuit className="size-4 text-violet-500" />
        {title ?? 'Insight cho vòng sau (đẩy về Creative)'}
      </div>
      <dl className="space-y-2">
        {row('Thắng — hook', digest.thang.hook_type.join(', '))}
        {row('Thắng — độ dài', digest.thang.do_dai)}
        {row('Thua — hook', digest.thua.hook_type.join(', '))}
        {row('Đề xuất', digest.de_xuat_vong_sau)}
      </dl>
    </div>
  )
}
