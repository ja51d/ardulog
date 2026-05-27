<script setup>
import { ref, onMounted } from 'vue'
import { listRecent, loadRecent, deleteRecent, formatRelativeTime } from '../utils/logCache.js'

const emit = defineEmits(['file'])
const hover = ref(false)
const input = ref(null)
const recents = ref([])
const loadingDemo = ref(false)

async function refresh() { recents.value = await listRecent() }
onMounted(refresh)

function onDrop(e) {
  hover.value = false
  const f = e.dataTransfer.files?.[0]
  if (f) emit('file', f)
}
function onPick(e) {
  const f = e.target.files?.[0]
  if (f) emit('file', f)
}
async function pickRecent(rec) {
  const full = await loadRecent(rec.id)
  if (!full?.buffer) return
  const fakeFile = { name: full.name, size: full.size, lastModified: full.lastModified }
  emit('file', fakeFile, { buffer: full.buffer, fromCache: true })
}
async function removeRecent(rec, e) {
  e.stopPropagation()
  await deleteRecent(rec.id)
  refresh()
}
async function loadDemo() {
  if (loadingDemo.value) return
  loadingDemo.value = true
  try {
    const res = await fetch('/demo-flight.bin', { cache: 'force-cache' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const buf = await res.arrayBuffer()
    const fakeFile = { name: 'demo-flight.bin', size: buf.byteLength, lastModified: Date.now() }
    emit('file', fakeFile, { buffer: buf, fromCache: true })
  } catch (e) {
    alert('Couldn\'t load demo flight: ' + (e?.message || e))
  } finally {
    loadingDemo.value = false
  }
}
function fmtSize(b) {
  if (b > 1024 * 1024) return (b / 1024 / 1024).toFixed(1) + ' MB'
  if (b > 1024)        return (b / 1024).toFixed(0) + ' KB'
  return b + ' B'
}
</script>

<template>
  <div class="landing">
    <div class="hero">
      <div class="hero-badge">
        <span class="dot"></span>
        ARDUPILOT TELEMETRY · LOCAL PARSE
      </div>
      <h1 class="hero-title">
        Drop a flight log.<br/>
        <span class="accent">See everything.</span>
      </h1>
      <p class="hero-sub">
        A browser-based diagnostic suite for ArduPilot telemetry — maps, plots,
        FFT, motor balance, PID tuning, 3D playback. Nothing leaves your machine.
      </p>
    </div>

    <div
      class="dropzone"
      :class="{ hover }"
      @dragover.prevent="hover = true"
      @dragleave.prevent="hover = false"
      @drop.prevent="onDrop"
      @click="input.click()"
    >
      <div class="drop-glow"></div>
      <div class="drop-icon">
        <svg viewBox="0 0 48 48" width="44" height="44" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M24 6 v24"/>
          <path d="M14 20 l10 10 l10 -10"/>
          <path d="M6 38 h36"/>
        </svg>
      </div>
      <div class="drop-title">DROP FLIGHT LOG HERE</div>
      <div class="drop-sub">or click to browse</div>
      <div class="drop-types">
        <span class="chip">.BIN</span>
        <span class="chip">.TLOG</span>
        <span class="chip">.LOG</span>
      </div>
      <input ref="input" type="file" accept=".bin,.tlog,.log" style="display:none" @change="onPick" />
    </div>

    <div class="demo-bar">
      <button class="demo-btn" :disabled="loadingDemo" @click.stop="loadDemo">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="5 3 19 12 5 21 5 3"/>
        </svg>
        {{ loadingDemo ? 'LOADING DEMO…' : 'TRY A SAMPLE FLIGHT' }}
      </button>
      <span class="demo-hint">478s · ArduPlane · 515k messages · no upload</span>
    </div>

    <div class="recents" v-if="recents.length">
      <div class="recents-head">
        <span class="kicker">RECENT LOGS</span>
        <span class="hint-dim">stored locally · never uploaded</span>
      </div>
      <div class="recents-list">
        <button v-for="r in recents" :key="r.id" class="recent" @click="pickRecent(r)">
          <div class="r-icon">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2 H6 a2 2 0 0 0 -2 2 v16 a2 2 0 0 0 2 2 h12 a2 2 0 0 0 2 -2 V8 z"/>
              <path d="M14 2 v6 h6"/>
            </svg>
          </div>
          <div class="r-meta">
            <div class="r-name">{{ r.name }}</div>
            <div class="r-sub">{{ fmtSize(r.size) }} · {{ formatRelativeTime(r.savedAt) }}</div>
          </div>
          <button class="r-x" @click.stop="removeRecent(r, $event)" title="Remove">×</button>
        </button>
      </div>
    </div>

    <div class="features">
      <div class="feature">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <rect x="4" y="10" width="16" height="11" rx="2"/>
            <path d="M8 10 V7 a4 4 0 0 1 8 0 v3"/>
          </svg>
        </div>
        <div class="feature-title">100% LOCAL</div>
        <div class="feature-text">Parsing runs in your browser via WebAssembly. The log never touches a server.</div>
      </div>
      <div class="feature">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M13 2 L4 14 h7 l-1 8 L20 10 h-7 z"/>
          </svg>
        </div>
        <div class="feature-title">FAST PARSE</div>
        <div class="feature-text">Streams half-million message logs in seconds with live progress feedback.</div>
      </div>
      <div class="feature">
        <div class="feature-icon">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 17 l6 -6 l4 4 l8 -8"/>
            <path d="M14 7 h7 v7"/>
          </svg>
        </div>
        <div class="feature-title">DEEP DIAGNOSTICS</div>
        <div class="feature-text">FFT spectrum, motor balance, PID step response, 3D attitude playback.</div>
      </div>
    </div>

    <div class="footer-note">
      Open-source · <a href="https://github.com/ja51d/ardulog" target="_blank" rel="noopener">github.com/ja51d/ardulog</a>
    </div>
  </div>
</template>

<style scoped>
.landing {
  max-width: 880px;
  margin: 0 auto;
  padding: 36px 24px 60px;
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.hero { text-align: center; padding-top: 16px; }
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border: 1px solid var(--border);
  background: var(--accent-soft);
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--text-dim);
  margin-bottom: 22px;
}
.hero-badge .dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 8px var(--success);
}
.hero-title {
  font-size: 44px;
  font-weight: 700;
  line-height: 1.1;
  margin: 0;
  letter-spacing: -0.5px;
  color: var(--text);
}
.hero-title .accent {
  background: var(--grad-accent);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.hero-sub {
  margin: 18px auto 0;
  max-width: 580px;
  color: var(--text-dim);
  font-size: 14px;
  line-height: 1.6;
}

.dropzone {
  position: relative;
  border: 1.5px dashed var(--border);
  border-radius: 14px;
  background:
    radial-gradient(ellipse at 50% 0%, rgba(61,169,252,0.08), transparent 60%),
    var(--bg-1);
  padding: 52px 32px 40px;
  text-align: center;
  cursor: pointer;
  transition: border-color 120ms, transform 120ms, background 120ms;
  overflow: hidden;
}
.dropzone:hover,
.dropzone.hover {
  border-color: var(--accent);
  transform: translateY(-1px);
  background:
    radial-gradient(ellipse at 50% 0%, rgba(61,169,252,0.18), transparent 60%),
    var(--bg-1);
}
.drop-glow {
  position: absolute;
  top: -40%; left: 50%;
  width: 120%; height: 100%;
  transform: translateX(-50%);
  background: radial-gradient(ellipse at center, rgba(61,169,252,0.15), transparent 60%);
  pointer-events: none;
  opacity: 0;
  transition: opacity 150ms;
}
.dropzone.hover .drop-glow { opacity: 1; }
.drop-icon {
  color: var(--accent);
  display: inline-flex;
  padding: 14px;
  border-radius: 14px;
  background: var(--accent-soft);
  margin-bottom: 18px;
}
.drop-title { color: var(--text); font-size: 14px; font-weight: 700; letter-spacing: 3px; }
.drop-sub { color: var(--text-dim); font-size: 12px; margin-top: 6px; font-family: var(--font-mono); }
.drop-types { display: flex; justify-content: center; gap: 8px; margin-top: 22px; }
.chip {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.5px;
  background: var(--bg-2);
}

/* Demo */
.demo-bar { display: flex; align-items: center; justify-content: center; gap: 14px; flex-wrap: wrap; }
.demo-btn {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--grad-accent);
  color: #fff;
  border: none;
  border-radius: 999px;
  padding: 10px 20px;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.8px;
  cursor: pointer;
  box-shadow: 0 4px 18px rgba(61,169,252,0.30);
  transition: filter 160ms, box-shadow 160ms, transform 160ms;
}
.demo-btn:hover:not(:disabled) {
  filter: brightness(1.1);
  box-shadow: 0 6px 26px rgba(61,169,252,0.55);
  transform: translateY(-1px);
}
.demo-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.demo-hint { color: var(--text-mute); font-family: var(--font-mono); font-size: 10px; letter-spacing: 1.5px; }
@media (max-width: 520px) { .demo-hint { display: none; } }

