import { PenLine } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { toast } from 'sonner'
import type { Idea, ScriptPackage } from '@/api/types'
import { useGenerateScript } from '@/hooks/use-creative'

/** Validator backend tính 2.8 từ/giây — hiển thị lại cùng công thức. */
const WORDS_PER_SEC = 2.8

interface ScriptPanelProps {
  idea: Idea | null
  targetDuration: number
  script: string
  onScriptChange: (script: string) => void
  pkg: ScriptPackage | null
  warnings: string[]
  onPackage: (pkg: ScriptPackage, warnings: string[]) => void
}

/** Bước 2 — từ idea đã chọn gọi POST /api/creative/script; script editable trước khi produce. */
export function ScriptPanel({
  idea,
  targetDuration,
  script,
  onScriptChange,
  pkg,
  warnings,
  onPackage,
}: ScriptPanelProps) {
  const generate = useGenerateScript((res) => {
    if (res.package) onPackage(res.package, res.warnings ?? [])
    toast.success('Đã có kịch bản — chỉnh sửa tuỳ ý rồi bấm Tạo video')
  })

  const handleGenerate = () =>
    generate.mutate(
      { idea: idea!, target_duration_sec: targetDuration },
      { onError: (e) => toast.error(`Viết kịch bản thất bại: ${e.message}`) },
    )

  const wordCount = script.trim() ? script.trim().split(/\s+/).length : 0
  const estSec = wordCount / WORDS_PER_SEC

  return (
    <Card className="p-4 md:p-6 gap-4">
      <div className="flex flex-col md:flex-row md:items-center gap-3">
        <div className="flex items-center gap-2">
          <PenLine className="size-4 text-primary" aria-hidden />
          <h3 className="text-base font-semibold text-foreground">2 · Kịch bản</h3>
        </div>
        <Button
          onClick={handleGenerate}
          disabled={!idea || generate.isPending}
          className="md:ml-auto"
        >
          {generate.isPending ? <Spinner /> : <PenLine />}
          Viết kịch bản
        </Button>
      </div>

      {!idea && !script && (
        <p className="text-sm text-muted-foreground">
          Chọn 1 ý tưởng ở bước 1 — hoặc dán thẳng kịch bản của bạn vào ô dưới.
        </p>
      )}
      {generate.isPending && (
        <p className="text-sm text-muted-foreground">
          Đang viết kịch bản… (thường nhanh nhờ cache pre-gen, tối đa ~60s)
        </p>
      )}

      <div className="space-y-2">
        <Textarea
          placeholder="Lời thoại voice-over liền mạch (110-140 từ cho 40-55s)…"
          value={script}
          onChange={(e) => onScriptChange(e.target.value)}
          rows={6}
        />
        {wordCount > 0 && (
          <p className="text-xs text-muted-foreground">
            {wordCount} từ · ước lượng ~{estSec.toFixed(0)}s giọng đọc
          </p>
        )}
      </div>

      {pkg && (
        <div className="space-y-3">
          {pkg.text_hook && (
            <div className="text-sm">
              <span className="font-medium text-foreground">Text hook (2-3s đầu): </span>
              <span className="text-muted-foreground">{pkg.text_hook}</span>
            </div>
          )}
          {pkg.caption && (
            <div className="text-sm">
              <span className="font-medium text-foreground">Caption: </span>
              <span className="text-muted-foreground">{pkg.caption}</span>
            </div>
          )}
          {!!pkg.hashtags?.length && (
            <div className="flex flex-wrap gap-1.5">
              {pkg.hashtags.map((h) => (
                <Badge key={h} variant="outline">
                  {h}
                </Badge>
              ))}
            </div>
          )}
        </div>
      )}

      {warnings.length > 0 && (
        <Alert variant="warning">
          <AlertTitle>Validator cảnh báo ({warnings.length})</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4 space-y-0.5">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
    </Card>
  )
}
