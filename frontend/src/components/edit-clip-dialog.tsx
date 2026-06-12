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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { toast } from 'sonner'
import type { Clip } from '@/api/types'
import { useCategories } from '@/hooks/use-categories'
import { useMoods, useUpdateVideo } from '@/hooks/use-videos'

interface EditClipDialogProps {
  library: string
  clip: Clip | null
  onOpenChange: (open: boolean) => void
}

/** Sửa metadata clip — PATCH /api/videos/{id} (clip_tag tự derive lại khi đổi category). */
export function EditClipDialog({ library, clip, onOpenChange }: EditClipDialogProps) {
  return (
    <Dialog open={!!clip} onOpenChange={onOpenChange}>
      {/* key theo clip.id → state form khởi tạo lại từ props, không cần effect */}
      {clip && (
        <EditClipForm key={clip.id} library={library} clip={clip} onOpenChange={onOpenChange} />
      )}
    </Dialog>
  )
}

function EditClipForm({
  library,
  clip,
  onOpenChange,
}: {
  library: string
  clip: Clip
  onOpenChange: (open: boolean) => void
}) {
  const categories = useCategories(library)
  const moods = useMoods()
  const update = useUpdateVideo(library)

  const [category, setCategory] = useState<string | null>(clip.category)
  const [description, setDescription] = useState(clip.description ?? '')
  const [mood, setMood] = useState<string | null>(clip.mood || null)
  const [hasPeople, setHasPeople] = useState(clip.has_people)

  const handleSave = () =>
    update.mutate(
      {
        id: clip.id,
        category: category ?? undefined,
        description,
        mood: mood ?? '',
        has_people: hasPeople,
      },
      {
        onSuccess: () => {
          toast.success('Đã cập nhật clip')
          onOpenChange(false)
        },
        onError: (e) => toast.error(`Không cập nhật được: ${e.message}`),
      },
    )

  return (
    <DialogContent className="max-h-screen overflow-y-auto md:max-h-[85vh] md:max-w-lg">
      <DialogHeader>
        <DialogTitle>Sửa clip {clip.id}</DialogTitle>
        <DialogDescription>{clip.file}</DialogDescription>
      </DialogHeader>

      <div className="space-y-4">
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
          <Label htmlFor="edit-desc">Mô tả</Label>
          <Input
            id="edit-desc"
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
            <Switch id="edit-people" checked={hasPeople} onCheckedChange={setHasPeople} />
            <Label htmlFor="edit-people" className="text-sm text-muted-foreground">
              Có người trong clip
            </Label>
          </div>
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Huỷ
        </Button>
        <Button onClick={handleSave} disabled={update.isPending}>
          Lưu
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
