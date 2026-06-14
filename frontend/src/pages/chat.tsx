import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Loader2, Plus, Square, Workflow } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useRun } from '@/hooks/use-workflow'
import {
  useChatSession,
  useChatSessions,
  useCreateSession,
  useDeleteSession,
  useSendMessage,
} from '@/hooks/use-chat'
import { useChatStore } from '@/stores/chat-store'
import { DirectorAvatar, MessageBubble } from '@/components/chat/message-bubble'
import { OptionChips } from '@/components/chat/option-chips'
import { HistorySidebar } from '@/components/chat/history-sidebar'
import { WorkflowPanel } from '@/components/chat/workflow-panel'
import { ScriptGate } from '@/components/chat/script-gate'
import { ApprovalGate } from '@/components/workflow/approval-gate'

const STARTERS = ['Một ngày ở canteen VNG', 'Góc học tập ở campus', 'Phỏng vấn intern mùa hè']

/**
 * Tab Chat — bố cục 3 cột kiểu cowork: lịch sử (trái) · hội thoại (giữa) ·
 * tiến trình pipeline + metadata từng step + gate duyệt/sửa kịch bản (phải).
 * Lịch sử lưu DB; reload + restart không mất.
 */
export default function ChatPage() {
  const sessionId = useChatStore((s) => s.sessionId)
  const setSessionId = useChatStore((s) => s.setSessionId)
  const create = useCreateSession()
  const del = useDeleteSession()
  const sessions = useChatSessions()
  const session = useChatSession(sessionId)
  const send = useSendMessage(sessionId)
  const [draft, setDraft] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const creating = useRef(false)

  // Tạo session lần đầu (hoặc khi session cũ 404 / đã xoá).
  useEffect(() => {
    if (sessionId || creating.current) return
    creating.current = true
    create.mutate(undefined, {
      onSuccess: (s) => setSessionId(s.id),
      onSettled: () => {
        creating.current = false
      },
    })
  }, [sessionId, create, setSessionId])

  useEffect(() => {
    if (session.isError) setSessionId(null)
  }, [session.isError, setSessionId])

  const data = session.data
  const run = useRun(data?.run_id ?? null)

  const messages = data?.messages ?? []
  const ui = data?.ui
  const showChips = ui?.kind === 'choices' && (ui.options?.length ?? 0) > 0 && !send.isPending
  const showStarters = messages.length <= 1 && !data?.run_id && !send.isPending
  const runData = data?.run_id ? run.data : undefined
  // Pipeline đang xử lý (chưa tới gate / chưa xong) → khoá composer + nút vuông đỏ.
  const processing = runData?.status === 'running'

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length, send.isPending, runData?.status])

  const onSend = (text: string) => {
    const t = text.trim()
    if (!t || send.isPending || !sessionId) return
    setDraft('')
    send.mutate(t)
  }

  const handleNew = () => {
    if (create.isPending) return
    create.mutate(undefined, { onSuccess: (s) => setSessionId(s.id) })
  }

  const handleDelete = (id: string) => {
    del.mutate(id, {
      onSuccess: () => {
        if (id === sessionId) setSessionId(null) // effect tự tạo cuộc mới
      },
    })
  }

  const sessionList = sessions.data ?? []

  return (
    <div className="flex flex-col gap-5">
      <div className="flex h-[calc(100dvh-9rem)] min-h-[26rem] gap-4">
        <HistorySidebar
          sessions={sessionList}
          activeId={sessionId}
          onSelect={setSessionId}
          onNew={handleNew}
          onDelete={handleDelete}
          creating={create.isPending}
        />

        {/* Cột giữa — hội thoại */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Thanh lịch sử cho mobile (sidebar ẩn) */}
          <div className="mx-auto mb-2 flex w-full max-w-4xl items-center gap-2 md:hidden">
            <Button variant="outline" size="sm" onClick={handleNew} disabled={create.isPending}>
              <Plus className="size-4" /> Mới
            </Button>
            {sessionList.length > 0 && (
              <Select value={sessionId ?? ''} onValueChange={setSessionId}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="Lịch sử…" />
                </SelectTrigger>
                <SelectContent>
                  {sessionList.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.title ?? 'Cuộc trò chuyện mới'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div ref={scrollRef} className="chat-scroll flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-4xl space-y-5 px-1 py-2">
              {messages.map((m, i) => (
                <MessageBubble key={i} message={m} />
              ))}

              {send.isPending && (
                <div className="flex items-center gap-3">
                  <DirectorAvatar />
                  <span className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" /> Đạo diễn đang soạn…
                  </span>
                </div>
              )}

              {showStarters && (
                <div className="flex flex-wrap gap-2">
                  {STARTERS.map((s) => (
                    <Button
                      key={s}
                      variant="outline"
                      size="sm"
                      className="h-auto rounded-full py-1.5"
                      onClick={() => onSend(s)}
                    >
                      {s}
                    </Button>
                  ))}
                </div>
              )}

              {showChips && (
                <OptionChips options={ui!.options} onPick={onSend} disabled={send.isPending} />
              )}

              {/* Gate cần user thao tác → hiện NGAY trong khung chat (mỗi gate tự
                  render null nếu chưa tới lượt). Flow view-only nằm ở sidebar phải. */}
              {runData && <ScriptGate run={runData} />}
              {runData && <ApprovalGate run={runData} />}
            </div>
          </div>

          {/* Composer kiểu ChatGPT — pill bo tròn + nút gửi tròn, ghim đáy khung */}
          <div className="mx-auto w-full max-w-4xl shrink-0 pt-2">
            <div className="flex items-end gap-2 rounded-3xl border border-border bg-background px-4 py-2 shadow-sm transition-colors focus-within:border-ring">
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    onSend(draft)
                  }
                }}
                placeholder={
                  processing ? 'Đang chạy pipeline…' : 'Nhập ý tưởng, trả lời, hoặc gõ “chạy đi” / “đăng đi”…'
                }
                rows={1}
                className="max-h-40 min-h-9 flex-1 resize-none border-0 bg-transparent px-0 py-1.5 text-sm shadow-none focus-visible:border-0 focus-visible:ring-0"
                disabled={!sessionId || session.isLoading || processing}
              />
              {processing ? (
                <Button
                  size="icon"
                  variant="destructive"
                  className="size-9 shrink-0 animate-pulse rounded-full"
                  disabled
                  title="Đang chạy pipeline…"
                  aria-label="Đang chạy pipeline"
                >
                  <Square className="size-3.5 fill-current" />
                </Button>
              ) : (
                <Button
                  size="icon"
                  className="size-9 shrink-0 rounded-full"
                  onClick={() => onSend(draft)}
                  disabled={!draft.trim() || send.isPending}
                  aria-label="Gửi"
                >
                  {send.isPending ? <Loader2 className="animate-spin" /> : <ArrowUp />}
                </Button>
              )}
            </div>
            <p className="mt-1.5 text-center text-xs text-muted-foreground">
              Đạo diễn AI điều khiển pipeline — nói ý tưởng, chọn nhạc, xác nhận để chạy.
            </p>
          </div>
        </div>

        {/* Cột phải — tiến trình pipeline (cowork style), chỉ trên lg+ */}
        {runData && (
          <aside className="hidden w-[380px] shrink-0 flex-col border-l border-border pl-4 lg:flex xl:w-[440px]">
            <div className="mb-2 flex items-center gap-2">
              <Workflow className="size-4 text-primary" aria-hidden />
              <h3 className="text-sm font-semibold text-foreground">Tiến trình pipeline</h3>
            </div>
            <div className="chat-scroll flex-1 overflow-y-auto pr-1">
              <WorkflowPanel run={runData} />
            </div>
          </aside>
        )}
      </div>

      {/* Fallback dưới khung chat cho màn nhỏ (< lg) — không có cột phải */}
      {runData && (
        <div className="mx-auto w-full max-w-4xl lg:hidden">
          <WorkflowPanel run={runData} />
        </div>
      )}
    </div>
  )
}
