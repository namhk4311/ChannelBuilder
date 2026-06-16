import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  backfillDurations,
  deleteVideo,
  fetchMoods,
  fetchVideos,
  updateVideo,
  uploadVideo,
  type UploadVideoInput,
} from '@/api/videos'

export function useVideos(library: string | null, category?: string) {
  return useQuery({
    queryKey: ['videos', library, category ?? null],
    queryFn: () => fetchVideos(library!, category),
    enabled: !!library,
  })
}

export function useMoods() {
  return useQuery({
    queryKey: ['moods'],
    queryFn: fetchMoods,
    select: (d) => d.moods,
    staleTime: Infinity,
  })
}

function useInvalidateVideos(library: string | null) {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['videos', library] })
    qc.invalidateQueries({ queryKey: ['categories', library] })
    qc.invalidateQueries({ queryKey: ['libraries'] })
  }
}

export function useUploadVideo(library: string | null) {
  const invalidate = useInvalidateVideos(library)
  return useMutation({
    mutationFn: (input: Omit<UploadVideoInput, 'library'>) =>
      uploadVideo({ ...input, library: library! }),
    onSuccess: invalidate,
  })
}

export function useUpdateVideo(library: string | null) {
  const invalidate = useInvalidateVideos(library)
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Parameters<typeof updateVideo>[1]) =>
      updateVideo(id, body),
    onSuccess: invalidate,
  })
}

export function useDeleteVideo(library: string | null) {
  const invalidate = useInvalidateVideos(library)
  return useMutation({
    mutationFn: deleteVideo,
    onSuccess: invalidate,
  })
}

export function useBackfillDurations(library: string | null) {
  const invalidate = useInvalidateVideos(library)
  return useMutation({
    mutationFn: () => backfillDurations(library ?? undefined),
    onSuccess: invalidate,
  })
}
