import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FileUpload } from '@/components/common/file-upload'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { toast } from 'sonner'
import { useCategories } from '@/hooks/use-categories'
import { useMoods, useUploadVideo } from '@/hooks/use-videos'

interface UploadClipDialogProps {
  library: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Upload 1 clip vào (library, category) — multipart POST /api/videos. */
export function UploadClipDialog({ library, open, onOpenChange }: UploadClipDialogProps) {
  const categories = useCategories(library)
  const moods = useMoods()
  const upload = useUploadVideo(library)

  const [file, setFile] = useState<File | null>(null)
  const [category, setCategory] = useState<string | null>(null)
  const [description, setDescription] = useState('')
  const [mood, setMood] = useState<string | null>(null)
  const [hasPeople, setHasPeople] = useState(false)

  const resetForm = () => {
    setFile(null)
    setCategory(null)
    setDescription('')
    setMood(null)
    setHasPeople(false)
  }

  const handleUpload = () =>
    upload.mutate(
      {
        file: file!,
        category: category!,
        description: description.trim(),
        mood: mood ?? '',
        has_people: hasPeople,
      },
      {
        onSuccess: (res) => {
          toast.success(
            `Đã upload “${res.filename}” (${res.duration_sec.toFixed(1)}s · ${res.resolution})`,
          )
          resetForm()
          onOpenChange(false)
        },
        onError: (e) => toast.error(`Upload thất bại: ${e.message}`),
      },
    )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-screen overflow-y-auto md:max-h-[85vh] md:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload clip</DialogTitle>
          <DialogDescription>
            Vào thư viện “{library}”. Mô tả + mood giúp LLM Producer chọn clip đúng ngữ cảnh.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <FileUpload
            accept="video/*"
            multiple={false}
            label="Kéo thả hoặc bấm để chọn video"
            hint="MP4/MOV — nên là khung dọc 9:16"
            onChange={(f) => setFile((f as File) ?? null)}
          />

          <div className="space-y-2">
            <Label>Category</Label>
            <Select value={category ?? ''} onValueChange={(v) => setCategory(v)}>
              <SelectTrigger aria-label="Chọn category">
                <SelectValue placeholder="Chọn category…" />
              </SelectTrigger>
              <SelectContent>
                {(categories.data ?? []).map((c) => (
                  <SelectItem key={c.name} value={c.name}>
                    {c.label ?? c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="clip-desc">Mô tả (LLM dùng để match kịch bản)</Label>
            <Input
              id="clip-desc"
              placeholder="vd: góc canteen giờ trưa, đông người, ánh sáng tự nhiên"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Mood</Label>
              <Select value={mood ?? ''} onValueChange={(v) => setMood(v)}>
                <SelectTrigger aria-label="Chọn mood">
                  <SelectValue placeholder="Chọn mood…" />
                </SelectTrigger>
                <SelectContent>
                  {(moods.data ?? []).map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2 md:pt-7">
              <Switch id="clip-people" checked={hasPeople} onCheckedChange={setHasPeople} />
              <Label htmlFor="clip-people" className="text-sm text-muted-foreground">
                Có người trong clip
              </Label>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Huỷ
          </Button>
          <Button onClick={handleUpload} disabled={!file || !category || upload.isPending}>
            {upload.isPending && <Spinner />}
            Upload
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
