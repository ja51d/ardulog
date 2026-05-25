<script setup>
// Frame-aware motor / servo analysis — mirrors _populate_motors() from app.py.
//   copter / heli  → per-motor PWM table, balance verdict, diagonal-pair check,
//                    desync event detector
//   plane / other  → per-channel table relabelled as SERVOS, no balance verdict
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { detectFrameKind } from '../analyzers/frameKind.js'
import { nanmax, nanmin, nanmean } from '../analyzers/helpers.js'

const props = defineProps({ parsed: Object })

const SUCCESS = '#5dba7c', WARN = '#d9a14a', DANGER = '#d96666', ACCENT = '#4a90e2', DIM = '#7a8699'
const PALETTE = ['#4a90e2', '#d9a14a', '#5dba7c', '#d96666', '#6aa9e8', '#f472b6', '#facc15', '#a78bfa']

const kind = computed(() => detectFrameKind(props.parsed || {}))

const channels = computed(() => {
  const rcou = props.parsed?.data?.RCOU
  if (!rcou) return []
  const keys = Object.keys(rcou).filter(k => /^C\d+$/.test(k))
    .sort((a, b) => parseInt(a.slice(1)) - parseInt(b.slice(1)))
    .slice(0, 8)
  const out = []
  for (const k of keys) {
    const arr = (rcou[k] || []).map(Number).filter(Number.isFinite)
    if (!arr.length) continue
    if (nanmax(arr) < 900) continue   // never armed
    out.push({ key: k, arr })
  }
  return out
})

const PLANE_ROLES = { C1: 'aileron', C2: 'elevator', C3: 'throttle', C4: 'rudder',
                      C5: 'aux', C6: 'aux', C7: 'aux', C8: 'aux' }

const analysis = computed(() => {
  const chs = channels.value
  if (!chs.length) return null
  // Plane / rover / sub / other — channel-by-channel only, no verdict
  if (['plane', 'rover', 'sub', 'other'].includes(kind.value)) {
    const rows = chs.map(({ key, arr }) => ({
      key,
      min: nanmin(arr),
      mean: nanmean(arr),
      max: nanmax(arr),
      range: nanmax(arr) - nanmin(arr),
      role: kind.value === 'plane' ? (PLANE_ROLES[key] || '—') : '—',
    }))
    return { mode: 'servos', kind: kind.value, rows }
  }
  // Copter / heli — armed-sample mask, per-motor stats, balance verdict
  const len = chs[0].arr.length
  const armed = new Array(len).fill(false)
  for (let i = 0; i < len; i++) {
    for (const c of chs) if (c.arr[i] > 1100) { armed[i] = true; break }
  }
  const armedCount = armed.filter(Boolean).length
  if (armedCount < 10) {
    return { mode: 'bench', kind: kind.value, hint: 'Motors never appear armed (no PWM > 1100 µs) — log may be from bench / unarmed.' }
  }
  const rows = chs.map(({ key, arr }) => {
    let sum = 0, n = 0, sat = 0
    for (let i = 0; i < arr.length; i++) {
      if (armed[i]) { sum += arr[i]; n++; if (arr[i] > 1900) sat++ }
    }
    return { key, mean: sum / n, satPct: sat / n * 100 }
  })
  const means = rows.map(r => r.mean)
  const overall = means.reduce((a, b) => a + b, 0) / means.length
  const spread = nanmax(means) - nanmin(means)
  // Worst motor
  let wi = 0
  for (let i = 1; i < means.length; i++) {
    if (Math.abs(means[i] - overall) > Math.abs(means[wi] - overall)) wi = i
  }
  const worstName = rows[wi].key
  const worstDelta = means[wi] - overall
  const worstRole = worstDelta > 0 ? 'working harder' : 'weaker / underloaded'
  let verdictColor, verdict
  if (spread < 60)   { verdictColor = SUCCESS; verdict = `GOOD · spread ${spread.toFixed(0)} µs` }
  else if (spread < 120) { verdictColor = WARN; verdict = `MARGINAL · spread ${spread.toFixed(0)} µs · suspect ${worstName} (${worstDelta >= 0 ? '+' : ''}${worstDelta.toFixed(0)} µs, ${worstRole})` }
  else { verdictColor = DANGER; verdict = `BAD · spread ${spread.toFixed(0)} µs · check ${worstName} first (${worstDelta >= 0 ? '+' : ''}${worstDelta.toFixed(0)} µs, ${worstRole})` }
  // Diagonal pair (Quad-X)
  let diagLine = ''
  if (chs.length >= 4) {
    const d1 = (means[0] + means[1]) / 2, d2 = (means[2] + means[3]) / 2
    const diff = d1 - d2
    const tag = Math.abs(diff) < 30 ? 'balanced'
      : `front/back or CG offset — pair (M1+M2) ${diff > 0 ? 'higher' : 'lower'} by ${Math.abs(diff).toFixed(0)} µs`
    diagLine = `(M1+M2)/2 = ${d1.toFixed(0)} µs · (M3+M4)/2 = ${d2.toFixed(0)} µs · ${tag}`
  }
  const perMotor = rows.map(r => {
    const delta = r.mean - overall
    let color = SUCCESS, mv = 'ok'
    if (Math.abs(delta) >= 60) { color = DANGER; mv = delta > 0 ? 'working harder' : 'weaker / underloaded' }
    else if (Math.abs(delta) >= 30) { color = WARN; mv = 'watch' }
    return { ...r, delta, deltaColor: color, motorVerdict: mv }
  })
  return { mode: 'motors', kind: kind.value, rows: perMotor, overall, spread, verdict, verdictColor, diagLine, armedCount }
})

