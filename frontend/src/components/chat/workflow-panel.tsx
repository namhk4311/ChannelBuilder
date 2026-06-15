import type { WorkflowRun } from '@/api/workflow'
import { RunStepList } from '@/components/workflow/run-step-list'

/**
 * Panel pipeline view-only cho sidebar phải (cowork style): timeline từng step +
 * metadata (bấm mở). KHÔNG chứa gate cần thao tác — gate confirm nằm trong khung chat.
 */
export function WorkflowPanel({ run }: { run: WorkflowRun }) {
  return <RunStepList steps={run.steps} ordinal />
}
