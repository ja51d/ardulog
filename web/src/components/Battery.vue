<script setup>
// Battery health view — voltage / current / consumed mAh from BAT
// messages (or CURR fallback). Plots two stacked uPlot charts plus
// a header tile with peak/average stats and a voltage-sag estimate.
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps({ parsed: Object })

const volRef = ref(null)
const curRef = ref(null)
const plots = { v: null, c: null }
const error = ref('')

const series = computed(() => {
  const d = props.parsed?.data, t = props.parsed?.times
  if (!d) return null
  const t0 = props.parsed.t_start || 0
  // Prefer BAT (modern AP), fall back to CURR (older logs)
  const block = d.BAT || d.CURR
  const tarr  = t?.BAT || t?.CURR
  if (!block || !tarr?.length) return null
  const trel = tarr.map(v => v - t0)
  // Battery 0 voltage in volts; current in amps; current_total = mAh consumed
  const volt = block.Volt || block.V || block.VoltR || []
  const curr = block.Curr || block.C || block.A || []
  const mAh  = block.CurrTot || block.MAH || block.E || []
  return { trel, volt, curr, mAh }
})

const stats = computed(() => {
  const s = series.value
  if (!s) return null
  const max = (arr) => { let m = -Infinity; for (const v of arr) if (v > m) m = v; return m === -Infinity ? null : m }
  const min = (arr) => { let m =  Infinity; for (const v of arr) if (v < m) m = v; return m ===  Infinity ? null : m }
  const avg = (arr) => { if (!arr.length) return null; let s = 0, n = 0; for (const v of arr) { if (Number.isFinite(v)) { s += v; n++ } } return n ? s / n : null }
  const vMin = min(s.volt), vMax = max(s.volt), vAvg = avg(s.volt)
  const cMax = max(s.curr), cAvg = avg(s.curr)
  const mLast = s.mAh.length ? s.mAh[s.mAh.length - 1] : null
  const sag = (vMax != null && vMin != null) ? vMax - vMin : null
  return { vMin, vMax, vAvg, cMax, cAvg, mLast, sag }
})

function fmt(v, d = 2, suffix = '') {
  return v == null ? '—' : v.toFixed(d) + suffix
}

function build() {
  if (!volRef.value || !curRef.value) return
  const s = series.value
  // Tear down previous plots if any
  for (const k of Object.keys(plots)) if (plots[k]) { plots[k].destroy(); plots[k] = null }
  if (!s) return

  const DIM = '#7d8aa0'
  const common = {
    width: volRef.value.clientWidth || 600,
    height: 220,
    axes: [
      { stroke: DIM, grid: { stroke: '#1f2733', width: 1 },
        values: (u, s) => s.map(v => v.toFixed(0) + 's') },
      { stroke: DIM, grid: { stroke: '#1f2733', width: 1 } },
    ],
    cursor: { drag: { x: true, y: false } },
    scales: { x: { time: false } },
    legend: { show: true },
  }

  if (s.volt?.length) {
    plots.v = new uPlot({
      ...common,
      series: [{}, {
        label: 'Voltage (V)', stroke: '#3da9fc', width: 1.6, fill: 'rgba(61,169,252,0.10)',
      }],
    }, [s.trel, Array.from(s.volt)], volRef.value)
  }
  if (s.curr?.length) {
    plots.c = new uPlot({
      ...common,
      series: [{}, {
        label: 'Current (A)', stroke: '#ff6b35', width: 1.6, fill: 'rgba(255,107,53,0.08)',
      }],
    }, [s.trel, Array.from(s.curr)], curRef.value)
  }
}

function resize() {
  if (!volRef.value || !curRef.value) return
  if (plots.v) plots.v.setSize({ width: volRef.value.clientWidth, height: 220 })
  if (plots.c) plots.c.setSize({ width: curRef.value.clientWidth, height: 220 })
}

let ro
onMounted(() => {
  nextTick(build)
  ro = new ResizeObserver(resize)
  if (volRef.value) ro.observe(volRef.value)
})
onBeforeUnmount(() => {
  if (ro) ro.disconnect()
  for (const k of Object.keys(plots)) if (plots[k]) plots[k].destroy()
})
watch(() => props.parsed, () => nextTick(build))
</script>

<template>
  <div class="battery">
    <div class="title">BATTERY · VOLTAGE · CURRENT · CONSUMED</div>

    <div v-if="!series" class="empty">
      <div class="t">NO BATTERY DATA</div>
      <div class="s">No BAT / CURR messages in this log.</div>
    </div>

    <template v-else>
      <div class="stats">
        <div class="cell"><div class="k">PEAK V</div><div class="v">{{ fmt(stats.vMax, 2, ' V') }}</div></div>
        <div class="cell"><div class="k">MIN V</div><div class="v">{{ fmt(stats.vMin, 2, ' V') }}</div></div>
        <div class="cell"><div class="k">AVG V</div><div class="v">{{ fmt(stats.vAvg, 2, ' V') }}</div></div>
        <div class="cell"><div class="k">SAG</div><div class="v">{{ fmt(stats.sag, 2, ' V') }}</div></div>
        <div class="cell"><div class="k">PEAK A</div><div class="v">{{ fmt(stats.cMax, 1, ' A') }}</div></div>
        <div class="cell"><div class="k">AVG A</div><div class="v">{{ fmt(stats.cAvg, 1, ' A') }}</div></div>
        <div class="cell"><div class="k">USED</div><div class="v">{{ fmt(stats.mLast, 0, ' mAh') }}</div></div>
      </div>

      <div class="chart">
        <div class="pane-label">VOLTAGE</div>
        <div ref="volRef" class="canvas"></div>
      </div>
      <div class="chart">
        <div class="pane-label">CURRENT</div>
        <div ref="curRef" class="canvas"></div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.battery { display: flex; flex-direction: column; gap: 12px; }
.title { color: var(--text-mute); font-size: 11px; font-weight: 700; letter-spacing: 2px; padding: 0 2px 4px; }
.empty {
  padding: 32px;
  text-align: center;
  background: linear-gradient(180deg, var(--panel-from), var(--panel-to));
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.empty .t { font-size: 14px; letter-spacing: 4px; font-weight: 700; background: var(--grad-accent); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.empty .s { color: var(--text-dim); font-family: var(--font-mono); font-size: 11px; margin-top: 10px; }

.stats {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 10px;
}
.cell {
  position: relative;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  overflow: hidden;
}
.cell::after { content:''; position:absolute; top:0; left:0; right:0; height:2px; background: var(--grad-accent); opacity: 0.55; }
.cell .k { color: var(--text-mute); font-size: 9px; font-weight: 700; letter-spacing: 2px; }
.cell .v { color: var(--text); font-family: var(--font-mono); font-size: 17px; font-weight: 700; margin-top: 4px; }

.chart {
  background: linear-gradient(180deg, var(--panel-from), var(--panel-to));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  box-shadow: var(--shadow-soft);
}
.pane-label { color: var(--text-mute); font-size: 9px; letter-spacing: 2.5px; font-weight: 700; margin-bottom: 8px; }
.canvas { width: 100%; height: 220px; }

@media (max-width: 900px) { .stats { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 480px) { .stats { grid-template-columns: repeat(2, 1fr); } .cell .v { font-size: 14px; } }
</style>
