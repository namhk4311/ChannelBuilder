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
import { SCHEDULE_STATUS_BADGE, fmtScheduleTime } from '@/lib/schedule-format'
import { useCancelSchedule, useRunScheduleNow, useSchedule } from '@/hooks/use-publisher'

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
                const badge = SCHEDULE_STATUS_BADGE[p.status] ?? SCHEDULE_STATUS_BADGE.pending
                return (
                  <TableRow key={p.id}>
                    <TableCell className="whitespace-nowrap">
                      {fmtScheduleTime(p.scheduled_for ?? p.published_at)}
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
