import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { confirmScale, fetchInsight } from '@/api/analyst'

/** insight_digest đang active — bước [E] trong run đọc để hiện trạng thái "đã xác nhận". */
export function useInsight() {
  return useQuery({ queryKey: ['analyst', 'insight'], queryFn: fetchInsight })
}

/** Xác nhận scale → persist insight active → invalidate để cập nhật trạng thái. */
export function useConfirmScale() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { batch: string; scaleIds?: string[] }) =>
      confirmScale(args.batch, args.scaleIds),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['analyst', 'insight'] }),
  })
}
