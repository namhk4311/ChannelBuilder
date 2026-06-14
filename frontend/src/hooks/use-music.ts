import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteMusic, fetchMusic, uploadMusic } from '@/api/music'

export function useMusic() {
  return useQuery({
    queryKey: ['music'],
    queryFn: fetchMusic,
  })
}

export function useUploadMusic() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: uploadMusic,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['music'] }),
  })
}

export function useDeleteMusic() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteMusic,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['music'] }),
  })
}
