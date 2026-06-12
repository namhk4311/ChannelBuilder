import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { fetchProduceStatus, startProduce } from '@/api/produce'

/**
 * Produce = job nền phía backend (6 step, ~2-3 phút).
 * Start → nhận job_id → poll /produce/status/{job_id} mỗi 1.5s tới done/error.
 */
export function useProduce() {
  const [jobId, setJobId] = useState<string | null>(null)

  const start = useMutation({
    mutationFn: startProduce,
    onSuccess: (res) => setJobId(res.job_id),
  })

  const job = useQuery({
    queryKey: ['produce', jobId],
    queryFn: () => fetchProduceStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'done' || status === 'error' ? false : 1500
    },
  })

  const reset = () => setJobId(null)

  return { start, job, jobId, reset }
}