// --- Plot ---
const plotRef = ref(null)
let plot = null

function rebuildPlot() {
  if (!plotRef.value) return
  if (plot) { plot.destroy(); plot = null }
  const chs = channels.value
  if (!chs.length) return
  const t0 = props.parsed.t_start || 0
  const tArr = (props.parsed.times.RCOU || []).map(t => t - t0)
  if (!tArr.length) return
  const series = [{}]
  const data = [tArr]
  chs.forEach((c, i) => {
    series.push({ label: c.key, stroke: PALETTE[i % PALETTE.length], width: 1.2, points: { show: false } })
    data.push(c.arr)
  })
  const rect = plotRef.value.getBoundingClientRect()
  plot = new uPlot({
    width: Math.max(400, rect.width),
    height: Math.max(280, rect.height),
    series,
    axes: [
      { stroke: DIM, grid: { stroke: '#323a47', width: 1 }, ticks: { stroke: '#323a47' },
        values: (u, s) => s.map(v => v.toFixed(1) + 's') },
      { stroke: DIM, grid: { stroke: '#323a47', width: 1 }, ticks: { stroke: '#323a47' }, label: 'PWM (µs)' },
    ],
    legend: { show: true },
    cursor: { drag: { x: true, y: false } },
  }, data, plotRef.value)
}

function handleResize() {
  if (!plot || !plotRef.value) return
  const r = plotRef.value.getBoundingClientRect()
  plot.setSize({ width: Math.max(400, r.width), height: Math.max(280, r.height) })
}

onMounted(() => { nextTick(rebuildPlot); window.addEventListener('resize', handleResize) })
onBeforeUnmount(() => { window.removeEventListener('resize', handleResize); if (plot) plot.destroy() })
watch(() => props.parsed, () => nextTick(rebuildPlot))
</script>

