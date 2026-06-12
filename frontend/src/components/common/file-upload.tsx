import { useRef, useState, type DragEvent } from 'react'
import { FileVideo, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface FileUploadProps {
  accept?: string
  multiple?: boolean
  label?: string
  hint?: string
  onChange: (file: File | File[] | null) => void
}

/** Dropzone chọn file — thay cho FileUpload của lib cũ (giữ nguyên props call site). */
export function FileUpload({
  accept,
  multiple = false,
  label = 'Kéo thả hoặc bấm để chọn file',
  hint,
  onChange,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)

  const emit = (next: File[]) => {
    setFiles(next)
    if (next.length === 0) onChange(null)
    else onChange(multiple ? next : next[0])
  }

  const handleFiles = (list: FileList | null) => {
    if (!list?.length) return
    emit(multiple ? [...files, ...Array.from(list)] : [list[0]])
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={cn(
          'flex w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-6 text-center transition-colors',
          dragging ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40',
        )}
      >
        <Upload className="size-5 text-muted-foreground" aria-hidden />
        <span className="text-sm font-medium text-foreground">{label}</span>
        {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        className="hidden"
        onChange={(e) => {
          handleFiles(e.target.files)
          e.target.value = ''
        }}
      />

      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"
            >
              <FileVideo className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-foreground">{f.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {(f.size / 1024 / 1024).toFixed(1)} MB
              </span>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label={`Bỏ file ${f.name}`}
                onClick={(e) => {
                  e.stopPropagation()
                  emit(files.filter((_, j) => j !== i))
                }}
              >
                <X />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
