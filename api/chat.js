// Vercel serverless function that proxies user messages to Google's
// free Gemini 1.5 Flash API. Keeps the API key on the server so it's
// never exposed in the browser.
//
// Env var required (set in Vercel dashboard → project → settings → env):
//   GEMINI_API_KEY  — free key from https://aistudio.google.com/apikey

// Per-IP rate limiter — a simple sliding window kept in module scope.
// Vercel cold-starts wipe this, and multiple serverless instances each
// keep their own map, so the *real* per-IP limit is "soft" — still
// enough to stop a single abuser from draining the daily Gemini quota.
const HITS_PER_WINDOW = 10
const WINDOW_MS = 60 * 60 * 1000      // 1 hour
const ipHits = new Map()              // ip → number[] (timestamps)

function rateLimit(ip) {
  const now = Date.now()
  const cutoff = now - WINDOW_MS
  let arr = ipHits.get(ip) || []
  arr = arr.filter(t => t > cutoff)
  if (arr.length >= HITS_PER_WINDOW) {
    const oldest = arr[0]
    const waitMs = WINDOW_MS - (now - oldest)
    return { allowed: false, retryAfterSec: Math.ceil(waitMs / 1000) }
  }
  arr.push(now)
  ipHits.set(ip, arr)
  // Best-effort GC: occasionally purge empty entries
  if (Math.random() < 0.02) {
    for (const [k, v] of ipHits) if (!v.length || v[v.length - 1] < cutoff) ipHits.delete(k)
  }
  return { allowed: true, remaining: HITS_PER_WINDOW - arr.length }
}

function clientIp(req) {
  return (
    (req.headers['x-forwarded-for'] || '').split(',')[0].trim() ||
    req.headers['x-real-ip'] ||
    req.socket?.remoteAddress ||
    'unknown'
  )
}

const SYSTEM_PROMPT = `You are ArduLog Copilot — an expert ArduPilot / drone flight log analyst.
You're answering questions about a parsed flight log. The user has just dropped a .bin / .tlog / .log
file into a browser-based viewer; the log was parsed locally and a condensed summary is included in
the user message under "LOG CONTEXT".

Style:
- Friendly, precise, pilot-y.
- Use units (m, m/s, A, V, °, Hz).
- Refer to specific numbers from the log when relevant.
- BE CONCISE. Aim for under ~250 words. Use short bullet lists (3-6 items max) only when
  enumerating distinct actions or parameters. NO long intros or restatements of the question.
- Skip "Here is..." / "Let's dive in..." preamble. Start with the substance.
- If the user asks about something the log doesn't capture, say so plainly.
- Never invent numbers that aren't in the context. If the user asks for something missing, suggest enabling
  the relevant logging or tell them which message type would have it.
- This is ArduPilot terminology specifically — RC inputs, modes, failsafes, EKF, GPS HDOP, PIDs, FFT, etc.`

