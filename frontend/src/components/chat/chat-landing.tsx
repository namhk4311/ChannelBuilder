import { BarChart3, CalendarClock, Clapperboard, Megaphone, type LucideIcon } from 'lucide-react'
import { DirectorMascot } from '@/components/icons/director-mascot'
import { cn } from '@/lib/utils'

/** 1 gợi ý mở đầu — bấm vào sẽ gửi `prompt` như tin nhắn user (giống starter chip cũ). */
interface Suggestion {
  icon: LucideIcon
  title: string
  desc: string
  prompt: string
}

/** 4 gợi ý khớp đúng các intent chat hỗ trợ: 2 luồng dựng video + Analyst + Lịch đăng. */
const SUGGESTIONS: Suggestion[] = [
  {
    icon: Clapperboard,
    title: 'Vlog clip có sẵn',
    desc: 'Dựng video TikTok từ kho clip của bạn',
    prompt: '🎬 Vlog clip có sẵn',
  },
  {
    icon: Megaphone,
    title: 'Video thông tin',
    desc: 'Tạo video thông tin có giọng đọc',
    prompt: '📢 Video thông tin',
  },
  {
    icon: BarChart3,
    title: 'Hiệu suất video',
    desc: 'Xem phân tích các video đã đăng',
    prompt: 'Cho mình xem hiệu suất các video đã đăng gần đây',
  },
  {
    icon: CalendarClock,
    title: 'Lịch đăng',
    desc: 'Video nào đang chờ đăng hôm nay',
    prompt: 'Hôm nay có video nào đang chờ đăng?',
  },
]

interface ChatLandingProps {
  onPick: (text: string) => void
  disabled?: boolean
}

/**
 * Landing page riêng cho tab Chat — hiện khi cuộc còn trống (chưa có tin nhắn
 * user / chưa start pipeline). Hero mascot + 4 thẻ gợi ý, bấm thẻ = gửi prompt.
 */
export function ChatLanding({ onPick, disabled }: ChatLandingProps) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-2 py-8 text-center">
      {/* Hero mascot trong khối bo tròn mềm */}
      <span className="mb-7 grid size-20 place-items-center rounded-3xl bg-orange-50 shadow-sm">
        <DirectorMascot className="size-12" />
      </span>

      <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
        Chào bạn, hôm nay mình dựng video gì nhỉ?
      </h1>
      <p className="mt-3 max-w-xl text-sm text-muted-foreground sm:text-base">
        Đạo diễn AI giúp bạn lên ý tưởng, dựng và đăng video TikTok cho VNG Insider.
      </p>

      {/* Lưới gợi ý: 1 cột (mobile) → 2 (sm) → 4 (lg) */}
      <div className="mt-9 grid w-full grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {SUGGESTIONS.map((s) => {
          const Icon = s.icon
          return (
            <button
              key={s.title}
              type="button"
              disabled={disabled}
              onClick={() => onPick(s.prompt)}
              className={cn(
                'group flex flex-col rounded-2xl border border-border bg-card p-4 text-left shadow-sm transition',
                'hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                'disabled:pointer-events-none disabled:opacity-60',
              )}
            >
              <span className="mb-4 grid size-11 place-items-center rounded-xl bg-orange-50 text-orange-600 transition group-hover:bg-orange-100">
                <Icon className="size-5" aria-hidden />
              </span>
              <span className="text-sm font-semibold text-foreground">{s.title}</span>
              <span className="mt-1 text-xs leading-relaxed text-muted-foreground">{s.desc}</span>
            </button>
          )
        })}
      </div>

      <p className="mt-8 text-xs text-muted-foreground">
        Chọn một gợi ý hoặc gõ yêu cầu của bạn bên dưới
      </p>
    </div>
  )
}
