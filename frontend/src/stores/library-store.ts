import { create } from 'zustand'

/** Library đang chọn — scope mọi query categories/videos/produce. */
interface LibraryState {
  library: string | null
  setLibrary: (name: string) => void
}

export const useLibraryStore = create<LibraryState>((set) => ({
  library: null,
  setLibrary: (name) => set({ library: name }),
}))
