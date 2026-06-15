import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import type { GateLabel, GradedVideo } from '@/api/analyst'

// Badge nhãn — tái dùng token màu của step-status-chip (emerald/amber/red), không hard-code hex.
const LABEL_STYLE: Record<GateLabel, string> = {
  SCALE: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  MONITOR: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  KILL: 'bg-red-500/10 text-red-600 dark:text-red-400',
}

export function LabelPill({ label }: { label: GateLabel }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold',
        LABEL_STYLE[label],
      )}
    >
      {label}
    </span>
  )
}

/** Bảng video đã chấm bởi absolute gate — chu_de/hook/độ dài/retention/nhãn/lý do. */
export function GradedTable({ videos }: { videos: GradedVideo[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/50 hover:bg-muted/50">
            <TableHead className="h-8 text-xs">Video</TableHead>
            <TableHead className="h-8 text-xs">Hook</TableHead>
            <TableHead className="h-8 text-xs">Độ dài</TableHead>
            <TableHead className="h-8 text-xs">Giữ chân 3s</TableHead>
            <TableHead className="h-8 text-xs">Nhãn</TableHead>
            <TableHead className="h-8 text-xs">Lý do</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {videos.map((v) => (
            <TableRow key={v.id}>
              <TableCell className="max-w-[14rem] whitespace-normal align-top text-xs">
                <span className="font-medium text-foreground">{v.chu_de}</span>
                <span className="ml-1 text-muted-foreground">({v.id})</span>
              </TableCell>
              <TableCell className="align-top text-xs">{v.hook_type}</TableCell>
              <TableCell className="align-top text-xs tabular-nums">{v.do_dai}s</TableCell>
              <TableCell className="align-top text-xs tabular-nums">{v.retention_3s_pct}%</TableCell>
              <TableCell className="align-top">
                <LabelPill label={v.label} />
              </TableCell>
              <TableCell className="max-w-md whitespace-normal align-top text-xs text-muted-foreground">
                {v.reason}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
