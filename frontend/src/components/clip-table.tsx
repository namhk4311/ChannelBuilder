import { useMemo, useState } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { toast } from 'sonner'
import type { Clip } from '@/api/types'
import { useDeleteVideo } from '@/hooks/use-videos'
import { ClipTablePagination } from '@/components/clip-table-pagination'
import { EditClipDialog } from '@/components/edit-clip-dialog'

// A23c — đúng 3 lựa chọn page size
const PAGE_SIZES = [10, 20, 50]

interface ClipTableProps {
  library: string
  clips: Clip[]
}

/** Bảng kho clip — desktop Table, mobile stacked list, pagination client-side. */
export function ClipTable({ library, clips }: ClipTableProps) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0])
  const [editing, setEditing] = useState<Clip | null>(null)
  const [deleting, setDeleting] = useState<Clip | null>(null)
  const remove = useDeleteVideo(library)

  const pageCount = Math.max(1, Math.ceil(clips.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const rows = useMemo(
    () => clips.slice((safePage - 1) * pageSize, safePage * pageSize),
    [clips, safePage, pageSize],
  )

  const handleDelete = () =>
    remove.mutate(deleting!.id, {
      onSuccess: () => {
        toast.success(`Đã xoá clip ${deleting!.id}`)
        setDeleting(null)
      },
      onError: (e) => toast.error(`Không xoá được: ${e.message}`),
    })

  const actions = (clip: Clip) => (
    <div className="flex justify-end gap-1">
      <Button variant="ghost" size="icon-sm" aria-label="Sửa clip" onClick={() => setEditing(clip)}>
        <Pencil />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        className="text-destructive"
        aria-label="Xoá clip"
        onClick={() => setDeleting(clip)}
      >
        <Trash2 />
      </Button>
    </div>
  )

  const paginationRow = (
    <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 border-t border-border px-4 py-3">
      <div className="hidden md:flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Số dòng / trang</span>
        <Select
          value={String(pageSize)}
          onValueChange={(v) => {
            setPageSize(Number(v))
            setPage(1)
          }}
        >
          <SelectTrigger className="w-20" size="sm" aria-label="Số dòng mỗi trang">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZES.map((n) => (
              <SelectItem key={n} value={String(n)}>
                {n}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <ClipTablePagination page={safePage} pageCount={pageCount} onPageChange={setPage} />
    </div>
  )

  return (
    <>
      {/* Desktop: Table + pagination trong CÙNG 1 Card (A23f) */}
      <Card className="hidden md:block overflow-hidden p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Clip</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Mood</TableHead>
              <TableHead className="text-right">Thời lượng</TableHead>
              <TableHead>Độ phân giải</TableHead>
              <TableHead>Người</TableHead>
              <TableHead className="text-right">Hành động</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((clip) => (
              <TableRow key={clip.id}>
                <TableCell className="max-w-64">
                  <div className="font-medium text-foreground truncate">{clip.file}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {clip.description || clip.id}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{clip.clip_tag || clip.category}</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">{clip.mood || '—'}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {clip.duration_sec.toFixed(1)}s
                </TableCell>
                <TableCell className="text-muted-foreground">{clip.resolution || '—'}</TableCell>
                <TableCell className="text-muted-foreground">
                  {clip.has_people ? 'Có' : 'Không'}
                </TableCell>
                <TableCell>{actions(clip)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {paginationRow}
      </Card>

      {/* Mobile: stacked list + pagination đơn giản trong cùng Card (A23e/A23b) */}
      <Card className="block md:hidden overflow-hidden p-0">
        <ul className="divide-y divide-border">
          {rows.map((clip) => (
            <li key={clip.id} className="p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 space-y-1">
                  <div className="font-medium text-foreground truncate">{clip.file}</div>
                  <div className="text-sm text-muted-foreground">
                    {clip.duration_sec.toFixed(1)}s · {clip.mood || 'chưa có mood'} ·{' '}
                    {clip.has_people ? 'có người' : 'không người'}
                  </div>
                  <Badge variant="secondary">{clip.clip_tag || clip.category}</Badge>
                </div>
                {actions(clip)}
              </div>
            </li>
          ))}
        </ul>
        <div className="flex items-center justify-between gap-3 border-t border-border px-4 py-3">
          <Button
            variant="outline"
            size="sm"
            disabled={safePage <= 1}
            onClick={() => setPage(safePage - 1)}
          >
            Trước
          </Button>
          <span className="text-sm text-muted-foreground">
            Trang {safePage} / {pageCount}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={safePage >= pageCount}
            onClick={() => setPage(safePage + 1)}
          >
            Sau
          </Button>
        </div>
      </Card>

      <EditClipDialog
        library={library}
        clip={editing}
        onOpenChange={(open) => !open && setEditing(null)}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        tone="red"
        icon={Trash2}
        title={`Xoá clip “${deleting?.file}”?`}
        description="Xoá cả record DB lẫn file trên MinIO — không hoàn tác được."
        confirmLabel="Xoá"
        cancelLabel="Huỷ"
        onConfirm={handleDelete}
        isPending={remove.isPending}
      />
    </>
  )
}
