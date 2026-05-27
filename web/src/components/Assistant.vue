<script setup>
// AI flight copilot — chat panel that sends the user's question + a
// condensed log summary to a free Gemini Flash backend (Vercel function
// at /api/chat). Replies are short, pilot-y, and grounded in the log.
import { ref, computed, nextTick } from 'vue'
import { buildLogSummaryForAI } from '../analyzers/logSummary.js'
import { renderMarkdown } from '../utils/markdown.js'

const props = defineProps({ parsed: Object })

const messages = ref([])     // { id, role, text, kind? }
const input = ref('')
const sending = ref(false)
const errorMsg = ref('')
const listRef = ref(null)
let nextId = 1
function newId() { return `m-${nextId++}` }

const logContext = computed(() => props.parsed ? buildLogSummaryForAI(props.parsed) : '(no log loaded)')
const hasLog = computed(() => !!props.parsed)

const SUGGESTIONS = [
  'Summarize this flight in 3 bullets',
  'Were there any failsafes or warnings?',
  'How was the battery health?',
  'Was the landing smooth?',
  'Any vibration / oscillation issues?',
  'What modes did I fly in?',
]

async function send(text) {
  const msg = (text ?? input.value).trim()
  if (!msg || sending.value) return
  errorMsg.value = ''
  messages.value.push({ id: newId(), role: 'user', text: msg })
  input.value = ''
  sending.value = true
  await nextTick(scrollToBottom)
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: messages.value,
        logContext: logContext.value,
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      errorMsg.value = data?.error || `HTTP ${res.status}`
      // Differentiate "rate-limited" from other errors so the bubble can
      // show a friendlier styled card.
      const isRate = data?.code === 'rate_limit_ip' || data?.code === 'rate_limit_upstream' || res.status === 429
      messages.value.push({
        id: newId(),
        role: 'assistant',
        text: errorMsg.value,
        kind: isRate ? 'rate-limit' : 'error',
      })
    } else {
      messages.value.push({ id: newId(), role: 'assistant', text: data.reply })
    }
  } catch (e) {
    errorMsg.value = String(e?.message || e)
    messages.value.push({ id: newId(), role: 'assistant', text: '⚠️ Network error: ' + errorMsg.value, kind: 'error' })
  } finally {
    sending.value = false
    await nextTick(scrollToBottom)
  }
}

function scrollToBottom() {
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}
function reset() {
  messages.value = []
  errorMsg.value = ''
}
function onEnter(e) {
  if (e.shiftKey) return
  e.preventDefault()
  send()
}
</script>

<template>
  <div class="assistant">
    <div class="head">
      <div class="head-left">
        <div class="title">
          <span class="gem">✦</span>
          <span class="t">FLIGHT COPILOT</span>
          <span class="badge">GEMINI · LIVE</span>
        </div>
        <div class="sub">Ask anything about this flight — log stays local, only a summary is sent.</div>
      </div>
      <button v-if="messages.length" class="reset" @click="reset">RESET</button>
    </div>

    <div class="list" ref="listRef">
      <div v-if="!messages.length" class="empty">
        <div class="welcome">
          <div class="welcome-icon">✦</div>
          <div class="welcome-text">Try asking…</div>
          <div class="suggestions">
            <button v-for="s in SUGGESTIONS" :key="s"
                    class="suggest" :disabled="!hasLog || sending"
                    @click="send(s)">{{ s }}</button>
          </div>
          <div v-if="!hasLog" class="warn">Load a log first to get useful answers.</div>
        </div>
      </div>
      <template v-else>
        <div v-for="m in messages" :key="m.id" class="msg" :class="m.role">
          <div class="bubble" :class="m.kind">
            <span v-if="m.kind === 'rate-limit'" class="bubble-icon">⏳</span>
            <span v-else-if="m.kind === 'error'" class="bubble-icon">⚠️</span>
            <!-- User messages render plain text; assistant renders markdown.
                 renderMarkdown escapes all input first, then re-inserts a
                 small allow-list of formatting tags — safe to v-html. -->
            <span v-if="m.role === 'user'" class="bubble-text">{{ m.text }}</span>
            <span v-else class="bubble-text md" v-html="renderMarkdown(m.text)"></span>
          </div>
        </div>
        <div v-if="sending" class="msg assistant">
          <div class="bubble typing">
            <span></span><span></span><span></span>
          </div>
        </div>
      </template>
    </div>

    <div class="composer">
      <textarea
        v-model="input"
        :disabled="sending"
        @keydown.enter="onEnter"
        rows="2"
        placeholder="Ask about this flight… (Enter to send, Shift+Enter for newline)"
        class="composer-input"
      ></textarea>
      <button class="send" :disabled="!input.trim() || sending" @click="send()">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13"/>
          <polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
        SEND
      </button>
    </div>
  </div>
</template>

<style scoped>
.assistant {
  display: flex; flex-direction: column;
  height: 100%; min-height: 0; gap: 12px;
  max-width: 920px;       /* keep chat readable on wide screens */
  width: 100%;
  margin: 0 auto;
}
.head {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 14px;
  padding: 16px 18px;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  position: relative;
  overflow: hidden;
  flex-shrink: 0;
}
.head::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--grad-accent);
  box-shadow: 0 0 14px rgba(61,169,252,0.5);
}
.title { display: flex; align-items: center; gap: 10px; }
.gem { color: var(--accent-2); font-size: 18px; }
.t   { font-weight: 700; letter-spacing: 2.5px; font-size: 13px; color: var(--text); }
.badge {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 1.8px;
  color: var(--success);
  background: rgba(52,211,153,0.10);
  border: 1px solid rgba(52,211,153,0.35);
  border-radius: 999px;
  padding: 2px 8px;
}
.sub { color: var(--text-dim); font-size: 11px; font-family: var(--font-mono); margin-top: 6px; }
.reset {
  background: var(--surface-1);
  border: 1px solid var(--border);
  color: var(--text-dim);
  border-radius: 999px;
  padding: 6px 12px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.5px;
  cursor: pointer;
  transition: color 160ms, border-color 160ms;
}
.reset:hover { color: var(--danger); border-color: rgba(248,113,113,0.5); }

