import { useEffect, useState } from 'react'
import { Clapperboard, Play } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/common/page-header'
import { EmptyState } from '@/components/common/empty-state'
import { LoadError } from '@/components/common/load-error'
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
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import type { RunStatus, StepStatus } from '@/api/workflow'
import { useLibraryStore } from '@/stores/library-store'
import { useAgents, useRun, useRuns, useStartRun } from '@/hooks/use-workflow'
import { AgentCatalog } from '@/components/workflow/agent-catalog'
import { ApprovalGate } from '@/components/workflow/approval-gate'
import { PipelineFlow } from '@/components/workflow/pipeline-flow'
import { RunStepList } from '@/components/workflow/run-step-list'
import { StepStatusChip } from '@/components/workflow/step-status-chip'
import { TikTokConnectCard } from '@/components/workflow/tiktok-connect-card'

const RUN_STATUS_AS_STEP: Record<RunStatus, StepStatus> = {
  running: 'running',
  awaiting_approval: 'awaiting',
  completed: 'ok',
  failed: 'failed',
  rejected: 'rejected',
}

export default function WorkflowPage() {
  const library = useLibraryStore((s) => s.library)
  const [topic, setTopic] = useState('')
  const [subtitles, setSubtitles] = useState(true)
  const [runId, setRunId] = useState<string | null>(null)

  const agents = useAgents()
  const runs = useRuns()
  const run = useRun(runId)
  const start = useStartRun((r) => {
    setRunId(r.id)
    toast.success(`Đã khởi động ${r.id}`)
  })

  // Mở UI là thấy ngay run mới nhất (kể cả run được start từ nơi khác).
  const latestRunId = runs.data?.[0]?.id
  useEffect(() => {
    if (!runId && latestRunId) setRunId(latestRunId)
  }, [runId, latestRunId])

  const runActive = run.data?.status === 'running' || run.data?.status === 'awaiting_approval'

  const handleStart = () =>
    start.mutate(
      { topic: topic.trim() || null, library: library ?? 'vng_insider', subtitles },
      { onError: (e) => toast.error(`Không khởi động được run: ${e.message}`) },
    )

  return (
    <div className="space-y-6 md:space-y-8">
      <PageHeader
        icon={Clapperboard}
        title="VNG Insider — Workflow"
        description="AI tự vận hành kênh TikTok: quét trend → kịch bản → dựng video → đăng → học. Human quyết định ở gate."
      />

      {/* Run controls */}
      <Card>
        <CardContent>
          <div className="flex flex-col md:flex-row md:items-center gap-3">
            <Input
              placeholder="Chủ đề (optional, dùng cho Creative)…"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="md:max-w-md"
            />
            <div className="flex items-center gap-2">
              <Switch id="wf-subtitles" checked={subtitles} onCheckedChange={setSubtitles} />
              <Label htmlFor="wf-subtitles" className="text-sm text-muted-foreground">
                Phụ đề
              </Label>
            </div>
            <Button
              onClick={handleStart}
              disabled={start.isPending || runActive || !library}
              className="md:ml-auto"
            >
              <Play /> Chạy pipeline
            </Button>
          </div>
          {!library && (
            <p className="mt-2 text-xs text-muted-foreground">
              Chọn thư viện clip ở góc trên để chạy — Producer chỉ pick clip trong thư viện đang
              chọn.
            </p>
          )}
          <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
            Pipeline chạy thật: Scout quét trend (dataset seed), Creative gọi LLM (VNGCloud MaaS),
            Producer render thật (ElevenLabs + ffmpeg) và Publisher đăng TikTok thật (video private
            SELF_ONLY, tối đa 5 post/24h).
          </p>
        </CardContent>
      </Card>

      {/* Kết nối TikTok cho Publisher [D] — OAuth 1 lần từ UI */}
      <TikTokConnectCard />

      {/* Pipeline */}
      {agents.isLoading && <Skeleton className="h-36 w-full" />}
      {agents.isError && (
        <LoadError
          title="Không tải được danh sách agent"
          description={agents.error.message}
          onRetry={() => agents.refetch()}
        />
      )}
      {agents.data && <PipelineFlow agents={agents.data} steps={run.data?.steps ?? []} />}

      {/* Human gate */}
      {run.data && <ApprovalGate run={run.data} />}

      {/* Run detail */}
      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <h3 className="text-base font-semibold text-foreground">Run hiện tại</h3>
              {run.data && <StepStatusChip status={RUN_STATUS_AS_STEP[run.data.status]} />}
            </div>
            {(runs.data?.length ?? 0) > 0 && (
              <Select value={runId ?? ''} onValueChange={setRunId}>
                <SelectTrigger className="w-56">
                  <SelectValue placeholder="Chọn run…" />
                </SelectTrigger>
                <SelectContent>
                  {runs.data!.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.id}
                      {r.topic ? ` · ${r.topic}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          {!runId && (
            <EmptyState
              variant="dashed"
              title="Chưa có run nào"
              description="Bấm “Chạy pipeline” để Orchestrator chạy end-to-end: Scout → Creative → Producer → gate → Publisher."
            />
          )}
          {runId && run.isLoading && (
            <div className="space-y-3">
              {Array.from({ length: 7 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          )}
          {runId && run.isError && (
            <LoadError
              title="Không tải được run"
              description={run.error.message}
              onRetry={() => run.refetch()}
            />
          )}
          {run.data && <RunStepList steps={run.data.steps} />}
        </CardContent>
      </Card>

      {/* Agent catalog */}
      {agents.data && (
        <section className="space-y-3">
          <h3 className="text-base font-semibold text-foreground">
            Agent &amp; tools (đọc live từ TOOL_DEFINITIONS)
          </h3>
          <AgentCatalog agents={agents.data} />
        </section>
      )}
    </div>
  )
}
