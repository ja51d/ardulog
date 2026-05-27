<script setup>
import { ref, computed } from 'vue'
import { parseDataFlash } from './parser/dataflash.js'
import { detectFrameKind } from './analyzers/frameKind.js'
import { saveRecent } from './utils/logCache.js'
import DropZone from './components/DropZone.vue'
import MetricsStrip from './components/MetricsStrip.vue'
import NavRail from './components/NavRail.vue'
import LogSummary from './components/LogSummary.vue'
import Review from './components/Review.vue'
import Params from './components/Params.vue'
import MapView from './components/MapView.vue'
import Plot from './components/Plot.vue'
import Motors from './components/Motors.vue'
import PidTuning from './components/PidTuning.vue'
import Info from './components/Info.vue'
import Cockpit from './components/Cockpit.vue'
import Fft from './components/Fft.vue'
import View3D from './components/View3D.vue'
import TerrainView from './components/TerrainView.vue'
import Battery from './components/Battery.vue'
import Assistant from './components/Assistant.vue'
import FlightReport from './components/FlightReport.vue'

const parsed = ref(null)
const error = ref(null)
const progress = ref(null)
const activeTab = ref('summary')
const navOpen = ref(false)

function setTab(t) {
  activeTab.value = t
  navOpen.value = false
}

async function loadFile(file, opts = {}) {
  error.value = null
  progress.value = { bytesRead: 0, total: file.size, lastType: '…' }
  try {
    const buf = opts.buffer || await file.arrayBuffer()
    const result = await parseDataFlash(buf, p => { progress.value = p })
    parsed.value = result
    progress.value = null
    if (!opts.fromCache) saveRecent(file, buf).catch(() => {})
  } catch (e) {
    console.error(e)
    error.value = e.message || String(e)
    progress.value = null
  }
}

const frame = computed(() => parsed.value ? detectFrameKind(parsed.value).toUpperCase() : '—')
</script>

<template>
  <div class="app">
    <header class="header">
      <button class="hamburger" :class="{ open: navOpen }" @click="navOpen = !navOpen" aria-label="Toggle menu">
        <span></span><span></span><span></span>
      </button>
      <img src="/favicon.svg" alt="ardulog" class="logo-img" />
      <div class="title-block">
        <div class="title">ARDULOG</div>
        <div class="sub">UAV LOG ANALYZER</div>
      </div>
      <div class="status">
        <span class="status-dot" :class="{ live: parsed }"></span>
        <span class="status-text">{{ parsed ? 'LIVE' : 'STANDBY' }}</span>
      </div>
      <div class="grow"></div>
      <div class="header-summary" v-if="parsed">
        {{ parsed.count.toLocaleString() }} msgs · {{ parsed.duration.toFixed(1) }}s
      </div>
      <div class="header-summary" v-else-if="progress">
        Parsing… {{ progress.lastType }} ({{ Math.round(progress.bytesRead/progress.total*100) }}%)
      </div>
      <div class="header-summary" v-else>no log loaded</div>
      <div class="credit">
        <div class="credit-line">BY JAVID</div>
        <a class="credit-link" href="https://github.com/ja51d" target="_blank" rel="noopener" title="@ja51d on GitHub">
          <svg viewBox="0 0 16 16" width="11" height="11" aria-hidden="true">
            <path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/>
          </svg>
          <span>@ja51d</span>
        </a>
      </div>
    </header>

    <MetricsStrip :parsed="parsed" :frame="frame" v-if="parsed" />

    <div class="body">
      <div class="nav-backdrop" :class="{ show: navOpen }" @click="navOpen = false"></div>
      <NavRail :active="activeTab" :enabled="!!parsed" :open="navOpen" @update:active="setTab" />
      <main class="content">
        <DropZone v-if="!parsed && !progress" @file="(f, o) => loadFile(f, o)" />
        <div v-else-if="progress" class="loading">
          <div class="loading-title">PARSING LOG…</div>
          <div class="loading-bar">
            <div class="loading-fill" :style="{width: (progress.bytesRead/progress.total*100)+'%'}"></div>
          </div>
          <div class="loading-meta">
            {{ (progress.bytesRead/1024/1024).toFixed(1) }} / {{ (progress.total/1024/1024).toFixed(1) }} MB
            · last type: <b>{{ progress.lastType }}</b>
          </div>
        </div>
        <LogSummary v-else-if="activeTab === 'summary'" :parsed="parsed" :frame="frame" />
        <Review    v-else-if="activeTab === 'review'"  :parsed="parsed" />
        <Params    v-else-if="activeTab === 'params'"  :parsed="parsed" />
        <MapView   v-else-if="activeTab === 'map'"     :parsed="parsed" />
        <TerrainView v-else-if="activeTab === 'terrain'" :parsed="parsed" />
        <Plot      v-else-if="activeTab === 'plot'"    :parsed="parsed" />
        <Motors    v-else-if="activeTab === 'motors'"  :parsed="parsed" />
        <PidTuning v-else-if="activeTab === 'pid'"     :parsed="parsed" />
        <Info      v-else-if="activeTab === 'info'"    :parsed="parsed" />
        <Cockpit   v-else-if="activeTab === 'cockpit'" :parsed="parsed" />
        <Battery   v-else-if="activeTab === 'battery'" :parsed="parsed" />
        <Assistant v-else-if="activeTab === 'ai'"      :parsed="parsed" />
        <FlightReport v-else-if="activeTab === 'report'" :parsed="parsed" />
        <Fft       v-else-if="activeTab === 'fft'"     :parsed="parsed" />
        <View3D    v-else-if="activeTab === '3d'"      :parsed="parsed" />
        <div v-else class="placeholder">
          <div class="placeholder-title">{{ activeTab.toUpperCase() }}</div>
          <div class="placeholder-sub">Coming soon.</div>
        </div>
        <div v-if="error" class="error">PARSE ERROR · {{ error }}</div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.app { display: flex; flex-direction: column; height: 100%; width: 100%; }

