<script setup>
import { ref, computed } from 'vue'
import { parseDataFlash } from './parser/dataflash.js'
import { detectFrameKind } from './analyzers/frameKind.js'
import DropZone from './components/DropZone.vue'
import MetricsStrip from './components/MetricsStrip.vue'
import NavRail from './components/NavRail.vue'
import LogSummary from './components/LogSummary.vue'

const parsed = ref(null)
const error = ref(null)
const progress = ref(null)
const activeTab = ref('summary')

async function loadFile(file) {
  error.value = null
  progress.value = { bytesRead: 0, total: file.size, lastType: '…' }
  try {
    const buf = await file.arrayBuffer()
    const result = await parseDataFlash(buf, p => { progress.value = p })
    parsed.value = result
    progress.value = null
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
    <!-- Header bar -->
    <header class="header">
      <div class="logo">[ <span class="dot"></span> ]</div>
      <div class="title-block">
        <div class="title">UAV LOG ANALYZER</div>
        <div class="sub">ARDUPILOT TELEMETRY DIAGNOSTIC TOOL · WEB</div>
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
      <div class="credit">BY JAVID</div>
    </header>

    <!-- Metrics strip -->
    <MetricsStrip :parsed="parsed" :frame="frame" v-if="parsed" />

    <!-- Body -->
    <div class="body">
      <NavRail v-model:active="activeTab" :enabled="!!parsed" />
      <main class="content">
        <DropZone v-if="!parsed && !progress" @file="loadFile" />
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
        <div v-else class="placeholder">
          <div class="placeholder-title">{{ activeTab.toUpperCase() }}</div>
          <div class="placeholder-sub">This view is part of phase 2. The desktop app has it today;
            the web port lands here in the next session.</div>
        </div>
        <div v-if="error" class="error">PARSE ERROR · {{ error }}</div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
}

.header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 22px;
  height: 64px;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.logo {
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 18px;
  letter-spacing: 2px;
}
.logo .dot {
  display: inline-block; width: 8px; height: 8px;
  background: var(--accent); vertical-align: middle;
  margin: 0 2px;
}
.title-block .title {
  color: var(--text);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 3px;
}
.title-block .sub {
  color: var(--text-dim);
  font-size: 10px;
  letter-spacing: 2px;
  margin-top: 2px;
}
.status {
  display: flex; align-items: center; gap: 6px; margin-left: 8px;
}
.status-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--text-dim);
}
.status-dot.live { background: var(--success); }
.status-text {
  color: var(--text-dim);
  font-size: 10px;
  letter-spacing: 2px;
  font-weight: 700;
}
.grow { flex: 1; }
.header-summary {
  padding: 6px 14px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
  min-width: 0;
}
.credit {
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.5px;
  padding: 0 8px;
}

.body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.content {
  flex: 1;
  padding: 18px 22px;
  overflow: auto;
  background: var(--bg-0);
}

.loading {
  max-width: 480px;
  margin: 60px auto;
  text-align: center;
}
.loading-title {
  font-size: 11px;
  letter-spacing: 4px;
  color: var(--text-dim);
  margin-bottom: 14px;
  font-weight: 700;
}
.loading-bar {
  background: var(--bg-2);
  border: 1px solid var(--border);
  height: 6px;
  overflow: hidden;
}
.loading-fill {
  height: 100%;
  background: var(--accent);
  transition: width 80ms linear;
}
.loading-meta {
  margin-top: 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-dim);
  text-align: center;
}
.placeholder-title {
  font-size: 22px;
  letter-spacing: 6px;
  font-weight: 700;
  color: var(--accent);
}
.placeholder-sub {
  margin-top: 12px;
  max-width: 460px;
  font-size: 12px;
  line-height: 1.5;
}

.error {
  margin-top: 18px;
  padding: 10px 14px;
  background: var(--bg-2);
  border: 1px solid var(--danger);
  border-left: 3px solid var(--danger);
  color: var(--danger);
  font-family: var(--font-mono);
  font-size: 12px;
}
</style>
