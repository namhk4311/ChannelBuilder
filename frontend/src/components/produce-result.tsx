import { AudioLines, Download, Film, VolumeX } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import type { ProduceResult } from '@/api/types'

interface ProduceResultViewProps {
  result: ProduceResult
}

/** Kết quả produce — preview video final + 3 link MinIO + metadata pipeline. */
export function ProduceResultView({ result }: ProduceResultViewProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-[auto_1fr] gap-4 md:gap-6">
      <video
        src={result.output_url}
        controls
        playsInline
        className="w-full max-w-60 mx-auto md:mx-0 rounded-xl border border-border bg-muted aspect-[9/16]"
      />

      <div className="space-y-4 min-w-0">
        <div className="flex flex-wrap gap-2">
          <a
            href={result.output_url}
            target="_blank"
            rel="noreferrer"
            className={buttonVariants()}
          >
            <Film /> Video final ({result.final_duration_sec.toFixed(1)}s)
          </a>
          <a
            href={result.silent_video_url}
            target="_blank"
            rel="noreferrer"
            className={buttonVariants({ variant: 'outline' })}
          >
            <VolumeX /> Bản silent
          </a>
          <a
            href={result.voice_url}
            target="_blank"
            rel="noreferrer"
            className={buttonVariants({ variant: 'outline' })}
          >
            <AudioLines /> Voice MP3 ({result.voice_duration_sec.toFixed(1)}s)
          </a>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <Badge variant="secondary">run {result.run_id}</Badge>
          <Badge variant="secondary">align: {result.alignment?.action ?? '?'}</Badge>
          <Badge variant="secondary">
            phụ đề: {result.subtitles ? `${result.subtitle_chunks} dòng` : 'không'}
          </Badge>
          <Badge variant="secondary">
            TTS cache {result.tts_cache_hit ? 'HIT' : 'MISS'}
          </Badge>
          <Badge variant="secondary">tổng {result.total_elapsed_sec.toFixed(0)}s</Badge>
        </div>

        {result.selected_clips?.length > 0 && (
          <div className="text-sm">
            <span className="font-medium text-foreground">
              {result.selected_clips.length} clip LLM đã chọn:{' '}
            </span>
            <span className="text-muted-foreground break-words">
              {result.selected_clips.join(' · ')}
            </span>
          </div>
        )}

        <div className="text-xs text-muted-foreground space-y-0.5">
          {Object.entries(result.stage_timings_sec ?? {}).map(([step, sec]) => (
            <div key={step} className="flex items-center gap-2">
              <Download className="size-3 opacity-0" aria-hidden />
              <span className="font-mono">{step}</span>
              <span>{sec.toFixed(1)}s</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
