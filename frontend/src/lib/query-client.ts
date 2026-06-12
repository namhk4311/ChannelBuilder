import { QueryClient } from '@tanstack/react-query'

/** Shared react-query client. Tune defaults per sub-app if needed. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
})
