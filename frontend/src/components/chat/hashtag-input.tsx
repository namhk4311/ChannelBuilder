import { useState, type KeyboardEvent } from 'react'
import { X } from 'lucide-react'

/** Chuẩn hoá 1 token thành hashtag: bỏ # thừa rồi thêm đúng 1 dấu #. */
function normalize(raw: string): string {
  const t = raw.trim().replace(/^#+/, '')
  return t ? `#${t}` : ''
}

interface HashtagInputProps {
  value: string[]
  onChange: (next: string[]) => void
}

/** Nhập hashtag dạng chip: mỗi tag 1 chip có nút xoá; Enter/space/phẩy để thêm. */
export function HashtagInput({ value, onChange }: HashtagInputProps) {
  const [text, setText] = useState('')

  const add = (raw: string) => {
    const tag = normalize(raw)
    setText('')
    if (!tag) return
    if (value.some((t) => t.toLowerCase() === tag.toLowerCase())) return // bỏ trùng
    onChange([...value, tag])
  }
  const removeAt = (i: number) => onChange(value.filter((_, idx) => idx !== i))

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
      e.preventDefault()
      add(text)
    } else if (e.key === 'Backspace' && !text && value.length) {
      removeAt(value.length - 1)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-input bg-background p-2 transition-colors focus-within:border-ring">
      {value.map((tag, i) => (
        <span
          key={`${tag}-${i}`}
          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
        >
          {tag}
          <button
            type="button"
            onClick={() => removeAt(i)}
            className="text-primary/60 transition-colors hover:text-primary"
            aria-label={`Xoá ${tag}`}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => add(text)}
        placeholder={value.length ? 'thêm tag…' : '#VNG #Campus …'}
        className="min-w-24 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
      />
    </div>
  )
}
