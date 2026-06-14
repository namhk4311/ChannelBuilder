import { Music } from 'lucide-react'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useMusic } from '@/hooks/use-music'

export interface MusicPickerValue {
  music_track_id: string | null
  beat_sync: boolean
  music_volume: number // 0.05 - 1.0
}

interface MusicPickerProps {
  value: MusicPickerValue
  onChange: (next: MusicPickerValue) => void
  disabled?: boolean
  idPrefix?: string
}

const fmtDur = (sec: number | null) => {
  if (!sec) return '?:??'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Reusable controls — dropdown nhạc + beat-sync switch + volume slider.
 *  Dùng cả ở ProducePanel (manual) lẫn WorkflowPage (auto pipeline). */
export function MusicPicker({ value, onChange, disabled, idPrefix = 'mp' }: MusicPickerProps) {
  const music = useMusic()
  const tracks = music.data ?? []
  const hasTrack = !!value.music_track_id
  const volPct = Math.round(value.music_volume * 100)

  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:flex-wrap">
      <div className="flex flex-col gap-1.5 min-w-0 md:min-w-64">
        <Label htmlFor={`${idPrefix}-track`} className="text-xs uppercase tracking-wide text-muted-foreground">
          <Music className="inline size-3 mr-1" aria-hidden /> Nhạc nền
        </Label>
        <Select
          value={value.music_track_id ?? 'none'}
          onValueChange={(v) =>
            onChange({ ...value, music_track_id: v === 'none' ? null : v })
          }
          disabled={disabled}
        >
          <SelectTrigger id={`${idPrefix}-track`} className="w-full md:w-72">
            <SelectValue placeholder="— Không nhạc —" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">— Không nhạc —</SelectItem>
            {tracks.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {t.label ?? t.file} · {(t.bpm ?? 0).toFixed(0)} BPM · {fmtDur(t.duration_sec)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2 pt-2 md:pt-0 md:pb-2">
        <Switch
          id={`${idPrefix}-beat`}
          checked={value.beat_sync}
          onCheckedChange={(beat_sync) => onChange({ ...value, beat_sync })}
          disabled={disabled || !hasTrack}
        />
        <Label htmlFor={`${idPrefix}-beat`} className="text-sm text-muted-foreground">
          Cut theo beat
        </Label>
      </div>

      <div className="flex flex-col gap-1.5 md:min-w-44">
        <Label htmlFor={`${idPrefix}-vol`} className="text-xs uppercase tracking-wide text-muted-foreground">
          Music volume
        </Label>
        <div className="flex items-center gap-2">
          <input
            id={`${idPrefix}-vol`}
            type="range"
            min={30}
            max={50}
            step={5}
            value={volPct}
            disabled={disabled || !hasTrack}
            onChange={(e) =>
              onChange({ ...value, music_volume: parseInt(e.target.value, 10) / 100 })
            }
            className="accent-primary w-32 disabled:opacity-40"
            aria-label="Music volume"
            title="Clamped 30-50% để voice luôn nghe rõ trên nhạc"
          />
          <span className="tabular-nums text-sm text-primary font-medium min-w-12">
            {volPct}%
          </span>
        </div>
      </div>
    </div>
  )
}

export const MUSIC_PICKER_DEFAULT: MusicPickerValue = {
  music_track_id: null,
  beat_sync: true,
  music_volume: 0.3,
}
