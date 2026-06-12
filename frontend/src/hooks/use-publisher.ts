import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { exchangeOAuthCode, fetchPublisherStatus, type OAuthExchangeResult } from '@/api/publisher'

export function usePublisherStatus() {
  return useQuery({
    queryKey: ['publisher', 'status'],
    queryFn: fetchPublisherStatus,
    staleTime: 30_000,
  })
}

export function useOAuthExchange(onDone: (r: OAuthExchangeResult) => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: exchangeOAuthCode,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['publisher', 'status'] })
      onDone(r)
    },
  })
}