/* Recents */
.recents { display: flex; flex-direction: column; gap: 10px; }
.recents-head { display: flex; align-items: baseline; gap: 12px; padding: 0 4px; }
.kicker { color: var(--text-mute); font-size: 10px; font-weight: 700; letter-spacing: 2.5px; }
.hint-dim { color: var(--text-mute); font-size: 10px; font-family: var(--font-mono); }
.recents-list { display: flex; flex-direction: column; gap: 6px; }
.recent {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms var(--ease-out), background 160ms var(--ease-out), transform 160ms var(--ease-out);
}
.recent:hover { border-color: var(--accent); background: var(--accent-soft); transform: translateY(-1px); }
.r-icon { color: var(--accent-2); }
.r-meta { flex: 1; min-width: 0; }
.r-name { color: var(--text); font-family: var(--font-mono); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.r-sub  { color: var(--text-mute); font-size: 10px; font-family: var(--font-mono); margin-top: 2px; }
.r-x {
  background: transparent;
  border: none;
  color: var(--text-mute);
  width: 24px; height: 24px;
  font-size: 18px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color 120ms, background 120ms;
}
.r-x:hover { color: var(--danger); background: rgba(248,113,113,0.10); }

/* Features */
.features { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.feature {
  padding: 22px 20px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  transition: border-color 120ms, transform 120ms;
}
.feature:hover { border-color: var(--accent); transform: translateY(-2px); }
.feature-icon { color: var(--accent); margin-bottom: 12px; }
.feature-title {
  font-size: 11px; letter-spacing: 2.5px;
  font-weight: 700; color: var(--text);
  margin-bottom: 6px;
}
.feature-text { color: var(--text-dim); font-size: 12px; line-height: 1.55; }

/* Footer */
.footer-note {
  text-align: center;
  font-family: var(--font-mono);
  font-size: 11px; color: var(--text-dim);
  margin-top: 8px;
}
.footer-note a { color: var(--accent); text-decoration: none; }
.footer-note a:hover { text-decoration: underline; }

@media (max-width: 700px) {
  .hero-title { font-size: 32px; }
  .features { grid-template-columns: 1fr; }
}
</style>