.header {
  display: flex; align-items: center; gap: 16px;
  padding: 12px 24px; height: 68px;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(14px) saturate(140%);
  -webkit-backdrop-filter: blur(14px) saturate(140%);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  position: relative;
  z-index: 5;
}
.header::after {
  content: ''; position: absolute; left: 0; right: 0; bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(61,169,252,0.45), transparent);
  pointer-events: none;
}
.logo-img {
  width: 38px; height: 38px; display: block;
  filter: drop-shadow(0 0 6px rgba(61,169,252,0.35));
  transition: filter 200ms var(--ease-out);
}
.logo-img:hover { filter: drop-shadow(0 0 12px rgba(61,169,252,0.7)); }
.title-block .title {
  color: var(--text);
  font-size: 16px; font-weight: 700; letter-spacing: 2.5px;
  background: linear-gradient(180deg, #ffffff 0%, #c7d1de 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.title-block .sub {
  color: var(--text-mute);
  font-size: 9px; letter-spacing: 2.2px; margin-top: 3px; font-weight: 600;
}
.status {
  display: inline-flex; align-items: center; gap: 7px;
  margin-left: 8px; padding: 4px 10px 4px 9px;
  border-radius: 999px;
  background: var(--surface-1);
  border: 1px solid var(--border);
}
.status-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--text-mute);
}
.status-dot.live {
  background: var(--success);
  box-shadow: 0 0 8px var(--success);
  animation: pulse 1.8s var(--ease-out) infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 6px rgba(52,211,153,0.6); }
  50%      { box-shadow: 0 0 14px rgba(52,211,153,0.9); }
}
.status-text {
  color: var(--text-dim);
  font-size: 9px; letter-spacing: 2.2px; font-weight: 700;
}
.grow { flex: 1; }
.header-summary {
  padding: 7px 14px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 11px; color: var(--text-2);
  min-width: 0;
}
.credit {
  display: flex; flex-direction: column; align-items: flex-end;
  gap: 2px; padding: 0 8px;
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: 1.5px; color: var(--text-dim);
}
.credit-link {
  display: inline-flex; align-items: center; gap: 4px;
  color: var(--text-dim); text-decoration: none;
  letter-spacing: 0.5px; font-size: 10px;
  transition: color 120ms;
}
.credit-link:hover { color: var(--accent); }
.credit-link svg { display: block; }

.body {
  flex: 1; display: flex; min-height: 0; position: relative;
}
.content {
  flex: 1; padding: 20px 24px; overflow: auto;
  background: transparent; position: relative;
}

.loading { max-width: 480px; margin: 60px auto; text-align: center; }
.loading-title {
  font-size: 11px; letter-spacing: 4px; color: var(--text-dim);
  margin-bottom: 14px; font-weight: 700;
}
.loading-bar {
  background: var(--bg-2); border: 1px solid var(--border);
  height: 6px; overflow: hidden;
}
.loading-fill {
  height: 100%; background: var(--accent);
  transition: width 80ms linear;
}
.loading-meta {
  margin-top: 14px; font-family: var(--font-mono);
  font-size: 11px; color: var(--text-dim);
}

.placeholder {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  height: 100%; color: var(--text-dim); text-align: center;
}
.placeholder-title {
  font-size: 22px; letter-spacing: 6px; font-weight: 700; color: var(--accent);
}
.placeholder-sub {
  margin-top: 12px; max-width: 460px; font-size: 12px; line-height: 1.5;
}

.error {
  margin-top: 18px; padding: 10px 14px;
  background: var(--bg-2); border: 1px solid var(--danger); border-left: 3px solid var(--danger);
  color: var(--danger); font-family: var(--font-mono); font-size: 12px;
}

/* Hamburger + drawer */
.hamburger {
  display: none;
  width: 36px; height: 36px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0;
  flex-direction: column; justify-content: center; align-items: center;
  gap: 4px; flex-shrink: 0; cursor: pointer;
  transition: background 160ms;
}
.hamburger:hover { background: var(--surface-2); }
.hamburger span {
  display: block; width: 16px; height: 2px;
  background: var(--text-2); border-radius: 1px;
  transition: transform 220ms var(--ease-out), opacity 160ms;
}
.hamburger.open span:nth-child(1) { transform: translateY(6px) rotate(45deg); }
.hamburger.open span:nth-child(2) { opacity: 0; }
.hamburger.open span:nth-child(3) { transform: translateY(-6px) rotate(-45deg); }

.nav-backdrop {
  display: none;
  position: absolute; inset: 0;
  background: rgba(8, 12, 20, 0.6);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  opacity: 0; pointer-events: none;
  transition: opacity 200ms var(--ease-out);
  z-index: 9;
}
.nav-backdrop.show { opacity: 1; pointer-events: auto; }

@media (max-width: 768px) {
  .header { height: 60px; padding: 8px 14px; gap: 10px; }
  .hamburger { display: inline-flex; }
  .logo-img { width: 32px; height: 32px; }
  .title-block .title { font-size: 13px; letter-spacing: 1.5px; }
  .title-block .sub { display: none; }
  .status { padding: 3px 8px; }
  .status-text { font-size: 8px; letter-spacing: 1.5px; }
  .header-summary { display: none; }
  .credit { display: none; }
  .nav-backdrop { display: block; }
  .content { padding: 14px; }
}
@media (max-width: 420px) {
  .header { gap: 8px; padding: 8px 10px; }
  .title-block .title { font-size: 12px; }
  .status { display: none; }
}
</style>
