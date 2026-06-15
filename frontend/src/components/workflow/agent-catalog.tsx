import { AlertTriangle, Wrench } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { Agent } from '@/api/workflow'

/** Catalog 5 agent + tool definitions đọc live từ TOOL_DEFINITIONS của từng package. */
export function AgentCatalog({ agents }: { agents: Agent[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
      {agents.map((agent) => (
        <Card key={agent.key}>
          <CardContent className="space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <span className="inline-flex items-center justify-center size-8 rounded-lg bg-primary/10 text-primary text-sm font-semibold shrink-0">
                  {agent.code}
                </span>
                <h3 className="text-base font-semibold text-foreground">{agent.name}</h3>
              </div>
              <span
                className={cn(
                  'rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap',
                  agent.build_status === 'built'
                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                    : 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
                )}
              >
                {agent.build_status === 'built' ? 'Đã build' : 'Chưa wire'}
              </span>
            </div>

            <p className="text-sm text-muted-foreground">{agent.role}</p>

            {agent.import_error && (
              <p className="flex items-start gap-1.5 text-xs text-destructive">
                <AlertTriangle className="size-3.5 shrink-0 mt-0.5" />
                {agent.import_error}
              </p>
            )}

            <ul className="space-y-1.5">
              {agent.tools.map((tool) => (
                <li key={tool.name} className="flex items-start gap-2 text-sm">
                  <Wrench className="size-3.5 text-muted-foreground shrink-0 mt-1" />
                  <div className="min-w-0">
                    <code className="text-xs font-medium text-foreground">{tool.name}</code>
                    <p className="text-xs text-muted-foreground line-clamp-2">
                      {tool.description}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
