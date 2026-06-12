import axios, { AxiosError } from 'axios'

/** Normalized error shape thrown by the client — catch this in UI code. */
export class ApiError extends Error {
  status: number
  code?: string
  details?: unknown
  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

/**
 * Shared axios instance. Configure via `.env` (VITE_API_BASE_URL).
 * Response interceptor normalize lỗi về `ApiError` — backend không có auth.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// --- Response: normalize errors --------------------------------------------
apiClient.interceptors.response.use(
  (res) => res,
  (error: AxiosError<{ message?: string; error?: string; code?: string; detail?: unknown }>) => {
    if (error.response) {
      const { status, data } = error.response
      throw new ApiError(
        data?.message || data?.error || error.message || 'Request failed',
        status,
        data?.code,
        data?.detail ?? data,
      )
    }
    if (error.request) {
      throw new ApiError('Network error — no response from server', 0)
    }
    throw new ApiError(error.message || 'Request setup failed', 0)
  },
)

// --- Typed helpers ----------------------------------------------------------
export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const { data } = await apiClient.get<T>(url, { params })
  return data
}

export async function post<T>(
  url: string,
  body?: unknown,
  config?: { timeout?: number },
): Promise<T> {
  const { data } = await apiClient.post<T>(url, body, config)
  return data
}

/** Multipart upload — để axios tự set boundary, không dùng Content-Type json mặc định. */
export async function postForm<T>(url: string, form: FormData): Promise<T> {
  const { data } = await apiClient.post<T>(url, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 0, // upload video có thể lâu — không giới hạn
  })
  return data
}

export async function put<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await apiClient.put<T>(url, body)
  return data
}

export async function patch<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await apiClient.patch<T>(url, body)
  return data
}

export async function del<T>(url: string): Promise<T> {
  const { data } = await apiClient.delete<T>(url)
  return data
}
