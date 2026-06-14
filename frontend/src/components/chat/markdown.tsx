import { Fragment, type ReactNode } from 'react'

/**
 * Markdown tối giản (không thêm dependency) — đủ cho reply của conductor:
 * **bold**, `code`, bullet list (- / * / •), numbered list (1.), xuống dòng,
 * và tách đoạn theo dòng trống. An toàn XSS (build React node, không innerHTML).
 */

const INLINE_RE = /(\*\*([^*]+)\*\*|`([^`]+)`)/g

function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  let last = 0
  let key = 0
  let m: RegExpExecArray | null
  INLINE_RE.lastIndex = 0
  while ((m = INLINE_RE.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index))
    if (m[2] !== undefined) {
      out.push(<strong key={key++}>{m[2]}</strong>)
    } else if (m[3] !== undefined) {
      out.push(
        <code key={key++} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
          {m[3]}
        </code>,
      )
    }
    last = INLINE_RE.lastIndex
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

const BULLET_RE = /^\s*[-*•]\s+/
const NUM_RE = /^\s*\d+\.\s+/

export function Markdown({ content }: { content: string }) {
  const blocks = (content ?? '').trim().split(/\n{2,}/)
  return (
    <div className="space-y-2.5 text-sm leading-relaxed">
      {blocks.map((block, bi) => {
        const lines = block.split('\n').filter((l) => l.length > 0)
        if (lines.length === 0) return null

        if (lines.every((l) => BULLET_RE.test(l))) {
          return (
            <ul key={bi} className="list-disc space-y-1 pl-5">
              {lines.map((l, li) => (
                <li key={li}>{renderInline(l.replace(BULLET_RE, ''))}</li>
              ))}
            </ul>
          )
        }
        if (lines.every((l) => NUM_RE.test(l))) {
          return (
            <ol key={bi} className="list-decimal space-y-1 pl-5">
              {lines.map((l, li) => (
                <li key={li}>{renderInline(l.replace(NUM_RE, ''))}</li>
              ))}
            </ol>
          )
        }
        return (
          <p key={bi} className="whitespace-pre-wrap">
            {lines.map((l, li) => (
              <Fragment key={li}>
                {renderInline(l)}
                {li < lines.length - 1 && <br />}
              </Fragment>
            ))}
          </p>
        )
      })}
    </div>
  )
}