export default async function handler(req, res) {
  // CORS — same-origin in production but keep it permissive for dev tools
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')
  if (req.method === 'OPTIONS') return res.status(204).end()

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'POST only' })
  }
  const key = process.env.GEMINI_API_KEY
  if (!key) {
    return res.status(503).json({
      error: 'Server misconfigured: GEMINI_API_KEY is not set. The site owner needs to add a free key from https://aistudio.google.com/apikey to Vercel env vars.',
      code: 'missing_key',
    })
  }

  // Rate-limit by client IP
  const ip = clientIp(req)
  const rl = rateLimit(ip)
  if (!rl.allowed) {
    const mins = Math.ceil(rl.retryAfterSec / 60)
    res.setHeader('Retry-After', String(rl.retryAfterSec))
    return res.status(429).json({
      error: `You've sent a lot of questions this hour. Please wait ~${mins} min and try again. (Shared free tier — keeps it sustainable.)`,
      code: 'rate_limit_ip',
      retryAfterSec: rl.retryAfterSec,
    })
  }

  let body
  try {
    body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body
  } catch {
    return res.status(400).json({ error: 'Invalid JSON' })
  }
  const { messages, logContext } = body || {}
  if (!Array.isArray(messages) || !messages.length) {
    return res.status(400).json({ error: 'messages[] required' })
  }

  // Convert chat history into Gemini's "contents" array. We attach the
  // log context to the *first* user message so the model has it from
  // turn one without re-sending it every call.
  const contents = []
  let firstUser = true
  for (const m of messages) {
    if (!m?.role || !m?.text) continue
    let text = m.text
    if (m.role === 'user' && firstUser && logContext) {
      text = `LOG CONTEXT:\n${logContext}\n\n---\nUser question: ${text}`
      firstUser = false
    }
    contents.push({
      role: m.role === 'assistant' ? 'model' : 'user',
      parts: [{ text }],
    })
  }

  // Model fallback chain — if the preferred model is overloaded (503),
  // automatically retry on a lighter / less popular model so users still
  // get an answer instead of "high demand, try later".
  const MODEL_CHAIN = ['gemini-2.5-flash', 'gemini-flash-latest', 'gemini-2.0-flash', 'gemini-2.5-flash-lite']
  const requestBody = JSON.stringify({
    contents,
    systemInstruction: { role: 'user', parts: [{ text: SYSTEM_PROMPT }] },
    generationConfig: { temperature: 0.4, topP: 0.9, maxOutputTokens: 2048 },
    safetySettings: [
      { category: 'HARM_CATEGORY_HARASSMENT',        threshold: 'BLOCK_ONLY_HIGH' },
      { category: 'HARM_CATEGORY_HATE_SPEECH',       threshold: 'BLOCK_ONLY_HIGH' },
      { category: 'HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold: 'BLOCK_ONLY_HIGH' },
      { category: 'HARM_CATEGORY_DANGEROUS_CONTENT', threshold: 'BLOCK_ONLY_HIGH' },
    ],
  })

  let upstream = null, lastErrTxt = '', lastStatus = 0
  for (const model of MODEL_CHAIN) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`
    try {
      upstream = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: requestBody,
      })
    } catch (e) {
      return res.status(502).json({ error: 'Upstream fetch failed: ' + (e?.message || e) })
    }
    if (upstream.ok) break
    // Retry only on transient: 503 (overloaded), 502/504 (gateway).
    // Anything else (401/403/429/etc) is permanent or quota-related.
    if (upstream.status !== 503 && upstream.status !== 502 && upstream.status !== 504) break
    lastErrTxt = await upstream.text().catch(() => '')
    lastStatus = upstream.status
  }

  if (!upstream.ok) {
    const txt = (await upstream.text().catch(() => '')) || lastErrTxt
    // Distinguish the friendly "we ran out of free quota today" case
    // from other upstream errors. Gemini returns 429 on per-day caps.
    if (upstream.status === 503 || lastStatus === 503) {
      return res.status(503).json({
        error: 'All Gemini models are overloaded right now. Please try again in a minute or two — usually a short blip.',
        code: 'overloaded',
      })
    }
    if (upstream.status === 429) {
      // Try to figure out *which* quota was hit so we give an honest message
      // (per-minute / per-day / unknown).
      let scope = 'unknown'
      try {
        const parsed = JSON.parse(txt)
        const violations = parsed?.error?.details?.flatMap?.(d => d?.violations || []) || []
        const quotaId = violations.map(v => v.quotaId || '').join(' ')
        if (/PerMinute/i.test(quotaId)) scope = 'minute'
        else if (/PerDay/i.test(quotaId)) scope = 'day'
      } catch (_) {}

      let msg
      if (scope === 'minute') {
        msg = 'Hit Gemini\'s per-minute free-tier limit (10 req/min across all visitors). Please wait ~60 seconds and try again.'
      } else if (scope === 'day') {
        msg = 'The shared daily AI quota has run out. It resets at midnight UTC. Sorry — try again tomorrow.'
      } else {
        msg = 'Gemini rate limit hit (shared free tier). Wait ~1 minute and try again — usually clears quickly.'
      }
      return res.status(429).json({ error: msg, code: 'rate_limit_upstream', scope })
    }
    if (upstream.status === 403 || /api.key/i.test(txt)) {
      return res.status(503).json({
        error: 'The site\'s Gemini key is invalid or expired. The site owner needs to refresh it in Vercel.',
        code: 'bad_key',
      })
    }
    return res.status(upstream.status).json({
      error: `Gemini API ${upstream.status}: ${txt.slice(0, 220)}`,
      code: 'upstream_error',
    })
  }

  const data = await upstream.json().catch(() => null)
  const candidate = data?.candidates?.[0]
  let reply = candidate?.content?.parts?.[0]?.text || ''
  const finishReason = candidate?.finishReason || ''

  // Gemini 2.5 Flash spends "thinking" tokens before output. If the model
  // hits MAX_TOKENS during thinking, content.parts can be empty. Re-issue
  // with a shorter, no-thinking config so we get *something* back.
  if (!reply && (finishReason === 'MAX_TOKENS' || !candidate?.content?.parts)) {
    const retryBody = JSON.parse(requestBody)
    retryBody.generationConfig = {
      temperature: 0.4, topP: 0.9, maxOutputTokens: 1200,
      thinkingConfig: { thinkingBudget: 0 },
    }
    const url2 = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${key}`
    try {
      const r2 = await fetch(url2, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(retryBody),
      })
      if (r2.ok) {
        const d2 = await r2.json().catch(() => null)
        reply = d2?.candidates?.[0]?.content?.parts?.[0]?.text || reply
      }
    } catch (_) {}
  }
  if (!reply) {
    return res.status(502).json({
      error: `Gemini returned an empty response (finishReason: ${finishReason || 'unknown'}). Try rephrasing your question or asking for a shorter answer.`,
      code: 'empty_reply',
    })
  }
  // Append a soft warning if the model cut off
  if (finishReason === 'MAX_TOKENS') reply += '\n\n*(Response was truncated — ask "continue" for the rest.)*'
  return res.status(200).json({ reply, finishReason })
}
