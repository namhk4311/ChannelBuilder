import { get, post } from '@/lib/api-client'

export interface PublisherStatus {
  /** Đủ env TIKTOK_CLIENT_KEY/SECRET/REDIRECT_URI ở backend. */
  configured: boolean
  /** tokens.json đã có refresh_token — publish được, token tự refresh. */
  connected: boolean
  open_id: string | null
  scope: string | null
  redirect_uri: string | null
}

export interface OAuthExchangeResult extends PublisherStatus {
  status: 'ok' | 'failed'
  error: string | null
}

export const fetchPublisherStatus = () => get<PublisherStatus>('/publisher/status')

export const fetchOAuthUrl = () =>
  get<{ status: 'ok' | 'failed'; url: string | null; error: string | null }>(
    '/publisher/oauth/url',
  )

export const exchangeOAuthCode = (code: string) =>
  post<OAuthExchangeResult>('/publisher/oauth/exchange', { code })
