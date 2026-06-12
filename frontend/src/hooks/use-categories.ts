import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createCategory, deleteCategory, fetchCategories } from '@/api/categories'

export function useCategories(library: string | null) {
  return useQuery({
    queryKey: ['categories', library],
    queryFn: () => fetchCategories(library!),
    enabled: !!library,
  })
}

export function useCreateCategory(library: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; label?: string; description?: string }) =>
      createCategory({ ...body, library: library! }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories', library] })
      qc.invalidateQueries({ queryKey: ['libraries'] })
    },
  })
}

export function useDeleteCategory(library: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => deleteCategory(name, library!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories', library] })
      qc.invalidateQueries({ queryKey: ['libraries'] })
    },
  })
}
