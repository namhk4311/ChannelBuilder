import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { PageHeader } from '@/components/common/page-header'
import { EmptyState } from '@/components/common/empty-state'
import type { Idea, ScriptPackage } from '@/api/types'
import { useLibraryStore } from '@/stores/library-store'
import { IdeaPanel } from '@/components/idea-panel'
import { ScriptPanel } from '@/components/script-panel'
import { ProducePanel } from '@/components/produce-panel'

/**
 * Studio — flow tạo video TikTok mới:
 * idea (Creative) → script (Creative, editable) → produce (Producer, poll job).
 */
export default function StudioPage() {
  const library = useLibraryStore((s) => s.library)

  const [targetDuration, setTargetDuration] = useState(48)
  const [selectedIdea, setSelectedIdea] = useState<Idea | null>(null)
  const [pkg, setPkg] = useState<ScriptPackage | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [script, setScript] = useState('')
  // Đổi kịch bản mới → remount ProducePanel để bỏ job/result cũ.
  const [produceKey, setProduceKey] = useState(0)

  const handlePackage = (newPkg: ScriptPackage, newWarnings: string[]) => {
    setPkg(newPkg)
    setWarnings(newWarnings)
    setScript(newPkg.script ?? '')
    setProduceKey((k) => k + 1)
  }

  return (
    <div className="space-y-6 md:space-y-8">
      <PageHeader
        icon={Sparkles}
        title="Tạo video"
        description="Sinh ý tưởng → viết kịch bản → dựng video có lồng tiếng từ kho clip. AI thực thi, bạn quyết định."
      />

      {!library && (
        <EmptyState
          variant="dashed"
          title="Chưa chọn thư viện"
          description="Chọn (hoặc tạo) thư viện clip ở góc trên — Producer chỉ pick clip trong thư viện đang chọn."
        />
      )}

      {library && (
        <>
          <IdeaPanel
            targetDuration={targetDuration}
            onTargetDuration={setTargetDuration}
            selectedIdea={selectedIdea}
            onSelectIdea={setSelectedIdea}
          />
          <ScriptPanel
            idea={selectedIdea}
            targetDuration={targetDuration}
            script={script}
            onScriptChange={setScript}
            pkg={pkg}
            warnings={warnings}
            onPackage={handlePackage}
          />
          <ProducePanel key={produceKey} script={script} library={library} />
        </>
      )}
    </div>
  )
}
