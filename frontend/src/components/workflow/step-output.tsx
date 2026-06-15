import { useMemo } from 'react'
import { Copy } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

/**
 * Render output của 1 step ở dạng người-đọc-được (bảng + key/value + badge)
 * thay cho JSON thô — non-tech vẫn hiểu. Tab "JSON" + nút Copy giữ output gốc.
 */

// Nhãn tiếng Việt cho các key hay gặp trong output của 4 agent.
const LABELS: Record<string, string> = {
  // scout [A]
  digest: 'Tổng hợp xu hướng',
  nganh: 'Ngành',
  metric: 'Chỉ số xếp hạng',
  so_video_quet: 'Số video quét',
  so_video_loai: 'Số video loại',
  top_format: 'Format nổi bật',
  format: 'Format',
  metric_tb: 'Chỉ số TB',
  so_video: 'Số video',
  ghi_chu: 'Ghi chú',
  do_dai_toi_uu: 'Độ dài tối ưu',
  hook_pattern_thang: 'Hook thắng',
  pattern: 'Mẫu hook',
  chu_de_hot: 'Chủ đề hot',
  chu_de: 'Chủ đề',
  nhom: 'Nhóm',
  format_yeu: 'Format yếu',
  benchmark_khoi_tao: 'Ngưỡng khởi tạo',
  nguong: 'Ngưỡng đạt',
  retention_3s_pct_nguong: 'Ngưỡng giữ chân 3s (%)',
  insight: 'Nhận định',
  warnings: 'Cảnh báo',
  // creative [B]
  ideas: 'Ý tưởng',
  id: 'Mã',
  title: 'Tiêu đề',
  pillar: 'Pillar',
  angle: 'Góc tiếp cận',
  trend_ref: 'Tham chiếu trend',
  insight_ref: 'Tham chiếu insight',
  est_fit: 'Độ phù hợp',
  package: 'Gói kịch bản',
  text_hook: 'Text hook',
  script: 'Lời thoại',
  caption: 'Caption',
  hashtags: 'Hashtag',
  shot_list: 'Shot list',
  idea: 'Ý tưởng đã chọn',
  line: 'Câu',
  voiceover: 'Lời đọc',
  duration_sec: 'Thời lượng (s)',
  clip_tag: 'Clip tag',
  alt_tag: 'Clip thay thế',
  scene_hint: 'Gợi ý cảnh',
  // producer [C]
  output_url: 'Link video',
  final_duration_sec: 'Thời lượng cuối (s)',
  selected_clips: 'Clip đã chọn',
  tts_cache_hit: 'TTS dùng cache',
  job_id: 'Mã job',
  // publisher [D] + gate
  video_url: 'Link video',
  video_id: 'Mã video',
  publish_id: 'Mã publish',
  videos: 'Video',
  view_count: 'Lượt xem',
  like_count: 'Lượt thích',
  comment_count: 'Bình luận',
  share_count: 'Chia sẻ',
}

// Key ẩn khỏi bảng (đã hiện ở chip trạng thái / câu tóm tắt, hoặc trùng lặp).
const BASE_HIDE = ['status']
const TOOL_HIDE: Record<string, string[]> = {
  // digest đã chứa mọi thứ; day_cho_* + chi_tiet là bản trùng/raw dành cho agent;
  // source đã hiển thị ở chip nguồn data.
  scan_trends: ['day_cho_creative', 'day_cho_analyst', 'chi_tiet', 'digest_tuan', 'source'],
  // used_insight render riêng bằng InsightBlock (RunStepList) — ẩn khỏi bảng ý tưởng.
  generate_ideas: ['used_insight'],
}

// String dài → render thành đoạn văn (không nhồi vào 1 dòng / 1 ô bảng).
const LONG_TEXT_KEYS = new Set(['script', 'voiceover', 'angle', 'caption', 'error'])

const numberFmt = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 })

