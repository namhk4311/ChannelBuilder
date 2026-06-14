import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/** Session chat hiện tại — persist vào localStorage để reload không mất cuộc đang mở. */
interface ChatState {
  sessionId: string | null
  setSessionId: (id: string | null) => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      sessionId: null,
      setSessionId: (id) => set({ sessionId: id }),
    }),
    { name: 'vng-chat-session' },
  ),
)
