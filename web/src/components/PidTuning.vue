<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { analyzePidTracking } from '../analyzers/pidTracking.js'

const props = defineProps({ parsed: Object })

const SUCCESS = '#5dba7c', WARN = '#d9a14a', DANGER = '#d96666', DIM = '#7a8699'
const BADGE = { good: SUCCESS, loose: WARN, lagging: WARN, oscillating: DANGER, 'no-command': DIM }

const stats = computed(() => analyzePidTracking(props.parsed || {}))

const rollRef = ref(null), pitchRef = ref(null), yawRef = ref(null)
const plots = { roll: null, pitch: null, yaw: null }

function buildOne(axis, refEl) {
  if (!refEl) return
  if (plots[axis]) { plots[axis].destroy(); plots[axis] = null }
  const att = props.parsed?.data?.ATT
  const attT = props.parsed?.times?.ATT
  if (!att || !attT?.length) return
  const desiredKey = { roll: 'DesRoll', pitch: 'DesPitch', yaw: 'DesYaw' }[axis]
  const actualKey  = { roll: 'Roll',    pitch: 'Pitch',    yaw: 'Yaw'    }[axis]
  if (!att[actualKey]) return
  const t0 = props.parsed.t_start || 0
  const xs = attT.map(t => t - t0)
  const actual = att[actualKey].map(Number)
  const desired = att[desiredKey] ? att[desiredKey].map(Number) : null
  const series = [{}, { label: 'actual',   stroke: '#d9a14a', width: 1.4, points: { show: false } }]
  const data = [xs, actual]
  if (desired) {
    series.push({ label: 'command', stroke: '#4a90e2', width: 1.4, points: { show: false }, dash: [5, 4] })
    data.push(desired)
  }
  const rect = refEl.getBoundingClientRect()
  plots[axis] = new uPlot({
    width: Math.max(400, rect.width),
    height: Math.max(140, rect.height),
    series,
    axes: [
      { stroke: DIM, grid: { stroke: '#323a47', width: 1 }, ticks: { stroke: '#323a47' },
        values: (u, s) => s.map(v => v.toFixed(1) + 's') },
      { stroke: DIM, grid: { stroke: '#323a47', width: 1 }, ticks: { stroke: '#323a47' }, label: 'deg' },
    ],
    legend: { show: true },
    cursor: { drag: { x: true, y: false } },
  }, data, refEl)
}

function buildAll() {
  buildOne('roll',  rollRef.value)
  buildOne('pitch', pitchRef.value)
  buildOne('yaw',   yawRef.value)
}
function handleResize() {
  for (const axis of ['roll', 'pitch', 'yaw']) {
    const el = { roll: rollRef.value, pitch: pitchRef.value, yaw: yawRef.value }[axis]
    if (plots[axis] && el) {
      const r = el.getBoundingClientRect()
      plots[axis].setSize({ width: Math.max(400, r.width), height: Math.max(140, r.height) })
    }
  }
}
let ro = null
function setupRO() {
  if (typeof ResizeObserver === 'undefined') return
  ro = new ResizeObserver(() => {
    handleResize()
    if (!plots.roll && !plots.pitch && !plots.yaw) buildAll()
  })
  for (const el of [rollRef.value, pitchRef.value, yawRef.value]) if (el) ro.observe(el)
}
onMounted(() => {
  nextTick(() => { buildAll(); setupRO() })
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (ro) { ro.disconnect(); ro = null }
  for (const k of Object.keys(plots)) if (plots[k]) plots[k].destroy()
})
watch(() => props.parsed, () => nextTick(buildAll))
</script>

<template>
  <div class="pid">
    <div class="title">PID TUNING · DESIRED VS ACTUAL ATTITUDE</div>

    <!-- Per-axis stats banner -->
    <div class="stats-card">
      <div class="hint">Cyan dashed = command  ·  Amber solid = vehicle response  ·  Big gap = loose tuning, ringing = P too high</div>
      <div class="stat-line" v-for="axis in ['roll','pitch','yaw']" :key="axis">
        <template v-if="stats[axis]">
          <span class="axis" :style="{ color: BADGE[stats[axis].verdict] }">{{ axis.toUpperCase() }}</span>
          <template v-if="stats[axis].verdict === 'no-command'">
            <span class="dim">·  {{ stats[axis].hint }}</span>
          </template>
          <template v-else>
            <span>·  RMS {{ stats[axis].rms_err.toFixed(1) }}°  ·  peak {{ stats[axis].peak_err.toFixed(0) }}°  ·  osc {{ stats[axis].osc_hz.toFixed(1) }} Hz  ·  lag {{ stats[axis].lag_ms.toFixed(0) }} ms</span>
            <span class="dim">·  {{ stats[axis].hint }}</span>
          </template>
        </template>
        <template v-else><span class="axis dim">{{ axis.toUpperCase() }}</span><span class="dim">·  no data</span></template>
      </div>
    </div>

    <!-- Three plots stacked -->
    <div class="panes">
      <div class="pane"><div class="pane-label">ROLL</div><div ref="rollRef" class="pane-canvas"></div></div>
      <div class="pane"><div class="pane-label">PITCH</div><div ref="pitchRef" class="pane-canvas"></div></div>
      <div class="pane"><div class="pane-label">YAW</div><div ref="yawRef" class="pane-canvas"></div></div>
    </div>
  </div>
</template>

<style scoped>
.pid { display: flex; flex-direction: column; gap: 10px; height: 100%; min-height: 0; }
.title {
  color: var(--text-dim);
  font-size: 11px; font-weight: 700; letter-spacing: 2px; padding: 0 2px 4px;
}
.stats-card {
  background: var(--bg-1);
  border: 1px solid var(--border);
  padding: 10px 14px;
  font-family: var(--font-mono);
  font-size: 11px;
}
.hint { color: var(--text-dim); margin-bottom: 6px; font-family: var(--font-ui); font-size: 11px; }
.stat-line { color: var(--text); display: flex; gap: 8px; flex-wrap: wrap; padding: 2px 0; }
.axis { font-weight: 700; min-width: 56px; }
.dim { color: var(--text-dim); }
.panes {
  flex: 1; display: flex; flex-direction: column; gap: 8px; min-height: 0;
}
.pane { flex: 1; min-height: 180px; display: flex; flex-direction: column; }
.pane-label {
  color: var(--text-dim);
  font-size: 9px; letter-spacing: 2px; font-weight: 700;
  padding: 0 4px 2px;
}
.pane-canvas { flex: 1; min-height: 150px; border: 1px solid var(--border); background: var(--bg-1); }
</style>
