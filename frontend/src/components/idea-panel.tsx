import { useState } from 'react'
import { Lightbulb } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import type { Idea } from '@/api/types'
import { useGenerateIdeas } from '@/hooks/use-creative'

const DURATIONS = [30, 40, 48, 55, 60]

interface IdeaPanelProps {
  targetDuration: number
  onTargetDuration: (sec: number) => void
  selectedIdea: Idea | null
  onSelectIdea: (idea: Idea | null) => void
}

/** Bước 1 — nhập chủ đề, gọi POST /api/creative/ideas (blocking ~30-60s), chọn 1 idea. */
export function IdeaPanel({
  targetDuration,
  onTargetDuration,
  selectedIdea,
  onSelectIdea,
}: IdeaPanelProps) {
  const [topic, setTopic] = useState('')
  const [ideas, setIdeas] = useState<Idea[]>([])

  const generate = useGenerateIdeas((res) => {
    setIdeas(res.ideas)
    onSelectIdea(null)
    toast.success(`Đã sinh ${res.ideas.length} ý tưởng — backend đang pre-gen kịch bản nền`)
  })

  const handleGenerate = () =>
    generate.mutate(
      { topic: topic.trim(), n_ideas: 5, target_duration_sec: targetDuration },
      { onError: (e) => toast.error(`Sinh ý tưởng thất bại: ${e.message}`) },
    )

  return (
    <Card className="p-4 md:p-6 gap-4">
      <div className="flex items-center gap-2">
        <Lightbulb className="size-4 text-primary" aria-hidden />
        <h3 className="text-base font-semibold text-foreground">1 · Ý tưởng</h3>
      </div>

      <div className="flex flex-col md:flex-row gap-3">
        <Input
          placeholder="Chủ đề video, vd: canteen và café ở VNG Campus…"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && topic.trim().length >= 2 && handleGenerate()}
          className="flex-1"
        />
        <div className="flex items-center gap-3">
          <Select
            value={String(targetDuration)}
            onValueChange={(v) => v && onTargetDuration(Number(v))}
          >
            <SelectTrigger className="w-28" aria-label="Thời lượng mục tiêu">
              <SelectValue placeholder="Thời lượng" />
            </SelectTrigger>
            <SelectContent>
              {DURATIONS.map((d) => (
                <SelectItem key={d} value={String(d)}>
                  ~{d} giây
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={handleGenerate}
            disabled={topic.trim().length < 2 || generate.isPending}
          >
            {generate.isPending ? <Spinner /> : <Lightbulb />}
            Sinh ý tưởng
          </Button>
        </div>
      </div>

      {generate.isPending && (
        <p className="text-sm text-muted-foreground">
          LLM đang sinh ý tưởng (~30-60s), giữ nguyên tab này…
        </p>
      )}

      {ideas.length > 0 && (
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-3" role="listbox" aria-label="Ý tưởng">
          {ideas.map((idea, i) => {
            const selected = selectedIdea === idea
            return (
              <li key={idea.id ?? i}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => onSelectIdea(selected ? null : idea)}
                  className={cn(
                    'w-full min-h-10 rounded-xl border p-3 text-left transition-colors',
                    selected
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/40',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium text-foreground">{idea.title ?? `Ý tưởng ${i + 1}`}</span>
                    {idea.pillar && <Badge variant="secondary">{idea.pillar}</Badge>}
                  </div>
                  {idea.angle && (
                    <p className="mt-1 text-sm text-muted-foreground">{idea.angle}</p>
                  )}
                  {typeof idea.est_fit === 'number' && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Độ khớp ước lượng: {(idea.est_fit * 100).toFixed(0)}%
                    </p>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
