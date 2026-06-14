import type { ChatMessage } from '@/api/chat'
import { TikTokIcon } from '@/components/icons/tiktok'
import { Markdown } from './markdown'

/** Avatar tròn của Đạo diễn AI — logo TikTok trên nền đen, dùng chung cho message + typing. */
export function DirectorAvatar() {
  return (
    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-black text-white">
      <TikTokIcon className="size-4" />
    </span>
  )
}

/**
 * Một dòng hội thoại kiểu ChatGPT:
 *  - user: bong bóng xám bo tròn, canh phải
 *  - assistant: avatar Đạo diễn + văn bản markdown, full-width
 */
export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap break-words rounded-3xl bg-muted px-4 py-2.5 text-sm text-foreground">
          {message.content}
        </div>
      </div>
    )
  }
  return (
    <div className="flex gap-3">
      <DirectorAvatar />
      <div className="min-w-0 flex-1 pt-0.5 text-foreground">
        <Markdown content={message.content} />
      </div>
    </div>
  )
}
