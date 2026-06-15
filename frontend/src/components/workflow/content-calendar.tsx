import { CalendarClock, PlayCircle, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/common/empty-state'
import { cn } from '@/lib/utils'
import type { SchedulePostStatus } from '@/api/publisher'
import { useCancelSchedule, useRunScheduleNow, useSchedule } from '@/hooks/use-publisher'

const STATUS_BADGE: Record<SchedulePostStatus, { label: string; className: string }> = {
  pending: { label: 'Chờ đăng', className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400' },
  publishing: { label: 'Đang đăng', className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400' },
  published: {
    label: 'Đã đăng',
    className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  },
  failed: { label: 'Lỗi', className: 'bg-red-500/10 text-red-600 dark:text-red-400' },
  skipped_dup: { label: 'Trùng', className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400' },
  skipped_limit: {
    label: 'Quá giới hạn',
    className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  },
  blocked_guardrail: {
    label: 'Chặn (guardrail)',
    className: 'bg-red-500/10 text-red-600 dark:text-red-400',
  },
  cancelled: { label: 'Đã huỷ', className: 'bg-muted text-muted-foreground' },
}

const FMT = new Intl.DateTimeFormat('vi-VN', {
  timeZone: 'Asia/Saigon',
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})
const fmtTime = (iso: string | null) => (iso ? FMT.format(new Date(iso)) : '—')

/**
 * Content Calendar — bảng bài đã/đang/sẽ đăng (đọc từ scheduled_posts). Poll 5s
 * để thấy tick tự đăng tới giờ. Nút "Chạy lịch ngay" để demo không cần đợi poller.
 */
export function ContentCalendar() {
  const schedule = useSchedule()
  const cancel = useCancelSchedule()
  const runNow = useRunScheduleNow()
  const posts = schedule.data ?? []

  const handleRunNow = () =>
    runNow.mutate(undefined, {
      onSuccess: (r) =>
        r.status === 'failed'
          ? toast.error(`Chạy lịch lỗi: ${r.error}`)
          : toast.success(`Chạy lịch: ${r.published} đăng · ${r.skipped} bỏ qua · ${r.failed} lỗi`),
      onError: (e) => toast.error(`Không chạy được lịch: ${e.message}`),
    })

  const handleCancel = (id: number) =>
    cancel.mutate(id, {
      onSuccess: (r) =>
        r.status === 'ok'
          ? toast.success('Đã huỷ bài')
          : toast.error(r.error ?? 'Huỷ thất bại'),
      onError: (e) => toast.error(`Không huỷ được: ${e.message}`),
    })

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <CalendarClock className="size-4 text-muted-foreground" />
            <h3 className="text-base font-semibold text-foreground">Lịch đăng</h3>
          </div>
          <Button size="sm" variant="outline" onClick={handleRunNow} disabled={runNow.isPending}>
            <PlayCircle /> Chạy lịch ngay
          </Button>
        </div>

        {schedule.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : posts.length === 0 ? (
          <EmptyState
            variant="dashed"
            title="Chưa có bài nào trong lịch"
            description="Tại gate, chọn “Lên lịch” để thêm bài vào đây, hoặc “Đăng ngay” để đăng tức thì."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Giờ hẹn</TableHead>
                <TableHead>Caption</TableHead>
                <TableHead>Nguồn</TableHead>
                <TableHead>Trạng thái</TableHead>
                <TableHead className="text-right">Thao tác</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {posts.map((p) => {
                const badge = STATUS_BADGE[p.status] ?? STATUS_BADGE.pending
                return (
                  <TableRow key={p.id}>
                    <TableCell className="whitespace-nowrap">
                      {fmtTime(p.scheduled_for ?? p.published_at)}
                    </TableCell>
                    <TableCell className="max-w-xs truncate" title={p.caption}>
                      {p.caption}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {p.trigger === 'scheduled' ? 'Lên lịch' : 'Đăng ngay'}
                    </TableCell>
                    <TableCell>
                      <span
                        className={cn(
                          'inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
                          badge.className,
                        )}
                      >
                        {badge.label}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      {p.status === 'pending' ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleCancel(p.id)}
                          disabled={cancel.isPending}
                        >
                          <Trash2 /> Huỷ
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
