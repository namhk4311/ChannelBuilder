import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { ChatSessionSummary } from '@/api/chat'

interface HistorySidebarProps {
  sessions: ChatSessionSummary[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  creating?: boolean
}

/** Sidebar lịch sử chat (desktop) — danh sách cuộc + New + xoá. */
export function HistorySidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
  onDelete,
  creating,
}: HistorySidebarProps) {
  return (
    <aside className="hidden w-60 shrink-0 flex-col gap-2 border-r border-border pr-3 md:flex">
      <Button variant="outline" className="justify-start gap-2" onClick={onNew} disabled={creating}>
        <Plus className="size-4" /> Cuộc trò chuyện mới
      </Button>
      <div className="chat-scroll -mr-1 flex-1 space-y-0.5 overflow-y-auto pr-1">
        {sessions.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">
            Chưa có cuộc trò chuyện
          </p>
        )}
        {sessions.map((s) => {
          const active = s.id === activeId
          return (
            <div
              key={s.id}
              className={cn(
                'group flex items-center gap-1 rounded-lg pr-1 text-sm',
                active ? 'bg-muted' : 'hover:bg-muted/60',
              )}
            >
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                className="min-w-0 flex-1 truncate px-2.5 py-2 text-left"
                title={s.title ?? 'Cuộc trò chuyện mới'}
              >
                {s.title ?? 'Cuộc trò chuyện mới'}
              </button>
              <button
                type="button"
                onClick={() => onDelete(s.id)}
                className="shrink-0 rounded p-1 text-muted-foreground opacity-0 transition hover:text-destructive group-hover:opacity-100"
                aria-label="Xoá cuộc trò chuyện"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
