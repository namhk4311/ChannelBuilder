import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createLibrary, fetchLibraries } from '@/api/libraries'
import { useLibraryStore } from '@/stores/library-store'

export function useLibraries() {
  return useQuery({
    queryKey: ['libraries'],
    queryFn: fetchLibraries,
    staleTime: 60_000,
  })
}

/** Tự chọn library đầu tiên khi chưa chọn gì (ưu tiên vng_insider nếu có). */
export function useAutoSelectLibrary() {
  const libraries = useLibraries()
  const { library, setLibrary } = useLibraryStore()

  useEffect(() => {
    if (library || !libraries.data?.length) return
    const preferred = libraries.data.find((l) => l.name === 'vng_insider') ?? libraries.data[0]
    setLibrary(preferred.name)
  }, [library, libraries.data, setLibrary])

  return libraries
}

export function useCreateLibrary(onCreated?: (name: string) => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createLibrary,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['libraries'] })
      onCreated?.(res.name)
    },
  })
}