<template>
  <div class="motors">
    <div class="title">MOTORS · RCOU PWM PER CHANNEL · BALANCE · DESYNC EVENTS</div>

    <!-- Plane / non-multirotor branch -->
    <div v-if="analysis && analysis.mode === 'servos'" class="card">
      <div class="head-row">
        <span class="kicker" :style="{ color: ACCENT }">SERVOS / THROTTLE</span>
        <span class="meta">frame type: {{ analysis.kind }} · {{ analysis.rows.length }} channels</span>
      </div>
      <div class="hint">
        On a fixed-wing, RCOU channels are aileron / elevator / throttle / rudder servos — not
        independent motors. Comparing means or spread between them is meaningless. Look at the
        throttle channel (usually C3) for engine output; the rest should sit near 1500 µs at trim.
      </div>
      <table>
        <thead><tr><th>CHANNEL</th><th>MIN</th><th>MEAN</th><th>MAX</th><th>RANGE</th><th>LIKELY ROLE</th></tr></thead>
        <tbody>
          <tr v-for="r in analysis.rows" :key="r.key">
            <td class="accent">{{ r.key }}</td>
            <td>{{ r.min.toFixed(0) }}</td>
            <td>{{ r.mean.toFixed(0) }}</td>
            <td>{{ r.max.toFixed(0) }}</td>
            <td>{{ r.range.toFixed(0) }} µs</td>
            <td class="dim">{{ r.role }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Copter branch -->
    <div v-else-if="analysis && analysis.mode === 'motors'" class="card">
      <div class="verdict-row">
        <span class="verdict" :style="{ color: analysis.verdictColor }">{{ analysis.verdict }}</span>
        <span class="meta">avg {{ analysis.overall.toFixed(0) }} µs · {{ analysis.armedCount }} armed samples</span>
      </div>
      <div v-if="analysis.diagLine" class="diag">DIAGONAL PAIRS · {{ analysis.diagLine }}</div>
      <table>
        <thead><tr><th>MOTOR</th><th>MEAN PWM</th><th>Δ vs AVG</th><th>SATURATED &gt;1900</th><th>VERDICT</th></tr></thead>
        <tbody>
          <tr v-for="r in analysis.rows" :key="r.key">
            <td class="accent">{{ r.key }}</td>
            <td>{{ r.mean.toFixed(0) }} µs</td>
            <td :style="{ color: r.deltaColor }">{{ r.delta >= 0 ? '+' : '' }}{{ r.delta.toFixed(0) }} µs</td>
            <td>{{ r.satPct.toFixed(1) }} %</td>
            <td :style="{ color: r.deltaColor }">{{ r.motorVerdict }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else-if="analysis && analysis.mode === 'bench'" class="card">
      <div class="hint">{{ analysis.hint }}</div>
    </div>

    <div v-else class="card">
      <div class="hint">No RCOU (motor output) messages in this log — can't analyse per-channel PWM.</div>
    </div>

    <div class="plot-wrap">
      <div ref="plotRef" class="plot-canvas"></div>
    </div>
  </div>
</template>

<style scoped>
.motors { display: flex; flex-direction: column; gap: 10px; height: 100%; min-height: 0; }
.title {
  color: var(--text-dim);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 2px;
  padding: 0 2px 4px;
}
.card {
  background: var(--bg-1);
  border: 1px solid var(--border);
  padding: 14px 18px;
}
.head-row, .verdict-row { display: flex; gap: 16px; align-items: baseline; margin-bottom: 10px; }
.kicker { font-size: 12px; font-weight: 700; letter-spacing: 2px; font-family: var(--font-mono); }
.verdict { font-size: 13px; font-weight: 700; letter-spacing: 1.5px; font-family: var(--font-mono); }
.meta { color: var(--text-dim); font-size: 11px; font-family: var(--font-mono); }
.diag { color: var(--text-dim); font-size: 11px; font-family: var(--font-mono); margin-bottom: 8px; }
.hint { color: var(--text-dim); font-size: 12px; line-height: 1.5; margin-bottom: 8px; }
table {
  width: 100%; border-collapse: collapse;
  font-family: var(--font-mono); font-size: 11px;
}
th {
  text-align: left;
  background: var(--bg-2);
  color: var(--text-dim);
  font-weight: 700; letter-spacing: 1.5px; font-size: 9px;
  padding: 7px 12px; border-bottom: 1px solid var(--border);
  font-family: var(--font-ui);
}
td { padding: 5px 12px; border-bottom: 1px solid var(--border); color: var(--text); }
.accent { color: var(--accent); }
.dim { color: var(--text-dim); }
.plot-wrap { flex: 1; min-height: 0; }
.plot-canvas { width: 100%; height: 100%; min-height: 280px; border: 1px solid var(--border); background: var(--bg-1); }
</style>
