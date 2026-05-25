<script setup>
// 3D flight track — Plotly scatter3d with the path coloured by altitude.
// Lat/Lng are projected to relative metres using an equirectangular
// approximation around the first valid coordinate.
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { extractTrack } from '../analyzers/extractTrack.js'

// Plotly is ~1.4 MB gzipped — load it on demand only when the 3D tab is
// first opened, so the rest of the app stays a tiny bundle.
let PlotlyP = null
function loadPlotly() {
  if (!PlotlyP) PlotlyP = import('plotly.js-dist-min').then(m => m.default || m)
  return PlotlyP
}

const props = defineProps({ parsed: Object })

const plotRef = ref(null)
const noTrack = ref(false)

const EARTH_R = 6371000   // metres

function project(coords) {
  const [lat0, lng0] = coords[0]
  const cos0 = Math.cos(lat0 * Math.PI / 180)
  const xs = [], ys = []
  for (const [lat, lng] of coords) {
    xs.push((lng - lng0) * cos0 * (Math.PI / 180) * EARTH_R)   // east-west metres
    ys.push((lat - lat0) * (Math.PI / 180) * EARTH_R)          // north-south metres
  }
  return { xs, ys }
}

const loading = ref(true)
async function render() {
  if (!plotRef.value) return
  const tr = extractTrack(props.parsed)
  if (!tr.coords.length) { noTrack.value = true; loading.value = false; return }
  noTrack.value = false
  loading.value = true
  const Plotly = await loadPlotly()
  loading.value = false
  if (!plotRef.value) return
  const { xs, ys } = project(tr.coords)
  // Altitude relative to the takeoff point so colors span a useful range
  const z0 = tr.alts.length ? tr.alts[0] : 0
  const z = tr.alts.map(a => a - z0)

  const trace = {
    type: 'scatter3d',
    mode: 'lines+markers',
    x: xs, y: ys, z,
    line: { width: 4, color: z, colorscale: [
      [0,    '#1a1f29'],
      [0.25, '#4a90e2'],
      [0.5,  '#6aa9e8'],
      [0.75, '#d9a14a'],
      [1,    '#d96666'],
    ], showscale: false },
    marker: { size: 2, color: z, colorscale: 'Viridis', showscale: false },
    hovertemplate: 'E %{x:.1f} m · N %{y:.1f} m · Z %{z:.1f} m<extra></extra>',
    name: 'track',
  }
  // Start/end markers
  const start = { type: 'scatter3d', mode: 'markers', x: [xs[0]], y: [ys[0]], z: [z[0]],
    marker: { size: 6, color: '#5dba7c', line: { color: '#1a1f29', width: 1 } },
    name: 'start', hovertemplate: 'START<extra></extra>' }
  const end = { type: 'scatter3d', mode: 'markers',
    x: [xs[xs.length-1]], y: [ys[ys.length-1]], z: [z[z.length-1]],
    marker: { size: 6, color: '#d9a14a', line: { color: '#1a1f29', width: 1 } },
    name: 'end', hovertemplate: 'END<extra></extra>' }

  const layout = {
    paper_bgcolor: '#1a1f29',
    plot_bgcolor:  '#1a1f29',
    margin: { l: 0, r: 0, t: 0, b: 0 },
    showlegend: false,
    scene: {
      bgcolor: '#1a1f29',
      aspectmode: 'data',
      camera: { eye: { x: 1.6, y: 1.6, z: 0.9 } },
      xaxis: { title: 'East (m)',  color: '#7a8699', gridcolor: '#323a47', backgroundcolor: '#1a1f29', showbackground: true, zerolinecolor: '#323a47' },
      yaxis: { title: 'North (m)', color: '#7a8699', gridcolor: '#323a47', backgroundcolor: '#1a1f29', showbackground: true, zerolinecolor: '#323a47' },
      zaxis: { title: 'Alt (m)',   color: '#7a8699', gridcolor: '#323a47', backgroundcolor: '#1a1f29', showbackground: true, zerolinecolor: '#323a47' },
    },
    font: { family: 'Inter, sans-serif', color: '#cdd6e0', size: 11 },
  }
  Plotly.react(plotRef.value, [trace, start, end], layout, {
    displayModeBar: true,
    modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
    responsive: true,
  })
}

onMounted(() => nextTick(render))
onBeforeUnmount(async () => {
  if (plotRef.value && PlotlyP) {
    try { (await PlotlyP).purge(plotRef.value) } catch (_) {}
  }
})
watch(() => props.parsed, () => nextTick(render))
</script>

<template>
  <div class="three-d">
    <div class="title">3D · FLIGHT TRACK · ALTITUDE-COLOURED</div>
    <div ref="plotRef" class="canvas"></div>
    <div v-if="loading && !noTrack" class="empty-msg">
      <div class="t">LOADING 3D ENGINE…</div>
      <div class="s">Plotly is ~1.4 MB — only fetched when you open this tab.</div>
    </div>
    <div v-if="noTrack" class="empty-msg">
      <div class="t">NO TRACK</div>
      <div class="s">No valid POS/GPS coordinates found in this log.</div>
    </div>
  </div>
</template>

<style scoped>
.three-d { display: flex; flex-direction: column; gap: 10px; height: 100%; min-height: 0; position: relative; }
.title { color: var(--text-dim); font-size: 11px; font-weight: 700; letter-spacing: 2px; padding: 0 2px 4px; }
.canvas { flex: 1; min-height: 0; border: 1px solid var(--border); background: var(--bg-1); }
.empty-msg {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  text-align: center; pointer-events: none;
}
.empty-msg .t { color: var(--text-dim); font-size: 14px; letter-spacing: 4px; font-weight: 700; }
.empty-msg .s { color: var(--text-dim); font-size: 11px; margin-top: 8px; font-family: var(--font-mono); }
</style>
