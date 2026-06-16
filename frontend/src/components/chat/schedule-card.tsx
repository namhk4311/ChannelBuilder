import { CalendarClock } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { SCHEDULE_STATUS_BADGE, fmtScheduleTime } from '@/lib/schedule-format'
import type { ChatSchedule } from '@/api/chat'

/**
 * Thẻ "video chờ đăng" trong khung chat — bảng read-only giống tab Lịch đăng
 * (tái dùng badge trạng thái + format giờ chung). today_only → tiêu đề "hôm nay".
 */
export function ScheduleCard({ schedule }: { schedule: ChatSchedule }) {
  const posts = schedule.posts
  const scope = schedule.today_only ? 'hôm nay' : 'đang chờ'

  return (
    <div className="space-y-3 rounded-xl border border-border bg-background p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <CalendarClock className="size-4 text-primary" aria-hidden />
        <h4 className="text-sm font-semibold text-foreground">Lịch đăng</h4>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {scope} · {posts.length} video
        </span>
      </div>

      {posts.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Hiện chưa có video nào {scope === 'hôm nay' ? 'hẹn đăng hôm nay' : 'đang chờ đăng'}.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Giờ hẹn</TableHead>
              <TableHead>Caption</TableHead>
              <TableHead>Nguồn</TableHead>
              <TableHead>Trạng thái</TableHead>
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
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
