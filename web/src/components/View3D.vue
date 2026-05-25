<script setup>
// 3D flight track — Plotly scatter3d with the path coloured by altitude.
// Lat/Lng are projected to relative metres using an equirectangular
// approximation around the first valid coordinate.
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { extractTrack } from '../analyzers/extractTrack.js'

const props = defineProps({ parsed: Object })

const plotRef = ref(null)
const noTrack = ref(false)
const loading = ref(true)
const errorMsg = ref('')
let Plotly = null

const EARTH_R = 6371000   // metres

function project(coords) {
  const [lat0, lng0] = coords[0]
  const cos0 = Math.cos(lat0 * Math.PI / 180)
  const xs = [], ys = []
  for (const [lat, lng] of coords) {
    xs.push((lng - lng0) * cos0 * (Math.PI / 180) * EARTH_R)
    ys.push((lat - lat0) * (Math.PI / 180) * EARTH_R)
  }
  return { xs, ys }
}

async function ensurePlotly() {
  if (Plotly) return Plotly
  try {
    const mod = await import('plotly.js-dist-min')
    Plotly = mod.default || mod.Plotly || mod
    return Plotly
  } catch (e) {
    errorMsg.value = 'Failed to load Plotly: ' + (e?.message || e)
    return null
  }
}

async function render() {
  loading.value = true
  errorMsg.value = ''
  await nextTick()
  if (!plotRef.value) { loading.value = false; return }

  const tr = extractTrack(props.parsed)
  if (!tr.coords.length) {
    noTrack.value = true
    loading.value = false
    return
  }
  noTrack.value = false

  const P = await ensurePlotly()
  if (!P || !plotRef.value) { loading.value = false; return }

  const { xs, ys } = project(tr.coords)
  const z0 = tr.alts.length ? tr.alts[0] : 0
  const z = tr.alts.map(a => a - z0)

  const trace = {
    type: 'scatter3d',
    mode: 'lines',
    x: xs, y: ys, z,
    line: {
      width: 5,
      color: z,
      colorscale: [
        [0,    '#4a90e2'],
        [0.5,  '#6aa9e8'],
        [0.75, '#d9a14a'],
        [1,    '#d96666'],
      ],
    },
    hovertemplate: 'E %{x:.1f} m · N %{y:.1f} m · Z %{z:.1f} m<extra></extra>',
    name: 'track',
  }
  const start = {
    type: 'scatter3d', mode: 'markers',
    x: [xs[0]], y: [ys[0]], z: [z[0]],
    marker: { size: 6, color: '#5dba7c' },
    name: 'start', hovertemplate: 'START<extra></extra>',
  }
  const end = {
    type: 'scatter3d', mode: 'markers',
    x: [xs[xs.length - 1]], y: [ys[ys.length - 1]], z: [z[z.length - 1]],
    marker: { size: 6, color: '#d9a14a' },
    name: 'end', hovertemplate: 'END<extra></extra>',
  }

  const layout = {
    paper_bgcolor: '#1a1f29',
    plot_bgcolor:  '#1a1f29',
    margin: { l: 0, r: 0, t: 0, b: 0 },
    showlegend: false,
    autosize: true,
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

  try {
    await P.react(plotRef.value, [trace, start, end], layout, {
      displayModeBar: true,
      responsive: true,
      modeBarButtonsToRemove: ['toImage'],
    })
    // Force a layout pass — Plotly sometimes ships with 0 height inside
    // a flex container until it sees a resize event.
    if (P.Plots && P.Plots.resize) P.Plots.resize(plotRef.value)
  } catch (e) {
    errorMsg.value = 'Plotly render error: ' + (e?.message || e)
  }
  loading.value = false
}

function onResize() {
  if (Plotly && plotRef.value && Plotly.Plots) {
    try { Plotly.Plots.resize(plotRef.value) } catch (_) {}
  }
}

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (Plotly && plotRef.value) {
    try { Plotly.purge(plotRef.value) } catch (_) {}
  }
})
watch(() => props.parsed, () => render())
</script>

<template>
  <div class="three-d">
    <div class="title">3D · FLIGHT TRACK · ALTITUDE-COLOURED</div>
    <div class="canvas-wrap">
      <div ref="plotRef" class="canvas"></div>
      <div v-if="loading && !noTrack && !errorMsg" class="overlay">
        <div class="t">LOADING 3D ENGINE…</div>
        <div class="s">Plotly is ~1.4 MB — fetched the first time you open this tab.</div>
      </div>
      <div v-else-if="noTrack" class="overlay">
        <div class="t">NO TRACK</div>
        <div class="s">No valid POS/GPS coordinates found in this log.</div>
      </div>
      <div v-else-if="errorMsg" class="overlay error">
        <div class="t">PLOTLY ERROR</div>
        <div class="s">{{ errorMsg }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.three-d {
  display: flex; flex-direction: column; gap: 10px;
  height: 100%; min-height: 0;
}
.title {
  color: var(--text-dim);
  font-size: 11px; font-weight: 700; letter-spacing: 2px;
  padding: 0 2px 4px;
}
.canvas-wrap {
  flex: 1; min-height: 400px;
  position: relative;
  border: 1px solid var(--border);
  background: var(--bg-1);
}
.canvas { width: 100%; height: 100%; min-height: 400px; }
.overlay {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  pointer-events: none;
  background: rgba(26, 31, 41, 0.92);
  padding: 22px 30px;
  border: 1px solid var(--border);
  max-width: 80%;
}
.overlay.error { border-color: var(--danger); }
.overlay .t {
  color: var(--text-dim);
  font-size: 14px; letter-spacing: 4px; font-weight: 700;
}
.overlay.error .t { color: var(--danger); }
.overlay .s {
  color: var(--text-dim);
  font-size: 11px; margin-top: 8px;
  font-family: var(--font-mono);
  line-height: 1.5;
}
</style>