function labelOf(key: string): string {
  return LABELS[key] ?? key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function isEmpty(v: unknown): boolean {
  if (v === null || v === undefined || v === '') return true
  if (Array.isArray(v)) return v.length === 0
  if (isPlainObject(v)) return Object.keys(v).length === 0
  return false
}

function isUrl(s: string): boolean {
  return /^https?:\/\//i.test(s)
}

function Primitive({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === '')
    return <span className="text-muted-foreground">—</span>
  if (typeof value === 'boolean')
    return (
      <Badge variant={value ? 'secondary' : 'outline'} className="font-normal">
        {value ? 'Có' : 'Không'}
      </Badge>
    )
  if (typeof value === 'number')
    return <span className="tabular-nums">{numberFmt.format(value)}</span>
  const s = String(value)
  if (isUrl(s))
    return (
      <a
        href={s}
        target="_blank"
        rel="noreferrer"
        className="text-primary underline underline-offset-2 break-all"
      >
        {s}
      </a>
    )
  return <span className="whitespace-pre-wrap break-words">{s}</span>
}

/** Value trong 1 ô bảng — gọn, không tạo bảng lồng. */
function CellValue({ value }: { value: unknown }) {
  if (Array.isArray(value) && value.every((v) => !isPlainObject(v) && !Array.isArray(v))) {
    if (value.length === 0) return <span className="text-muted-foreground">—</span>
    return (
      <div className="flex flex-wrap gap-1">
        {value.map((v, i) => (
          <Badge key={i} variant="secondary" className="font-normal">
            {String(v)}
          </Badge>
        ))}
      </div>
    )
  }
  if (isPlainObject(value) || Array.isArray(value)) return <Value value={value} />
  return <Primitive value={value} />
}

/** Mảng object → bảng (cột = hợp các key, theo thứ tự xuất hiện). */
function ObjectTable({ rows, hide }: { rows: Record<string, unknown>[]; hide: Set<string> }) {
  const cols: string[] = []
  for (const r of rows)
    for (const k of Object.keys(r)) if (!hide.has(k) && !cols.includes(k)) cols.push(k)
  // Bỏ cột rỗng ở mọi dòng (vd trend_ref/insight_ref luôn null) cho gọn.
  const shown = cols.filter((c) => rows.some((r) => !isEmpty(r[c])))
  if (shown.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/50 hover:bg-muted/50">
            {shown.map((c) => (
              <TableHead key={c} className="h-8 text-xs">
                {labelOf(c)}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r, i) => (
            <TableRow key={i}>
              {shown.map((c) => (
                <TableCell key={c} className="max-w-md whitespace-normal align-top text-xs">
                  <CellValue value={r[c]} />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function Value({ value, hide }: { value: unknown; hide?: Set<string> }) {
  const hideSet = hide ?? new Set<string>()
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground">—</span>
    if (value.every(isPlainObject))
      return <ObjectTable rows={value as Record<string, unknown>[]} hide={hideSet} />
    // Mảng chuỗi dài (insight, warnings) → bullet list; chuỗi ngắn (hashtag) → chip.
    const longish = value.some((v) => typeof v === 'string' && v.length > 40)
    if (longish)
      return (
        <ul className="list-disc space-y-1 pl-5 text-sm text-foreground">
          {value.map((v, i) => (
            <li key={i}>{String(v)}</li>
          ))}
        </ul>
      )
    return (
      <div className="flex flex-wrap gap-1.5">
        {value.map((v, i) => (
          <Badge key={i} variant="secondary" className="font-normal">
            {String(v)}
          </Badge>
        ))}
      </div>
    )
  }
  if (isPlainObject(value)) return <ObjectView obj={value} hide={hideSet} />
  return <Primitive value={value} />
}

function ObjectView({ obj, hide }: { obj: Record<string, unknown>; hide: Set<string> }) {
  const entries = Object.entries(obj).filter(([k, v]) => !hide.has(k) && !isEmpty(v))
  if (entries.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <dl className="space-y-2.5">
      {entries.map(([k, v]) => {
        const longText = LONG_TEXT_KEYS.has(k) && typeof v === 'string'
        const stacked = Array.isArray(v) || isPlainObject(v) || longText
        return (
          <div
            key={k}
            className={cn(stacked ? 'space-y-1' : 'flex flex-wrap items-baseline gap-x-2 gap-y-0.5')}
          >
            <dt className="shrink-0 text-xs font-medium text-muted-foreground">{labelOf(k)}</dt>
            <dd className="min-w-0 flex-1 text-sm text-foreground">
              <Value value={v} hide={hide} />
            </dd>
          </div>
        )
      })}
    </dl>
  )
}

export function StepOutput({ tool, output }: { tool: string; output: unknown }) {
  const json = useMemo(() => JSON.stringify(output, null, 2), [output])
  const hide = useMemo(
    () => new Set<string>([...BASE_HIDE, ...(TOOL_HIDE[tool] ?? [])]),
    [tool],
  )

  const copy = () =>
    navigator.clipboard
      .writeText(json)
      .then(() => toast.success('Đã copy output dạng JSON'))
      .catch(() => toast.error('Không copy được — clipboard bị chặn'))

  return (
    <div className="rounded-lg border border-border bg-muted/30">
      <Tabs defaultValue="table">
        <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5">
          <div className="flex min-w-0 items-center gap-3">
            <TabsList variant="line" className="h-7">
              <TabsTrigger value="table" className="text-xs">
                Bảng
              </TabsTrigger>
              <TabsTrigger value="json" className="text-xs">
                JSON
              </TabsTrigger>
            </TabsList>
          </div>
          <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2" onClick={copy}>
            <Copy /> Copy JSON
          </Button>
        </div>
        <TabsContent value="table" className="m-0 max-h-96 overflow-auto p-3">
          {isPlainObject(output) || Array.isArray(output) ? (
            <Value value={output} hide={hide} />
          ) : (
            <Primitive value={output} />
          )}
        </TabsContent>
        <TabsContent value="json" className="m-0">
          <pre className="max-h-96 overflow-auto p-3 text-xs leading-relaxed">{json}</pre>
        </TabsContent>
      </Tabs>
    </div>
  )
}
