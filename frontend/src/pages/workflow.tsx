import { useEffect, useState } from 'react'
import { Clapperboard } from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader } from '@/components/common/page-header'
import { EmptyState } from '@/components/common/empty-state'
import { LoadError } from '@/components/common/load-error'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import type { PublishMode, RunStatus, StepStatus } from '@/api/workflow'
import { useLibraryStore } from '@/stores/library-store'
import { useAgents, useRun, useRuns, useStartRun } from '@/hooks/use-workflow'
import { ScriptGate } from '@/components/chat/script-gate'
import { AgentCatalog } from '@/components/workflow/agent-catalog'
import { ApprovalGate } from '@/components/workflow/approval-gate'
import { InsightActiveBanner } from '@/components/workflow/insight-active-banner'
import { PipelineFlow } from '@/components/workflow/pipeline-flow'
import { RunControls } from '@/components/workflow/run-controls'
import { RunStepList } from '@/components/workflow/run-step-list'
import { StepStatusChip } from '@/components/workflow/step-status-chip'
import { TikTokConnectCard, TikTokConnectedLine } from '@/components/workflow/tiktok-connect-card'
import { MUSIC_PICKER_DEFAULT, type MusicPickerValue } from '@/components/music-picker'

const RUN_STATUS_AS_STEP: Record<RunStatus, StepStatus> = {
  running: 'running',
  awaiting_idea: 'awaiting',
  awaiting_script: 'awaiting',
  awaiting_approval: 'awaiting',
  completed: 'ok',
  failed: 'failed',
  rejected: 'rejected',
}

export default function WorkflowPage() {
  const library = useLibraryStore((s) => s.library)
  const [topic, setTopic] = useState('')
  const [subtitles, setSubtitles] = useState(true)
  const [music, setMusic] = useState<MusicPickerValue>(MUSIC_PICKER_DEFAULT)
  const [publishMode, setPublishMode] = useState<PublishMode>('review_publish')
  const [qcConfirm, setQcConfirm] = useState(false)
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
      {
        topic: topic.trim() || null,
        library: library ?? 'vng_insider',
        subtitles,
        music_track_id: music.music_track_id,
        beat_sync: music.beat_sync,
        music_volume: music.music_volume,
        publish_mode: publishMode,
        qc_mode: qcConfirm ? 'confirm' : 'auto',
      },
      { onError: (e) => toast.error(`Không khởi động được run: ${e.message}`) },
    )

  return (
    <div className="space-y-6 md:space-y-8">
      <PageHeader
        icon={Clapperboard}
        title="VNG Insider — Workflow"
        description="AI tự vận hành kênh TikTok: quét trend → kịch bản → dựng video → đăng → học. Human quyết định ở gate."
      />

      {/* Run controls — gom theo agent (Creative / Producer / Publisher) */}
      <RunControls
        topic={topic}
        setTopic={setTopic}
        subtitles={subtitles}
        setSubtitles={setSubtitles}
        music={music}
        setMusic={setMusic}
        publishMode={publishMode}
        setPublishMode={setPublishMode}
        qcConfirm={qcConfirm}
        setQcConfirm={setQcConfirm}
        onStart={handleStart}
        isPending={start.isPending}
        runActive={runActive}
        hasLibrary={!!library}
      />

      {/* Đóng vòng học [E]→[B]: báo trước vòng tới Creative học từ batch nào (nếu đã confirm) */}
      <InsightActiveBanner />

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

      {/* QC gate (confirm mode) — human duyệt / cho Creative viết lại / huỷ kịch bản */}
      {run.data && <ScriptGate run={run.data} />}

      {/* Human gate — hành động khớp chế độ đăng đã chốt lúc start (đọc run.publish_mode) */}
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
              description="Bấm “Chạy pipeline” để Orchestrator chạy end-to-end: Scout → Creative → Producer → Publisher → Analyst."
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
          {run.data && <RunStepList steps={run.data.steps} ordinal />}
        </CardContent>
      </Card>

      {/* Agent catalog */}
      {agents.data && (
        <section className="space-y-3">
          <h3 className="text-base font-semibold text-foreground">Agent &amp; tools</h3>
          <AgentCatalog agents={agents.data} />
        </section>
      )}

      {/* Trạng thái kết nối TikTok — để cuối trang, chỉ thông tin */}
      <TikTokConnectedLine />
    </div>
  )
}
