/**
 * Lightweight markdown renderer for LLM responses.
 * Handles: bold, italic, links, ordered/unordered lists, line breaks, tables.
 * No external dependencies.
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderInline(text: string): string {
  let result = escapeHtml(text)
  // Bold: **text** or __text__
  result = result.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  result = result.replace(/__(.+?)__/g, '<strong>$1</strong>')
  // Italic: *text* or _text_ (but not inside words for _)
  result = result.replace(/\*(.+?)\*/g, '<em>$1</em>')
  result = result.replace(/(?<!\w)_(.+?)_(?!\w)/g, '<em>$1</em>')
  // Inline code: `text`
  result = result.replace(/`(.+?)`/g, '<code class="zk-inline-code">$1</code>')
  // Links: [text](url)
  result = result.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  )
  // Auto-link emails
  result = result.replace(
    /([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/g,
    '<a href="mailto:$1">$1</a>'
  )
  return result
}

function parseTable(lines: string[], startIdx: number): { html: string; endIdx: number } {
  const headerLine = lines[startIdx].trim()
  const headerCells = headerLine.split('|').filter(c => c.trim()).map(c => c.trim())

  // Check if next line is separator (---|---|---)
  if (startIdx + 1 >= lines.length || !/^\|?[\s-:|]+\|?$/.test(lines[startIdx + 1].trim())) {
    return { html: '', endIdx: startIdx }
  }

  let html = '<div class="zk-table-wrap"><table class="zk-table"><thead><tr>'
  for (const cell of headerCells) {
    html += `<th>${renderInline(cell)}</th>`
  }
  html += '</tr></thead><tbody>'

  let i = startIdx + 2
  while (i < lines.length) {
    const line = lines[i].trim()
    if (!line || !line.includes('|')) break
    const cells = line.split('|').filter(c => c.trim()).map(c => c.trim())
    html += '<tr>'
    for (const cell of cells) {
      html += `<td>${renderInline(cell)}</td>`
    }
    html += '</tr>'
    i++
  }

  html += '</tbody></table></div>'
  return { html, endIdx: i - 1 }
}

export function markdownToHtml(text: string): string {
  const lines = text.split('\n')
  const parts: string[] = []
  let i = 0
  let inList: 'ol' | 'ul' | null = null

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    // Empty line — only close list if next content isn't a continuation
    if (!trimmed) {
      if (inList) {
        // Peek ahead: does the next non-empty line continue the list?
        let peek = i + 1
        while (peek < lines.length && !lines[peek].trim()) peek++
        const nextLine = peek < lines.length ? lines[peek].trim() : ''
        const nextIsOl = /^\d+\.\s+/.test(nextLine)
        const nextIsUl = /^[-*]\s+/.test(nextLine)
        const continues = (inList === 'ol' && nextIsOl) || (inList === 'ul' && nextIsUl)
        if (!continues) {
          parts.push(inList === 'ol' ? '</ol>' : '</ul>')
          inList = null
        }
      }
      i++
      continue
    }

    // Table detection: line with | separators followed by a --- separator line
    if (trimmed.includes('|') && i + 1 < lines.length && /^\|?[\s-:|]+\|?$/.test(lines[i + 1].trim())) {
      if (inList) {
        parts.push(inList === 'ol' ? '</ol>' : '</ul>')
        inList = null
      }
      const table = parseTable(lines, i)
      if (table.html) {
        parts.push(table.html)
        i = table.endIdx + 1
        continue
      }
    }

    // Ordered list: "1. ", "2. ", etc.
    const olMatch = trimmed.match(/^(\d+)\.\s+(.+)/)
    if (olMatch) {
      if (inList !== 'ol') {
        if (inList) parts.push('</ul>')
        parts.push('<ol class="zk-list">')
        inList = 'ol'
      }
      parts.push(`<li>${renderInline(olMatch[2])}</li>`)
      i++
      continue
    }

    // Unordered list: "- " or "* "
    const ulMatch = trimmed.match(/^[-*]\s+(.+)/)
    if (ulMatch) {
      if (inList !== 'ul') {
        if (inList) parts.push('</ol>')
        parts.push('<ul class="zk-list">')
        inList = 'ul'
      }
      parts.push(`<li>${renderInline(ulMatch[1])}</li>`)
      i++
      continue
    }

    // Not a list item — close any open list
    if (inList) {
      parts.push(inList === 'ol' ? '</ol>' : '</ul>')
      inList = null
    }

    // Headings: ### h3, ## h2 (skip h1, too big for chat)
    if (trimmed.startsWith('### ')) {
      parts.push(`<h4 class="zk-heading">${renderInline(trimmed.slice(4))}</h4>`)
      i++
      continue
    }
    if (trimmed.startsWith('## ')) {
      parts.push(`<h3 class="zk-heading">${renderInline(trimmed.slice(3))}</h3>`)
      i++
      continue
    }

    // Regular paragraph
    parts.push(`<p>${renderInline(trimmed)}</p>`)
    i++
  }

  // Close any trailing list
  if (inList) {
    parts.push(inList === 'ol' ? '</ol>' : '</ul>')
  }

  return parts.join('')
}

interface MarkdownContentProps {
  content: string
}

export function MarkdownContent({ content }: MarkdownContentProps) {
  const html = markdownToHtml(content)
  return <div className="zk-md" dangerouslySetInnerHTML={{ __html: html }} />
}
