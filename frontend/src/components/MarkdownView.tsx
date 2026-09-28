import { useMemo } from 'react'
import { renderMarkdown } from '../lib/markdown'

/** Renders a report's `{kind: "markdown"}` section body: headings, bold, lists, links and tables,
 * sanitized by DOMPurify before it ever reaches the DOM (see lib/markdown.ts). */
export function MarkdownView({ body, className = '' }: { body: string; className?: string }) {
  const html = useMemo(() => renderMarkdown(body), [body])
  return <div className={`md-body ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
}
