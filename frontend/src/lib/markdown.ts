// Safe markdown -> sanitized HTML for the Reports "markdown" section (API.md CharacterReport.sections).
// marked handles headings/bold/lists/links/tables; DOMPurify strips anything else (script tags,
// event handler attributes, etc.) before the result is ever handed to dangerouslySetInnerHTML.
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: false })

/** Renders a markdown string to sanitized HTML. Synchronous: the report fixtures/backend never
 * use marked's async extensions, so `marked.parse` always returns a string here. */
export function renderMarkdown(source: string): string {
  const html = marked.parse(source, { async: false }) as string
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'hr', 'strong', 'em', 'del', 'code', 'pre',
      'ul', 'ol', 'li', 'a', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span',
    ],
    ALLOWED_ATTR: ['href', 'title', 'target', 'rel'],
  })
}
