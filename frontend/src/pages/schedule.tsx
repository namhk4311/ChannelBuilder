import { CalendarClock } from 'lucide-react'
import { PageHeader } from '@/components/common/page-header'
import { ContentCalendar } from '@/components/workflow/content-calendar'

/** Trang "Lịch đăng" — calendar bài đã/đang/sẽ đăng (tách riêng khỏi Workflow). */
export default function SchedulePage() {
  return (
    <div className="space-y-6 md:space-y-8">
      <PageHeader
        icon={CalendarClock}
        title="Lịch đăng"
        description="Bài đã/đang/sẽ đăng lên TikTok. Bài lên lịch tự đăng tới giờ; bấm “Chạy lịch ngay” để đăng các bài tới hạn ngay lập tức."
      />
      <ContentCalendar />
    </div>
  )
}
