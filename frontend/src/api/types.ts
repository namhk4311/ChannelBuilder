/** Backend ChannelBuilder — shared response shapes (FastAPI, see backend/README.md). */

export interface Library {
  name: string
  label: string | null
  description: string | null
  created_at: string | null
  category_count: number
  video_count: number
}

export interface Category {
  name: string
  label: string | null
  library: string
  default_tag: string | null
  description: string | null
  created_at: string | null
  video_count: number
}

export interface Clip {
  id: string
  file: string
  library: string
  category: string
  clip_tag: string
  description: string
  mood: string
  duration_sec: number
  has_people: boolean
  resolution: string
  notes: string
  object_name: string
  size_bytes: number
  uploaded_at: string | null
}

/** 1 idea từ POST /api/creative/ideas — LLM output, field có thể thiếu. */
export interface Idea {
  id?: string
  title?: string
  pillar?: string
  angle?: string
  trend_ref?: string | null
  insight_ref?: string | null
  est_fit?: number
  [key: string]: unknown
}

export interface IdeasResponse {
  status: 'ok' | 'failed'
  error: string | null
  ideas: Idea[]
}

export interface ShotLine {
  line?: number
  voiceover?: string
  duration_sec?: number
  clip_tag?: string
  alt_tag?: string | null
  scene_hint?: string
}

/** script_package từ POST /api/creative/script — script là 1 string liền mạch. */
export interface ScriptPackage {
  script: string
  text_hook?: string
  caption?: string
  hashtags?: string[]
  shot_list?: ShotLine[]
  idea?: Idea
  [key: string]: unknown
}

export interface ScriptResponse {
  status: 'ok' | 'failed'
  error: string | null
  package: ScriptPackage | null
  warnings?: string[]
}

export type ProduceJobStatus = 'queued' | 'running' | 'done' | 'error'

export interface ProduceResult {
  run_id: string
  voice_url: string
  silent_video_url: string
  output_url: string
  voice_duration_sec: number
  silent_video_duration_sec: number
  final_duration_sec: number
  selected_clips: string[]
  alignment: { action: string; [key: string]: unknown }
  subtitles: boolean
  subtitle_chunks: number
  tts_cache_hit: boolean
  stage_timings_sec: Record<string, number>
  total_elapsed_sec: number
}

export interface ProduceJob {
  status: ProduceJobStatus
  percent: number
  message: string
  result: ProduceResult | null
  error: string | null
}

/** 1 track nhạc nền — backend tự detect BPM + beats bằng librosa lúc upload. */
export interface MusicTrack {
  id: string
  label: string | null
  file: string
  object_name: string
  duration_sec: number | null
  bpm: number | null
  mood: string | null
  size_bytes: number | null
  uploaded_at: string | null
  preview_url: string
}

export interface MusicUploadResponse {
  id: string
  bpm: number
  duration_sec: number
  n_beats: number
}
