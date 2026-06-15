import type { ReactNode } from 'react'
import { Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { MusicPicker, type MusicPickerValue } from '@/components/music-picker'
import type { PublishMode } from '@/api/workflow'

/** Nhóm control theo agent — badge mã (B/C/D khớp rail pipeline) + tên + mô tả ngắn. */
function AgentGroup({
  code,
  name,
  hint,
  children,
}: {
  code: string
  name: string
  hint: string
  children: ReactNode
}) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2">
        <span className="inline-flex size-5 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
          {code}
        </span>
        <span className="text-sm font-semibold text-foreground">{name}</span>
        <span className="text-xs text-muted-foreground">· {hint}</span>
      </div>
      <div className="md:pl-7">{children}</div>
    </div>
  )
}

interface RunControlsProps {
  topic: string
  setTopic: (v: string) => void
  subtitles: boolean
  setSubtitles: (v: boolean) => void
  music: MusicPickerValue
  setMusic: (v: MusicPickerValue) => void
  publishMode: PublishMode
  setPublishMode: (v: PublishMode) => void
  onStart: () => void
  isPending: boolean
  runActive: boolean
  hasLibrary: boolean
}

const PUBLISH_MODE_HINT: Record<PublishMode, string> = {
  review_publish: 'Bạn duyệt ở bước cuối → đăng ngay lên TikTok.',
  schedule: 'Bạn duyệt + chọn giờ → bài vào “Lịch đăng”, tự đăng tới giờ.',
}

/** Khu cấu hình + CTA chạy pipeline, gom control theo từng agent cho dễ hiểu. */
export function RunControls({
  topic,
  setTopic,
  subtitles,
  setSubtitles,
  music,
  setMusic,
  publishMode,
  setPublishMode,
  onStart,
  isPending,
  runActive,
  hasLibrary,
}: RunControlsProps) {
  return (
    <Card>
      <CardContent className="space-y-5">
        <AgentGroup code="B" name="Creative" hint="Ý tưởng & kịch bản">
          <Input
            placeholder="Chủ đề (tuỳ chọn) — vd: canteen VNG, góc làm việc…"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={runActive}
            className="md:max-w-md"
          />
        </AgentGroup>

        <AgentGroup code="C" name="Producer" hint="Dựng video · phụ đề · nhạc nền">
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Switch
                id="wf-subtitles"
                checked={subtitles}
                onCheckedChange={setSubtitles}
                disabled={runActive}
              />
              <Label htmlFor="wf-subtitles" className="text-sm text-muted-foreground">
                Phụ đề
              </Label>
            </div>
            <MusicPicker value={music} onChange={setMusic} disabled={runActive} idPrefix="wf" />
          </div>
        </AgentGroup>

        <AgentGroup code="D" name="Publisher" hint="Cách đăng lên TikTok">
          <div className="flex flex-col gap-1.5 md:max-w-md">
            <Label
              htmlFor="wf-publish-mode"
              className="text-xs uppercase tracking-wide text-muted-foreground"
            >
              Chế độ đăng
            </Label>
            <Select
              value={publishMode}
              onValueChange={(v) => setPublishMode(v as PublishMode)}
              disabled={runActive}
            >
              <SelectTrigger id="wf-publish-mode" className="w-full md:w-72">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="review_publish">Kiểm duyệt rồi đăng ngay</SelectItem>
                <SelectItem value="schedule">Lên lịch đăng</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{PUBLISH_MODE_HINT[publishMode]}</p>
          </div>
        </AgentGroup>

        <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">
            {hasLibrary
              ? 'Pipeline chạy: Scout → Creative → Producer → gate duyệt → Publisher.'
              : 'Chọn thư viện clip ở góc trên để chạy — Producer chỉ pick clip trong thư viện đang chọn.'}
          </p>
          <Button
            size="lg"
            onClick={onStart}
            disabled={isPending || runActive || !hasLibrary}
            className="sm:shrink-0"
          >
            <Play /> Chạy pipeline
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
