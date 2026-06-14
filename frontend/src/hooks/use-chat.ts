import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createChatSession,
  deleteChatSession,
  fetchChatSession,
  listChatSessions,
  sendChatMessage,
  type ChatSession,
} from '@/api/chat'

/** Lấy state hội thoại. Chỉ cập nhật qua mutation (setQueryData) — không poll nền. */
export function useChatSession(id: string | null) {
  return useQuery({
    queryKey: ['chat', id],
    queryFn: () => fetchChatSession(id!),
    enabled: !!id,
    staleTime: Infinity,
    retry: false, // 404 (đã xoá / id lạ) → để page tự tạo session mới
  })
}

/** Danh sách cuộc chat cho sidebar (mới nhất trước). */
export function useChatSessions() {
  return useQuery({
    queryKey: ['chat', 'list'],
    queryFn: listChatSessions,
    select: (d) => d.sessions,
  })
}

export function useCreateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createChatSession,
    onSuccess: (s) => {
      qc.setQueryData(['chat', s.id], s)
      qc.invalidateQueries({ queryKey: ['chat', 'list'] })
    },
  })
}

/** Gửi 1 message → conductor trả state mới (reply LLM + ui + run_id).
 *  Optimistic: append ngay tin nhắn user vào cache để nó hiện TRƯỚC khi loader
 *  agent xuất hiện; server trả về thì thay bằng state thật (user + reply). */
export function useSendMessage(id: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (text: string) => sendChatMessage(id!, text),
    onMutate: async (text: string) => {
      await qc.cancelQueries({ queryKey: ['chat', id] })
      const prev = qc.getQueryData<ChatSession>(['chat', id])
      if (prev) {
        qc.setQueryData<ChatSession>(['chat', id], {
          ...prev,
          messages: [...prev.messages, { role: 'user', content: text }],
          // ẩn chips/starters trong lúc chờ (ui mới sẽ về cùng response)
          ui: { ...prev.ui, kind: 'pending', options: [] },
        })
      }
      return { prev }
    },
    onError: (_e, _text, ctx) => {
      if (ctx?.prev) qc.setQueryData(['chat', id], ctx.prev) // rollback
    },
    onSuccess: (s) => {
      qc.setQueryData(['chat', s.id], s)
      qc.invalidateQueries({ queryKey: ['chat', 'list'] }) // title + thứ tự cập nhật
    },
  })
}

export function useDeleteSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteChatSession(id),
    onSuccess: (_d, id) => {
      qc.removeQueries({ queryKey: ['chat', id] })
      qc.invalidateQueries({ queryKey: ['chat', 'list'] })
    },
  })
}
