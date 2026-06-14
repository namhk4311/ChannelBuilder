import { Button } from '@/components/ui/button'
import type { ChatOption } from '@/api/chat'

interface OptionChipsProps {
  options: ChatOption[]
  disabled?: boolean
  /** Bấm chip = gửi label như 1 lượt user (sugar cho việc gõ). */
  onPick: (label: string) => void
}

/** Quick-reply chips từ conductor (vd chọn thư viện / nhạc). */
export function OptionChips({ options, disabled, onPick }: OptionChipsProps) {
  if (!options?.length) return null
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o, i) => (
        <Button
          key={`${o.value ?? 'none'}-${i}`}
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => onPick(o.label)}
          className="h-auto rounded-full py-1.5"
        >
          <span className="font-medium">{o.label}</span>
          {o.hint && <span className="ml-1.5 text-xs text-muted-foreground">{o.hint}</span>}
        </Button>
      ))}
    </div>
  )
}
