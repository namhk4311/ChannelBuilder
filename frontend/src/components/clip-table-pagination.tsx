import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'

/** Cửa sổ số trang: 1 … (p-1, p, p+1) … N. */
function pageWindow(page: number, pageCount: number): (number | 'gap')[] {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, i) => i + 1)
  const middle = [page - 1, page, page + 1].filter((p) => p > 1 && p < pageCount)
  const out: (number | 'gap')[] = [1]
  if (middle[0] > 2) out.push('gap')
  out.push(...middle)
  if (middle[middle.length - 1] < pageCount - 1) out.push('gap')
  out.push(pageCount)
  return out
}

interface ClipTablePaginationProps {
  page: number
  pageCount: number
  onPageChange: (page: number) => void
}

/** Numbered pagination cho desktop — compose từ primitives của lib. */
export function ClipTablePagination({ page, pageCount, onPageChange }: ClipTablePaginationProps) {
  const go = (p: number) => (e: React.MouseEvent) => {
    e.preventDefault()
    if (p >= 1 && p <= pageCount && p !== page) onPageChange(p)
  }

  return (
    <Pagination className="hidden md:flex justify-end">
      <PaginationContent>
        <PaginationItem>
          <PaginationPrevious href="#" aria-disabled={page <= 1} onClick={go(page - 1)} />
        </PaginationItem>
        {pageWindow(page, pageCount).map((p, i) =>
          p === 'gap' ? (
            <PaginationItem key={`gap-${i}`}>
              <PaginationEllipsis />
            </PaginationItem>
          ) : (
            <PaginationItem key={p}>
              <PaginationLink href="#" isActive={p === page} onClick={go(p)}>
                {p}
              </PaginationLink>
            </PaginationItem>
          ),
        )}
        <PaginationItem>
          <PaginationNext href="#" aria-disabled={page >= pageCount} onClick={go(page + 1)} />
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  )
}
