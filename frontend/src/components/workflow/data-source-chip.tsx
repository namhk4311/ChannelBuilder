import { cn } from '@/lib/utils'
import type { StepDataSource } from '@/api/workflow'

/** Chip nói rõ step chạy data thật hay giả — điểm minh bạch của demo. */
const SOURCE_MAP: Record<StepDataSource, { label: string; className: string }> = {
  real: { label: 'data thật', className: 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400' },
  sample: { label: 'sample', className: 'border-sky-500/40 text-sky-600 dark:text-sky-400' },
  mock: { label: 'mock', className: 'border-amber-500/40 text-amber-600 dark:text-amber-400' },
  stub: { label: 'stub', className: 'border-border text-muted-foreground' },
}

export function DataSourceChip({ source }: { source: StepDataSource | null }) {
  if (!source) return null
  const s = SOURCE_MAP[source]
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap',
        s.className,
      )}
    >
      {s.label}
    </span>
  )
}
