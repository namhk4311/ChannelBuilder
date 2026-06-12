import { useState } from 'react'
import { FolderOpen, Plus } from 'lucide-react'
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
import { toast } from 'sonner'
import { useAutoSelectLibrary, useCreateLibrary } from '@/hooks/use-libraries'
import { useLibraryStore } from '@/stores/library-store'

/** Dropdown chọn library (scope toàn app) + nút tạo library mới. */
export function LibraryPicker() {
  const libraries = useAutoSelectLibrary()
  const { library, setLibrary } = useLibraryStore()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [label, setLabel] = useState('')

  const create = useCreateLibrary((created) => {
    setLibrary(created)
    setOpen(false)
    setName('')
    setLabel('')
    toast.success(`Đã tạo thư viện “${created}”`)
  })

  const handleCreate = () =>
    create.mutate(
      { name: name.trim(), label: label.trim() || undefined },
      { onError: (e) => toast.error(`Không tạo được thư viện: ${e.message}`) },
    )

  return (
    <div className="flex items-center gap-2">
      <FolderOpen className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      <Select value={library ?? ''} onValueChange={(v) => v && setLibrary(v)}>
        <SelectTrigger className="min-w-44" aria-label="Chọn thư viện">
          <SelectValue placeholder="Chọn thư viện…" />
        </SelectTrigger>
        <SelectContent>
          {(libraries.data ?? []).map((l) => (
            <SelectItem key={l.name} value={l.name}>
              {l.label ?? l.name}
              <span className="ml-1 text-xs text-muted-foreground">({l.video_count} clip)</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button variant="outline" size="icon" aria-label="Tạo thư viện mới" onClick={() => setOpen(true)}>
        <Plus />
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-screen md:max-h-[85vh] md:max-w-md">
          <DialogHeader>
            <DialogTitle>Tạo thư viện mới</DialogTitle>
            <DialogDescription>
              Mỗi thư viện là 1 kho clip độc lập (taxonomy category riêng).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="lib-name">Slug (a-z, 0-9, _)</Label>
              <Input
                id="lib-name"
                placeholder="vd: nhatrang_travel"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lib-label">Tên hiển thị</Label>
              <Input
                id="lib-label"
                placeholder="vd: Du lịch Nha Trang"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Huỷ
            </Button>
            <Button onClick={handleCreate} disabled={!name.trim() || create.isPending}>
              Tạo thư viện
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
