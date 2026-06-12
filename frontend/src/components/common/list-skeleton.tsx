import { Skeleton } from '@/components/ui/skeleton'

interface ListSkeletonProps {
  rows?: number
}

/** Skeleton dạng danh sách khi đang tải. */
export function ListSkeleton({ rows = 5 }: ListSkeletonProps) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Đang tải…">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-12 w-full rounded-lg" />
      ))}
    </div>
  )
}
