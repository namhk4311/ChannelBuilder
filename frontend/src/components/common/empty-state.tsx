import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  /** `dashed` → khung viền đứt; `centered` → không viền, chỉ căn giữa. */
  variant?: 'dashed' | 'centered'
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

/** Trạng thái rỗng — thay cho EmptyState của lib cũ. */
export function EmptyState({
  variant = 'dashed',
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 rounded-xl p-8 text-center',
        variant === 'dashed' && 'border border-dashed border-border',
        className,
      )}
    >
      <h3 className="text-base font-semibold text-foreground">{title}</h3>
      {description && (
        <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
