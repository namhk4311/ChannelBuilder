import type { ReactNode } from 'react'
import { Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
import type { InfoOptions, PublishMode, VideoMode, VisualStyle } from '@/api/workflow'
import { VlogFields } from './run-controls-vlog-fields'
import { InfoFields } from './run-controls-info-fields'

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
  // Loại video
  mode: VideoMode
  setMode: (v: VideoMode) => void
  // Vlog
  topic: string
  setTopic: (v: string) => void
  qcConfirm: boolean
  setQcConfirm: (v: boolean) => void
  // Video thông tin
  infoOptions?: InfoOptions
  visualStyle: VisualStyle
  setVisualStyle: (v: VisualStyle, sceneDefault: number) => void
  brand: string
  setBrand: (v: string) => void
  eventText: string
  setEventText: (v: string) => void
  nScenes: number
  setNScenes: (v: number) => void
  // Dùng chung
  subtitles: boolean
  setSubtitles: (v: boolean) => void
  music: MusicPickerValue
  setMusic: (v: MusicPickerValue) => void
  publishMode: PublishMode
  setPublishMode: (v: PublishMode) => void
  onStart: () => void
  isPending: boolean
  runActive: boolean
  canStart: boolean
}

/** Khu cấu hình + CTA chạy pipeline, gom control theo từng agent cho dễ hiểu. */
export function RunControls({
  mode,
  setMode,
  topic,
  setTopic,
  qcConfirm,
  setQcConfirm,
  infoOptions,
  visualStyle,
  setVisualStyle,
  brand,
  setBrand,
  eventText,
  setEventText,
  nScenes,
  setNScenes,
  subtitles,
  setSubtitles,
  music,
  setMusic,
  publishMode,
  setPublishMode,
  onStart,
  isPending,
  runActive,
  canStart,
}: RunControlsProps) {
  const isInfo = mode === 'info'
  return (
    <Card>
      <CardContent className="space-y-5">
        {/* Loại video — quyết định nhánh pipeline + bộ field hiển thị */}
        <div className="flex flex-col gap-1.5 md:max-w-md">
          <Label
            htmlFor="wf-video-mode"
            className="text-xs uppercase tracking-wide text-muted-foreground"
          >
            Loại video
          </Label>
          <Select value={mode} onValueChange={(v) => setMode(v as VideoMode)} disabled={runActive}>
            <SelectTrigger id="wf-video-mode" className="w-full md:w-72">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="vlog">🎬 Vlog clip có sẵn</SelectItem>
              <SelectItem value="info">📢 Video thông tin</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <AgentGroup
          code="B"
          name="Creative"
          hint={isInfo ? 'Nội dung & storyboard' : 'Ý tưởng & kịch bản'}
        >
          {isInfo ? (
            <InfoFields
              infoOptions={infoOptions}
              visualStyle={visualStyle}
              setVisualStyle={setVisualStyle}
              brand={brand}
              setBrand={setBrand}
              eventText={eventText}
              setEventText={setEventText}
              nScenes={nScenes}
              setNScenes={setNScenes}
              runActive={runActive}
            />
          ) : (
            <VlogFields
              topic={topic}
              setTopic={setTopic}
              qcConfirm={qcConfirm}
              setQcConfirm={setQcConfirm}
              runActive={runActive}
            />
          )}
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
          </div>
        </AgentGroup>

        <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">
            {isInfo
              ? 'Video thông tin: tự dò loại nội dung → storyboard → dựng banner/ảnh → đăng. Nhập nội dung thông tin để chạy.'
              : canStart
                ? 'Pipeline chạy: Scout → Creative → Producer → Publisher → Analyst.'
                : 'Chọn thư viện clip ở góc trên để chạy — Producer chỉ pick clip trong thư viện đang chọn.'}
          </p>
          <Button
            size="lg"
            onClick={onStart}
            disabled={isPending || runActive || !canStart}
            className="sm:shrink-0"
          >
            <Play /> Chạy pipeline
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
