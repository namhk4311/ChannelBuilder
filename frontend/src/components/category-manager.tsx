import { useState } from 'react'
import { FolderPlus, Tags, Trash2 } from 'lucide-react'
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
import { ConfirmDialog } from '@/components/common/confirm-dialog'
import { EmptyState } from '@/components/common/empty-state'
import { toast } from 'sonner'
import { useCategories, useCreateCategory, useDeleteCategory } from '@/hooks/use-categories'

interface CategoryManagerProps {
  library: string
}

/** Quản lý category trong library đang chọn — tạo / xoá (xoá chỉ khi không còn video). */
export function CategoryManager({ library }: CategoryManagerProps) {
  const categories = useCategories(library)
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [label, setLabel] = useState('')
  const [deleting, setDeleting] = useState<string | null>(null)

  const create = useCreateCategory(library)
  const remove = useDeleteCategory(library)

  const handleCreate = () =>
    create.mutate(
      { name: name.trim(), label: label.trim() || undefined },
      {
        onSuccess: (res) => {
          setCreateOpen(false)
          setName('')
          setLabel('')
          toast.success(`Đã tạo category “${res.name}” (tag: ${res.default_tag})`)
        },
        onError: (e) => toast.error(`Không tạo được category: ${e.message}`),
      },
    )

  const handleDelete = () =>
    remove.mutate(deleting!, {
      onSuccess: () => {
        toast.success(`Đã xoá category “${deleting}”`)
        setDeleting(null)
      },
      onError: (e) => toast.error(`Không xoá được: ${e.message}`),
    })

  return (
    <Card className="p-4 md:p-6 gap-4">
      <div className="flex items-center gap-2">
        <Tags className="size-4 text-primary" aria-hidden />
        <h3 className="text-base font-semibold text-foreground">Categories</h3>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          onClick={() => setCreateOpen(true)}
        >
          <FolderPlus /> Thêm category
        </Button>
      </div>

      {categories.data?.length === 0 && (
        <EmptyState
          variant="dashed"
          title="Chưa có category"
          description="Tạo category trước khi upload clip — clip_tag được derive tự động từ tên category."
        />
      )}

      {!!categories.data?.length && (
        <ul className="flex flex-wrap gap-2">
          {categories.data.map((c) => (
            <li
              key={c.name}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 py-1 pl-3 pr-1 text-sm"
            >
              <span className="font-medium text-foreground">{c.label ?? c.name}</span>
              <span className="text-muted-foreground">· {c.video_count} clip</span>
              <Button
                variant="ghost"
                size="icon-sm"
                className="text-destructive"
                aria-label={`Xoá category ${c.name}`}
                disabled={c.video_count > 0}
                onClick={() => setDeleting(c.name)}
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-screen md:max-h-[85vh] md:max-w-md">
          <DialogHeader>
            <DialogTitle>Thêm category</DialogTitle>
            <DialogDescription>
              Thuộc thư viện “{library}”. Slug a-z 0-9 underscore, vd: canteen_cafe.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="cat-name">Slug</Label>
              <Input
                id="cat-name"
                placeholder="vd: canteen_cafe"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cat-label">Tên hiển thị</Label>
              <Input
                id="cat-label"
                placeholder="vd: Canteen & Café"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Huỷ
            </Button>
            <Button onClick={handleCreate} disabled={!name.trim() || create.isPending}>
              Tạo category
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => !open && setDeleting(null)}
        tone="red"
        icon={Trash2}
        title={`Xoá category “${deleting}”?`}
        description="Chỉ xoá được khi category không còn video."
        confirmLabel="Xoá"
        cancelLabel="Huỷ"
        onConfirm={handleDelete}
        isPending={remove.isPending}
      />
    </Card>
  )
}
