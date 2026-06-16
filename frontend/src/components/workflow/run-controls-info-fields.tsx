import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { InfoOptions, VisualStyle } from '@/api/workflow'

/** Độ dài tối thiểu của nội dung thông tin (khớp validate conductor: event_text >= 20). */
export const EVENT_TEXT_MIN = 20

interface InfoFieldsProps {
  infoOptions?: InfoOptions
  visualStyle: VisualStyle
  /** Đổi visual_style — đồng thời clamp n_scenes về scene_default của style mới. */
  setVisualStyle: (v: VisualStyle, sceneDefault: number) => void
  brand: string
  setBrand: (v: string) => void
  eventText: string
  setEventText: (v: string) => void
  nScenes: number
  setNScenes: (v: number) => void
  runActive: boolean
}

/** Field riêng cho "Video thông tin" — visual_style → brand (khi solid) → nội dung → số cảnh. */
export function InfoFields({
  infoOptions,
  visualStyle,
  setVisualStyle,
  brand,
  setBrand,
  eventText,
  setEventText,
  nScenes,
  setNScenes,
  runActive,
}: InfoFieldsProps) {
  if (!infoOptions) {
    return <p className="text-xs text-muted-foreground">Đang tải tuỳ chọn…</p>
  }

  const currentStyle = infoOptions.visual_styles.find((s) => s.value === visualStyle)
  const needsBrand = currentStyle?.needs_brand ?? false
  const sceneOptions = currentStyle?.scenes ?? []
  const textLen = eventText.trim().length

  return (
    <div className="flex flex-col gap-3">
      {/* Phong cách hình ảnh */}
      <div className="flex flex-col gap-1.5 md:max-w-md">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Phong cách hình ảnh
        </Label>
        <Select
          value={visualStyle}
          onValueChange={(v) => {
            const style = infoOptions.visual_styles.find((s) => s.value === v)
            setVisualStyle(v as VisualStyle, style?.scene_default ?? nScenes)
          }}
          disabled={runActive}
        >
          <SelectTrigger className="w-full md:w-72">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {infoOptions.visual_styles.map((s) => (
              <SelectItem key={s.value} value={s.value}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {currentStyle?.hint && (
          <p className="text-xs text-muted-foreground">{currentStyle.hint}</p>
        )}
      </div>

      {/* Brand — chỉ khi visual_style cần (solid) */}
      {needsBrand && (
        <div className="flex flex-col gap-1.5 md:max-w-md">
          <Label className="text-xs uppercase tracking-wide text-muted-foreground">
            Thương hiệu (màu nền)
          </Label>
          <Select value={brand} onValueChange={setBrand} disabled={runActive}>
            <SelectTrigger className="w-full md:w-72">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {infoOptions.brands.map((b) => (
                <SelectItem key={b.value} value={b.value}>
                  {b.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Nội dung thông tin */}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="wf-event-text" className="text-xs uppercase tracking-wide text-muted-foreground">
          Nội dung thông tin
        </Label>
        <Textarea
          id="wf-event-text"
          placeholder="Dán đoạn tin/thông báo cần làm video — vd: Chính phủ Mỹ ra lệnh tạm dừng vài mô hình AI lớn để rà soát an toàn…"
          value={eventText}
          onChange={(e) => setEventText(e.target.value)}
          disabled={runActive}
          rows={4}
          className="md:max-w-xl"
        />
        <p className="text-xs text-muted-foreground">
          {textLen < EVENT_TEXT_MIN
            ? `Cần thêm ${EVENT_TEXT_MIN - textLen} ký tự (tối thiểu ${EVENT_TEXT_MIN}).`
            : `${textLen} ký tự.`}
        </p>
      </div>

      {/* Số cảnh — dải theo visual_style */}
      <div className="flex flex-col gap-1.5 md:max-w-md">
        <Label className="text-xs uppercase tracking-wide text-muted-foreground">
          Số cảnh
        </Label>
        <Select
          value={String(nScenes)}
          onValueChange={(v) => setNScenes(Number(v))}
          disabled={runActive}
        >
          <SelectTrigger className="w-full md:w-72">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {sceneOptions.map((n) => (
              <SelectItem key={n} value={String(n)}>
                {n === 1 ? '1 cảnh (1 banner)' : `${n} cảnh`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
