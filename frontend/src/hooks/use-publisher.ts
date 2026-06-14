import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  cancelSchedule,
  exchangeOAuthCode,
  fetchPublisherStatus,
  listSchedule,
  runScheduleNow,
  schedulePost,
  type OAuthExchangeResult,
} from '@/api/publisher'

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

// ─── Queue lịch đăng ──────────────────────────────────────────────────────────

const SCHEDULE_KEY = ['publisher', 'schedule']

/** List calendar; poll 5s để theo dõi tick đăng bài tới giờ. */
export function useSchedule(status?: string) {
  return useQuery({
    queryKey: [...SCHEDULE_KEY, status ?? 'all'],
    queryFn: () => listSchedule(status),
    select: (d) => d.posts,
    refetchInterval: 5_000,
  })
}

export function useSchedulePost() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: schedulePost,
    onSuccess: () => qc.invalidateQueries({ queryKey: SCHEDULE_KEY }),
  })
}

export function useCancelSchedule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: cancelSchedule,
    onSuccess: () => qc.invalidateQueries({ queryKey: SCHEDULE_KEY }),
  })
}

export function useRunScheduleNow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: runScheduleNow,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SCHEDULE_KEY })
      qc.invalidateQueries({ queryKey: ['workflow', 'runs'] })
    },
  })
}
