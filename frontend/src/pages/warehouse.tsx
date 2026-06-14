import { useState } from 'react'
import { Clapperboard, Upload } from 'lucide-react'
import { PageHeader } from '@/components/common/page-header'
import { EmptyState } from '@/components/common/empty-state'
import { LoadError } from '@/components/common/load-error'
import { ListSkeleton } from '@/components/common/list-skeleton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useLibraryStore } from '@/stores/library-store'
import { useCategories } from '@/hooks/use-categories'
import { useVideos } from '@/hooks/use-videos'
import { CategoryManager } from '@/components/category-manager'
import { ClipTable } from '@/components/clip-table'
import { MusicLibrary } from '@/components/music-library'
import { UploadClipDialog } from '@/components/upload-clip-dialog'

/** Kho clip — quản lý category + upload + duyệt clip trong library đang chọn. */
export default function WarehousePage() {
  const library = useLibraryStore((s) => s.library)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const categories = useCategories(library)
  const videos = useVideos(library, categoryFilter ?? undefined)

  const filtered = (videos.data ?? []).filter((v) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    return [v.file, v.description, v.id, v.clip_tag].some((s) => s?.toLowerCase().includes(q))
  })

  return (
    <div className="space-y-6 md:space-y-8">
      <PageHeader
        icon={Clapperboard}
        title="Kho clip"
        description="Nguồn footage cho Producer — LLM chỉ pick clip trong thư viện đang chọn."
        actions={
          <Button onClick={() => setUploadOpen(true)} disabled={!library}>
            <Upload /> Upload clip
          </Button>
        }
      />

      {!library && (
        <EmptyState
          variant="dashed"
          title="Chưa chọn thư viện"
          description="Chọn (hoặc tạo) thư viện ở góc trên để xem kho clip."
        />
      )}

      {library && (
        <>
          <CategoryManager library={library} />

          {/* Toolbar: 1 filter + search — giữ inline cả mobile */}
          <div className="flex flex-col md:flex-row md:items-center gap-2">
            <Select
              value={categoryFilter ?? 'all'}
              onValueChange={(v) => setCategoryFilter(v === 'all' ? null : v)}
            >
              <SelectTrigger className="md:w-56" aria-label="Lọc theo category">
                <SelectValue placeholder="Mọi category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Mọi category</SelectItem>
                {(categories.data ?? []).map((c) => (
                  <SelectItem key={c.name} value={c.name}>
                    {c.label ?? c.name} ({c.video_count})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              placeholder="Tìm theo tên file / mô tả / tag…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="md:ml-auto md:max-w-xs"
            />
          </div>

          {videos.isLoading && <ListSkeleton />}
          {videos.isError && (
            <LoadError
              title="Không tải được kho clip"
              description={(videos.error as Error).message}
              onRetry={() => videos.refetch()}
            />
          )}
          {videos.data && filtered.length === 0 && (
            <EmptyState
              variant={search || categoryFilter ? 'centered' : 'dashed'}
              title={search || categoryFilter ? 'Không có clip khớp bộ lọc' : 'Kho đang trống'}
              description={
                search || categoryFilter
                  ? 'Thử đổi từ khoá hoặc bỏ lọc category.'
                  : 'Upload clip đầu tiên để Producer có nguồn dựng video.'
              }
              action={
                !search && !categoryFilter ? (
                  <Button onClick={() => setUploadOpen(true)}>
                    <Upload /> Upload clip
                  </Button>
                ) : undefined
              }
            />
          )}
          {filtered.length > 0 && <ClipTable library={library} clips={filtered} />}

          <UploadClipDialog library={library} open={uploadOpen} onOpenChange={setUploadOpen} />
        </>
      )}

      {/* Thư viện nhạc nền — không scope theo library, dùng chung cho mọi Producer/Workflow */}
      <MusicLibrary />
    </div>
  )
}
