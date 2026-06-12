import { AlertCircle, RotateCcw } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

interface LoadErrorProps {
  title: string
  description?: string
  onRetry?: () => void
}

/** Lỗi tải dữ liệu + nút thử lại. */
export function LoadError({ title, description, onRetry }: LoadErrorProps) {
  return (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        {description && <p>{description}</p>}
        {onRetry && (
          <Button variant="outline" size="sm" className="mt-2" onClick={onRetry}>
            <RotateCcw /> Thử lại
          </Button>
        )}
      </AlertDescription>
    </Alert>
  )
}
