import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from '@/components/ui/sonner'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { queryClient } from '@/lib/query-client'
import { ErrorBoundary } from '@/components/error-boundary'
import { LibraryPicker } from '@/components/library-picker'
import StudioPage from '@/pages/studio'
import WarehousePage from '@/pages/warehouse'

// Vite `base` (theo VITE_BASE_ROUTE) → router basename, deploy dưới subpath vẫn chạy.
const BASENAME = import.meta.env.BASE_URL.replace(/\/+$/, '') || '/'

/** Nav 2 section (Tabs sync router) + library picker dùng chung mọi trang. */
function ShellNav() {
  const location = useLocation()
  const navigate = useNavigate()
  const section = location.pathname.startsWith('/warehouse') ? 'warehouse' : 'studio'

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Tabs
        value={section}
        onValueChange={(v) => navigate(v === 'warehouse' ? '/warehouse' : '/')}
      >
        <TabsList>
          <TabsTrigger value="studio">Tạo video</TabsTrigger>
          <TabsTrigger value="warehouse">Kho clip</TabsTrigger>
        </TabsList>
      </Tabs>
      <LibraryPicker />
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary appName="channel-builder">
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename={BASENAME}>
          <div className="channel-builder px-4 py-6 md:px-6 md:py-8">
            <div className="mx-auto max-w-7xl space-y-6 md:space-y-8">
              <ShellNav />
              <Routes>
                <Route index element={<StudioPage />} />
                <Route path="warehouse" element={<WarehousePage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
              <Toaster richColors closeButton />
            </div>
          </div>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
