import { useState } from 'react'
import { Clapperboard, RotateCcw } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { toast } from 'sonner'
import { useProduce } from '@/hooks/use-produce'
import { ProduceResultView } from '@/components/produce-result'

interface ProducePanelProps {
  script: string
  library: string | null
}

/** Bước 3 — POST /api/produce (job nền 6 step) rồi poll progress tới khi có 3 link MinIO. */
export function ProducePanel({ script, library }: ProducePanelProps) {
  const [subtitles, setSubtitles] = useState(true)
  const { start, job, jobId, reset } = useProduce()

  const status = job.data?.status
  const running = start.isPending || status === 'queued' || status === 'running'
  const canStart = !!library && script.trim().length >= 10 && !running

  const handleStart = () =>
    start.mutate(
      { script: script.trim(), subtitles, library: library! },
      { onError: (e) => toast.error(`Không start được job: ${e.message}`) },
    )

  return (
    <Card className="p-4 md:p-6 gap-4">
      <div className="flex flex-col md:flex-row md:items-center gap-3">
        <div className="flex items-center gap-2">
          <Clapperboard className="size-4 text-primary" aria-hidden />
          <h3 className="text-base font-semibold text-foreground">3 · Tạo video</h3>
        </div>
        <div className="flex items-center gap-3 md:ml-auto">
          <div className="flex items-center gap-2">
            <Switch
              id="subtitles"
              checked={subtitles}
              onCheckedChange={setSubtitles}
              disabled={running}
            />
            <Label htmlFor="subtitles" className="text-sm text-muted-foreground">
              Phụ đề theo giọng đọc
            </Label>
          </div>
          {(status === 'done' || status === 'error') && (
            <Button variant="outline" onClick={reset}>
              <RotateCcw /> Làm lại
            </Button>
          )}
          <Button onClick={handleStart} disabled={!canStart}>
            {running ? <Spinner /> : <Clapperboard />}
            Tạo video
          </Button>
        </div>
      </div>

      {!jobId && (
        <p className="text-sm text-muted-foreground">
          Pipeline 6 bước: TTS → LLM chọn clip (thư viện đang chọn) → ghép → cân thời lượng →
          lồng tiếng + phụ đề → upload MinIO. Mất ~2-3 phút.
        </p>
      )}

      {jobId && job.data && status !== 'done' && status !== 'error' && (
        <div className="space-y-2">
          <Progress value={job.data.percent} aria-label="Tiến độ tạo video" />
          <p className="text-sm text-muted-foreground">
            {job.data.percent}% — {job.data.message}
          </p>
        </div>
      )}

      {jobId && job.isError && (
        <Alert variant="destructive">
          <AlertTitle>Không poll được trạng thái job</AlertTitle>
          <AlertDescription>{(job.error as Error)?.message}</AlertDescription>
        </Alert>
      )}

      {status === 'error' && (
        <Alert variant="destructive">
          <AlertTitle>Pipeline lỗi</AlertTitle>
          <AlertDescription>{job.data?.error ?? 'Không rõ nguyên nhân'}</AlertDescription>
        </Alert>
      )}

      {status === 'done' && job.data?.result && <ProduceResultView result={job.data.result} />}
    </Card>
  )
}
