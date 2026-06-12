import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { CheckCircle2, ExternalLink, KeyRound } from 'lucide-react'
import { toast } from 'sonner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { fetchOAuthUrl } from '@/api/publisher'
import { useOAuthExchange, usePublisherStatus } from '@/hooks/use-publisher'

/** User dán nguyên URL callback cũng được — tự rút ?code= ra. */
function extractCode(input: string): string {
  const t = input.trim()
  try {
    const code = new URL(t).searchParams.get('code')
    if (code) return code
  } catch {
    /* không phải URL → coi như code thuần */
  }
  return t
}

/**
 * Kết nối TikTok cho Publisher [D] — OAuth 1 lần, token tự refresh.
 * TikTok không cho đăng ký redirect localhost → user đăng nhập ở tab mới,
 * rồi dán code (hoặc nguyên URL trang callback) vào đây.
 */
export function TikTokConnectCard() {
  const status = usePublisherStatus()
  const [code, setCode] = useState('')
  const exchange = useOAuthExchange((r) => {
    if (r.status === 'ok') {
      toast.success(`Đã kết nối TikTok (open_id ${r.open_id ?? '?'})`)
      setCode('')
    } else {
      toast.error(`Đổi code thất bại: ${r.error}`)
    }
  })

  // Nếu callback.html redirect về UI kèm ?code=... → tự đổi token, khỏi dán tay.
  // (code TikTok chỉ dùng được 1 lần — ref chặn StrictMode double-fire.)
  const [searchParams, setSearchParams] = useSearchParams()
  const autoFired = useRef(false)
  const urlCode = searchParams.get('code')
  const connected = status.data?.connected
  useEffect(() => {
    if (!urlCode || connected === undefined || autoFired.current) return
    autoFired.current = true
    if (!connected) exchange.mutate(urlCode)
    const next = new URLSearchParams(searchParams)
    for (const k of ['code', 'scopes', 'state']) next.delete(k)
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ chạy khi có code trên URL
  }, [urlCode, connected])

  if (!status.data) return null

  if (status.data.connected) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <CheckCircle2 className="size-3.5 text-emerald-600 dark:text-emerald-400" />
        TikTok đã kết nối · open_id{' '}
        <code className="text-foreground">{status.data.open_id}</code> · scope{' '}
        <code className="text-foreground">{status.data.scope}</code> — token tự refresh, không
        cần OAuth lại.
      </p>
    )
  }

  const openAuthorize = async () => {
    try {
      const r = await fetchOAuthUrl()
      if (r.status !== 'ok' || !r.url) throw new Error(r.error ?? 'Backend không trả URL')
      window.open(r.url, '_blank', 'noopener')
    } catch (e) {
      toast.error(`Không lấy được link đăng nhập: ${(e as Error).message}`)
    }
  }

  const submitCode = () => {
    const c = extractCode(code)
    if (!c) return
    exchange.mutate(c)
  }

  return (
    <Alert variant="warning">
      <KeyRound />
      <AlertTitle>TikTok chưa kết nối — bước "Đăng TikTok" ở mode live sẽ lỗi</AlertTitle>
      <AlertDescription>
        <div className="space-y-2 w-full">
          <p>
            Kết nối 1 lần là xong (token tự refresh):{' '}
            <span className="text-foreground">
              ① bấm nút đăng nhập TikTok → ② trang callback hiện code → ③ dán code (hoặc
              nguyên URL trang đó) vào ô dưới.
            </span>
            {!status.data.configured && (
              <span className="text-destructive">
                {' '}
                Backend thiếu env TIKTOK_CLIENT_KEY/SECRET/REDIRECT_URI — bổ sung `.env` trước.
              </span>
            )}
          </p>
          <div className="flex flex-col sm:flex-row gap-2">
            <Button size="sm" onClick={openAuthorize} disabled={!status.data.configured}>
              <ExternalLink /> Đăng nhập TikTok
            </Button>
            <Input
              placeholder="Dán code hoặc URL callback…"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submitCode()}
              className="sm:max-w-sm h-8"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={submitCode}
              disabled={!code.trim() || exchange.isPending}
            >
              {exchange.isPending && <Spinner />}
              Lưu code
            </Button>
          </div>
        </div>
      </AlertDescription>
    </Alert>
  )
}
