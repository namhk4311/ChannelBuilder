import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { QcCheckStatus, QcIssueType, QcVerdict } from '@/api/workflow'

/**
 * Card QC kịch bản cho non-tech: badge tổng (đạt / N cảnh báo) + danh sách issue
 * (màu theo severity, nhãn type tiếng Việt, where + detail + gợi ý sửa).
 * Dùng ở 2 nơi: bước `qc_script` trong timeline + gate duyệt kịch bản (Chat tab).
 */

const TYPE_LABELS: Record<QcIssueType, string> = {
  clip_missing: 'Thiếu clip',
  clip_coverage: 'Clip không đủ phủ câu',
  script_cut: 'Kịch bản cụt',
  hook_weak: 'Hook yếu',
  flow: 'Mạch / nội dung',
  clip_mismatch: 'Clip lệch ý câu',
}

function checkLabel(s?: QcCheckStatus): string {
  return s === 'pass' ? 'đạt' : s === 'warn' ? 'có cảnh báo' : 'bỏ qua'
}

export function QcVerdictCard({ verdict }: { verdict?: QcVerdict | null }) {
  if (!verdict) return null
  const issues = verdict.issues ?? []
  const pass = verdict.verdict === 'pass'
  const nErr = issues.filter((i) => i.severity === 'error').length
  const allSkipped =
    verdict.checks?.deterministic === 'skipped' && verdict.checks?.llm === 'skipped'

  return (
    <div
      className={cn(
        'space-y-2 rounded-lg border p-3',
        pass ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-primary/40 bg-primary/5',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {pass ? (
          <CheckCircle2 className="size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
        ) : (
          <AlertTriangle className="size-4 shrink-0 text-primary" />
        )}
        <span className="text-sm font-semibold text-foreground">
          {pass
            ? 'Kịch bản đạt QC'
            : `QC: ${issues.length} cảnh báo${nErr ? ` · ${nErr} lỗi nặng` : ''}`}
        </span>
        <span className="ml-auto flex flex-wrap gap-1">
          <Badge
            variant="outline"
            className="text-[11px] font-normal"
            title="Kiểm tự động (deterministic, 0 quota): clip có trong kho không, có đủ phủ câu không, câu cụt / hook yếu."
          >
            Kiểm tự động: {checkLabel(verdict.checks?.deterministic)}
          </Badge>
          <Badge
            variant="outline"
            className="text-[11px] font-normal"
            title="AI đánh giá (LLM): chất lượng hook, mạch kể có trôi không, clip có khớp ý lời thoại không. Tắt được bằng CREATIVE_QC_USE_LLM=false."
          >
            AI đánh giá: {checkLabel(verdict.checks?.llm)}
          </Badge>
        </span>
      </div>

      {issues.length > 0 && (
        <ul className="space-y-1.5">
          {issues.map((it, i) => (
            <li key={i} className="flex gap-2 text-xs">
              {it.severity === 'error' ? (
                <XCircle className="mt-0.5 size-3.5 shrink-0 text-destructive" />
              ) : (
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-500" />
              )}
              <div className="min-w-0 space-y-0.5">
                <p>
                  <span className="font-medium text-foreground">
                    {TYPE_LABELS[it.type] ?? it.type}
                  </span>
                  {it.where && <span className="text-muted-foreground"> · {it.where}</span>}
                </p>
                {it.detail && <p className="text-muted-foreground">{it.detail}</p>}
                {it.suggested_fix && (
                  <p className="text-foreground">
                    <span className="text-muted-foreground">Gợi ý: </span>
                    {it.suggested_fix}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {allSkipped && issues.length === 0 && (
        <p className="text-xs text-muted-foreground">
          QC bỏ qua (không truy cập được kho clip / LLM) — human tự duyệt.
        </p>
      )}
    </div>
  )
}
