import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

interface VlogFieldsProps {
  topic: string
  setTopic: (v: string) => void
  qcConfirm: boolean
  setQcConfirm: (v: boolean) => void
  runActive: boolean
}

/** Field riêng cho video Vlog — chủ đề (tuỳ chọn) + toggle xác nhận QC kịch bản. */
export function VlogFields({ topic, setTopic, qcConfirm, setQcConfirm, runActive }: VlogFieldsProps) {
  return (
    <div className="flex flex-col gap-3">
      <Input
        placeholder="Chủ đề (tuỳ chọn) — vd: canteen VNG, góc làm việc…"
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        disabled={runActive}
        className="md:max-w-md"
      />
      <div className="flex items-start gap-2">
        <Switch
          id="wf-qc-confirm"
          checked={qcConfirm}
          onCheckedChange={setQcConfirm}
          disabled={runActive}
          className="mt-0.5"
        />
        <div className="space-y-0.5">
          <Label htmlFor="wf-qc-confirm" className="text-sm text-muted-foreground">
            Cần xác nhận kịch bản (QC)
          </Label>
          <p className="text-xs text-muted-foreground">
            {qcConfirm
              ? 'Dừng ở bước QC để bạn duyệt / cho Creative viết lại / huỷ.'
              : 'Tự động: AI tự cho Creative viết lại nếu QC báo lỗi nặng (tối đa 2 lần) rồi dựng.'}
          </p>
        </div>
      </div>
    </div>
  )
}
