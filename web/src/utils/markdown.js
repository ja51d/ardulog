// Tiny markdown → HTML renderer for chat bubbles. Handles the subset
// the AI actually uses: **bold**, *italic*, `code`, lists, headings,
// paragraphs, line breaks. NO arbitrary HTML pass-through — we escape
// every input first to prevent XSS, then re-insert known-good tags.

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function renderMarkdown(input) {
  if (!input) return ''
  // Escape FIRST, then re-introduce safe inline/block formatting.
  let s = escapeHtml(String(input))

  // ----- Block-level: split into paragraphs / lists / headings ------
  const lines = s.split(/\r?\n/)
  const out = []
  let listOpen = null     // 'ul' | 'ol' | null
  let paraBuf = []

  function flushPara() {
    if (paraBuf.length) {
      out.push('<p>' + paraBuf.join(' ') + '</p>')
      paraBuf = []
    }
  }
  function closeList() {
    if (listOpen) { out.push(`</${listOpen}>`); listOpen = null }
  }

  for (let raw of lines) {
    const line = raw.trim()
    if (!line) { flushPara(); closeList(); continue }

    // Headings: ###, ##, # — convert to h3..h5 for chat scale
    const heading = line.match(/^(#{1,6})\s+(.*)$/)
    if (heading) {
      flushPara(); closeList()
      const lvl = Math.min(6, Math.max(3, heading[1].length + 2))
      out.push(`<h${lvl}>${inline(heading[2])}</h${lvl}>`)
      continue
    }

    // Unordered list: -, *, • (followed by space)
    const ul = line.match(/^[-*•]\s+(.*)$/)
    if (ul) {
      flushPara()
      if (listOpen !== 'ul') { closeList(); out.push('<ul>'); listOpen = 'ul' }
      out.push(`<li>${inline(ul[1])}</li>`)
      continue
    }

    // Ordered list: 1. item
    const ol = line.match(/^(\d+)\.\s+(.*)$/)
    if (ol) {
      flushPara()
      if (listOpen !== 'ol') { closeList(); out.push('<ol>'); listOpen = 'ol' }
      out.push(`<li>${inline(ol[2])}</li>`)
      continue
    }

    // Regular paragraph line — accumulate
    closeList()
    paraBuf.push(inline(line))
  }
  flushPara(); closeList()

  return out.join('')
}

function inline(s) {
  // **bold**, __bold__
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  // *italic*, _italic_ — but only when not part of a bullet (we already handled bullets)
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  s = s.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>')
  // `code`
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
  // Bare URLs → links (cheap regex; good enough for chat)
  s = s.replace(/https?:\/\/[^\s<]+/g, m => `<a href="${m}" target="_blank" rel="noopener">${m}</a>`)
  return s
}