.list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.msg {
  display: flex;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}
.empty { padding: 22px 0; }
.welcome { text-align: center; max-width: 540px; margin: 0 auto; }
.welcome-icon { color: var(--accent-2); font-size: 28px; }
.welcome-text { color: var(--text-mute); font-family: var(--font-mono); font-size: 11px; letter-spacing: 2px; margin: 8px 0 14px; }
.suggestions {
  display: flex; flex-wrap: wrap; gap: 6px; justify-content: center;
}
.suggest {
  background: var(--surface-1);
  border: 1px solid var(--border);
  color: var(--text-2);
  border-radius: 999px;
  padding: 7px 14px;
  font-size: 11px;
  cursor: pointer;
  transition: color 160ms, border-color 160ms, background 160ms, transform 160ms;
}
.suggest:hover:not(:disabled) {
  color: var(--accent-2);
  border-color: var(--accent);
  background: var(--accent-soft);
  transform: translateY(-1px);
}
.suggest:disabled { opacity: 0.4; cursor: not-allowed; }
.warn { color: var(--warn); font-family: var(--font-mono); font-size: 11px; margin-top: 14px; }

.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }
.bubble {
  max-width: 80%;
  padding: 11px 15px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.55;
  word-wrap: break-word;
  overflow-wrap: anywhere;
}
.msg.user .bubble { white-space: pre-wrap; }   /* user messages preserve newlines */
.msg.user .bubble {
  background: var(--grad-accent);
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 14px rgba(61,169,252,0.30);
}
.msg.assistant .bubble {
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text);
  border-bottom-left-radius: 4px;
}
.msg.assistant .bubble.rate-limit {
  background: linear-gradient(180deg, rgba(240,183,93,0.10), rgba(240,183,93,0.04));
  border-color: rgba(240,183,93,0.35);
  color: var(--text-2);
}
.msg.assistant .bubble.error {
  background: linear-gradient(180deg, rgba(248,113,113,0.10), rgba(248,113,113,0.04));
  border-color: rgba(248,113,113,0.35);
  color: var(--text-2);
}
.bubble-icon { margin-right: 6px; }

/* ----- Rendered markdown inside assistant bubbles -----
 * Use :deep() because v-html content doesn't get the scoped attribute,
 * so plain scoped selectors won't match the rendered <p>, <ul>, etc.
 */
.bubble-text.md :deep(*:first-child) { margin-top: 0 !important; }
.bubble-text.md :deep(*:last-child)  { margin-bottom: 0 !important; }
.bubble-text.md :deep(p) {
  margin: 0 0 8px;
  line-height: 1.55;
}
.bubble-text.md :deep(strong) { color: var(--accent-3); font-weight: 700; }
.bubble-text.md :deep(em)     { color: var(--text); font-style: italic; }
.bubble-text.md :deep(code) {
  background: var(--surface-3);
  border: 1px solid var(--border);
  padding: 1px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 0.92em;
  color: var(--accent-2);
}
.bubble-text.md :deep(h3),
.bubble-text.md :deep(h4),
.bubble-text.md :deep(h5) {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--text);
}
.bubble-text.md :deep(ul),
.bubble-text.md :deep(ol) {
  margin: 4px 0 8px;
  padding-left: 22px;
}
.bubble-text.md :deep(li) {
  margin: 3px 0;
  line-height: 1.5;
}
.bubble-text.md :deep(ul li::marker) { color: var(--accent-2); }
.bubble-text.md :deep(ol li::marker) { color: var(--accent-2); font-weight: 700; }
.bubble-text.md :deep(a) {
  color: var(--accent-2);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.bubble-text.md :deep(a:hover) { color: var(--accent-3); }
.bubble.typing {
  display: inline-flex; gap: 4px; padding: 14px 16px;
}
.bubble.typing span {
  width: 6px; height: 6px;
  background: var(--text-mute);
  border-radius: 50%;
  animation: blink 1.2s infinite;
}
.bubble.typing span:nth-child(2) { animation-delay: 0.2s; }
.bubble.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 80%, 100% { opacity: 0.25; transform: translateY(0); }
  40%           { opacity: 1;    transform: translateY(-2px); }
}

.composer {
  display: flex; gap: 10px; align-items: flex-end;
  flex-shrink: 0;
  padding: 12px;
  background: linear-gradient(180deg, var(--panel-from), var(--panel-to));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.composer-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  resize: none;
  outline: none;
  padding: 6px 4px;
  line-height: 1.5;
}
.composer-input::placeholder { color: var(--text-mute); }
.send {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--grad-accent);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  padding: 8px 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(61,169,252,0.30);
  transition: filter 160ms, box-shadow 160ms;
}
.send:hover:not(:disabled) { filter: brightness(1.1); box-shadow: 0 4px 22px rgba(61,169,252,0.55); }
.send:disabled { opacity: 0.45; cursor: not-allowed; box-shadow: none; }
</style>
