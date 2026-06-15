import { useEffect, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { Clip } from '@/api/types'

interface ClipPreviewDialogProps {
  clip: Clip | null
  onOpenChange: (open: boolean) => void
}

/** Xem lại 1 clip gốc (scene) — player video portrait + metadata. URL presigned từ backend. */
export function ClipPreviewDialog({ clip, onOpenChange }: ClipPreviewDialogProps) {
  // Lỗi tải video (codec .MOV trình duyệt không phát được / URL hết hạn) → hiện link mở tab.
  const [loadError, setLoadError] = useState(false)
  useEffect(() => setLoadError(false), [clip?.id])

  return (
    <Dialog open={!!clip} onOpenChange={onOpenChange}>
      {clip && (
        <DialogContent className="max-h-screen overflow-y-auto md:max-h-[94vh] md:max-w-lg">
          <DialogHeader className="min-w-0">
            <DialogTitle className="truncate pr-6 text-base" title={clip.file}>
              {clip.file}
            </DialogTitle>
            <DialogDescription>
              {[
                clip.clip_tag || clip.category,
                clip.mood,
                `${clip.duration_sec.toFixed(1)}s`,
                clip.resolution,
              ]
                .filter(Boolean)
                .join(' · ')}
            </DialogDescription>
          </DialogHeader>

          {!clip.preview_url ? (
            <p className="rounded-lg border border-dashed border-border py-10 text-center text-sm text-muted-foreground">
              Chưa có link xem clip — thử tải lại trang (Cmd/Ctrl + R).
            </p>
          ) : loadError ? (
            <div className="space-y-3 rounded-lg border border-dashed border-border py-8 text-center">
              <p className="text-sm text-muted-foreground">
                Trình duyệt không phát được định dạng clip này (thường là .MOV).
              </p>
              <a
                href={clip.preview_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
              >
                <ExternalLink className="size-4" /> Mở / tải clip ở tab mới
              </a>
            </div>
          ) : (
            // key=id → đổi clip thì remount player, không giữ frame clip cũ
            <video
              key={clip.id}
              src={clip.preview_url}
              controls
              autoPlay
              playsInline
              onError={() => setLoadError(true)}
              className="mx-auto max-h-[78vh] w-auto rounded-lg border border-border bg-black"
            />
          )}

          {clip.description && (
            <p className="text-sm text-muted-foreground">{clip.description}</p>
          )}
          {clip.notes && (
            <div className="flex items-center gap-2">
              <Badge variant="outline">Ghi chú</Badge>
              <span className="text-sm text-muted-foreground">{clip.notes}</span>
            </div>
          )}
        </DialogContent>
      )}
    </Dialog>
  )
}
