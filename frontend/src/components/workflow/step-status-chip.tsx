import { cn } from '@/lib/utils'
import type { StepStatus } from '@/api/workflow'

/** Pill trạng thái step/run — theme neutral nên dùng palette + dark variant tường minh. */
const STATUS_MAP: Record<StepStatus, { label: string; className: string; pulse?: boolean }> = {
  pending: { label: 'Chờ', className: 'bg-muted text-muted-foreground' },
  running: {
    label: 'Đang chạy',
    className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
    pulse: true,
  },
  ok: { label: 'Xong', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' },
  failed: { label: 'Lỗi', className: 'bg-red-500/10 text-red-600 dark:text-red-400' },
  stub: { label: 'Stub', className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400' },
  awaiting: {
    label: 'Chờ duyệt',
    className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
    pulse: true,
  },
  rejected: { label: 'Từ chối', className: 'bg-red-500/10 text-red-600 dark:text-red-400' },
  skipped: { label: 'Bỏ qua', className: 'bg-muted text-muted-foreground' },
}

export function StepStatusChip({ status, className }: { status: StepStatus; className?: string }) {
  const s = STATUS_MAP[status] ?? STATUS_MAP.pending
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
        s.className,
        className,
      )}
    >
      {s.pulse && <span className="size-1.5 rounded-full bg-current animate-pulse" />}
      {s.label}
    </span>
  )
}
