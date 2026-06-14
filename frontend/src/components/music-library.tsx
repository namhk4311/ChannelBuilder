import { useState } from 'react'
import { Music, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { FileUpload } from '@/components/common/file-upload'
import { ListSkeleton } from '@/components/common/list-skeleton'
import { LoadError } from '@/components/common/load-error'
import { Spinner } from '@/components/ui/spinner'
import { useDeleteMusic, useMusic, useUploadMusic } from '@/hooks/use-music'

const MOOD_OPTIONS = ['chill', 'hype', 'cinematic', 'upbeat', 'emotional', 'trending']

const fmtDur = (sec: number | null) => {
  if (!sec) return '—'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

const fmtDate = (iso: string | null) => {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('vi-VN', {
      dateStyle: 'short',
      timeStyle: 'short',
    })
  } catch {
    return '—'
  }
}

/** Thư viện nhạc nền — upload + table list + delete.
 *  Dùng cho beat-sync ở ProducePanel / WorkflowPage qua MusicPicker. */
export function MusicLibrary() {
  const music = useMusic()
  const upload = useUploadMusic()
  const remove = useDeleteMusic()

  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [label, setLabel] = useState('')
  const [mood, setMood] = useState<string>('')
  const [deleting, setDeleting] = useState<string | null>(null)

  const handleUpload = () => {
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    fd.append('label', label.trim() || file.name)
    fd.append('mood', mood)
    upload.mutate(fd, {
      onSuccess: (res) => {
        toast.success(`Đã upload · ${res.bpm.toFixed(1)} BPM · ${res.n_beats} beats`)
        setOpen(false)
        setFile(null)
        setLabel('')
        setMood('')
      },
      onError: (e) => toast.error(`Upload lỗi: ${e.message}`),
    })
  }

  const handleDelete = () => {
    if (!deleting) return
    remove.mutate(deleting, {
      onSuccess: () => {
        toast.success('Đã xoá track')
        setDeleting(null)
      },
      onError: (e) => toast.error(`Không xoá được: ${e.message}`),
    })
  }

  const tracks = music.data ?? []

  return (
    <Card className="p-4 md:p-6 gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Music className="size-4 text-primary" aria-hidden />
        <h3 className="text-base font-semibold text-foreground">Thư viện nhạc nền</h3>
        <span className="text-sm text-muted-foreground">· dùng cho beat-sync</span>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          onClick={() => setOpen(true)}
        >
          <Plus /> Upload track
        </Button>
      </div>

      <p className="text-xs text-muted-foreground">
        Upload mp3 (download trend từ TikTok hoặc royalty-free). Backend tự detect BPM + beat
        times bằng librosa → dùng cho cut snap khi Producer dựng video.
      </p>

      {music.isLoading && <ListSkeleton />}
      {music.isError && (
        <LoadError
          title="Không tải được danh sách nhạc"
          description={(music.error as Error).message}
          onRetry={() => music.refetch()}
        />
      )}
      {music.data && tracks.length === 0 && (
        <EmptyState
          variant="dashed"
          title="Chưa có track nào"
          description="Upload mp3 đầu tiên — backend tự detect BPM và beat times."
          action={
            <Button onClick={() => setOpen(true)}>
              <Plus /> Upload track
            </Button>
          }
        />
      )}
      {tracks.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tên nhạc · File</TableHead>
                <TableHead className="w-24">BPM</TableHead>
                <TableHead className="w-20">Dur</TableHead>
                <TableHead className="w-32">Mood</TableHead>
                <TableHead className="w-72">Preview</TableHead>
                <TableHead className="w-32">Uploaded</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {tracks.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>
                    <div className="font-medium text-foreground truncate max-w-64">
                      {t.label ?? t.file}
                    </div>
                    <div className="text-xs text-muted-foreground truncate max-w-64">
                      {t.file}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="tabular-nums">
                      {(t.bpm ?? 0).toFixed(1)}
                    </Badge>
                  </TableCell>
                  <TableCell className="tabular-nums">{fmtDur(t.duration_sec)}</TableCell>
                  <TableCell>
                    {t.mood ? <Badge variant="secondary">{t.mood}</Badge> : '—'}
                  </TableCell>
                  <TableCell>
                    <audio
                      controls
                      preload="none"
                      src={t.preview_url}
                      className="h-8 w-full max-w-64"
                    />
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {fmtDate(t.uploaded_at)}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-destructive"
                      aria-label={`Xoá track ${t.label ?? t.file}`}
                      onClick={() => setDeleting(t.id)}
                    >
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-screen md:max-h-[85vh] md:max-w-md">
          <DialogHeader>
            <DialogTitle>Upload track nhạc nền</DialogTitle>
            <DialogDescription>
              Backend chạy librosa detect BPM + beat_times (~1-2s/track) rồi cache vào DB.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <FileUpload
              accept="audio/mpeg,audio/mp3,audio/*"
              label="Kéo thả mp3 hoặc bấm để chọn"
              hint="Định dạng tối ưu: mp3 stereo 128-320 kbps"
              onChange={(f) => setFile(f as File | null)}
            />
            <div className="space-y-2">
              <Label htmlFor="music-label">Tên nhạc</Label>
              <Input
                id="music-label"
                placeholder="vd: Lofi 120 BPM"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="music-mood">Mood (optional)</Label>
              <Select value={mood} onValueChange={setMood}>
                <SelectTrigger id="music-mood">
                  <SelectValue placeholder="— chọn mood —" />
                </SelectTrigger>
                <SelectContent>
                  {MOOD_OPTIONS.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={upload.isPending}>
              Huỷ
            </Button>
            <Button onClick={handleUpload} disabled={!file || upload.isPending}>
              {upload.isPending ? <Spinner /> : <Plus />} Upload track
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        tone="red"
        icon={Trash2}
        title="Xoá track này?"
        description="Sẽ xoá khỏi MinIO + DB. Producer đang dùng track này sẽ không bị ảnh hưởng (đã render xong)."
        confirmLabel="Xoá"
        cancelLabel="Huỷ"
        onConfirm={handleDelete}
        isPending={remove.isPending}
      />
    </Card>
  )
}
