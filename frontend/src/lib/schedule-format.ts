import type { SchedulePostStatus } from '@/api/publisher'

/**
 * Format dùng chung cho mọi bảng lịch đăng (tab "Lịch đăng" + thẻ lịch trong Chat)
 * → badge trạng thái + giờ hẹn hiển thị ĐỒNG NHẤT, không lệch giữa các nơi.
 */
export const SCHEDULE_STATUS_BADGE: Record<
  SchedulePostStatus,
  { label: string; className: string }
> = {
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

/** ISO (UTC) → "dd/MM HH:mm" giờ Việt Nam; null → "—". */
export const fmtScheduleTime = (iso: string | null) => (iso ? FMT.format(new Date(iso)) : '—')
