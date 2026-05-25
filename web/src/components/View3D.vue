<script setup>
// 3D flight track — Plotly scatter3d with the path coloured by altitude.
// Lat/Lng are projected to relative metres using an equirectangular
// approximation around the first valid coordinate.
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { extractTrack } from '../analyzers/extractTrack.js'

const props = defineProps({ parsed: Object })

const plotRef = ref(null)
const noTrack = ref(false)
const loading = ref(true)
const errorMsg = ref('')
let Plotly = null

// Playback state — animates a marker along the track
const playing = ref(false)
const speed = ref(1)
const playT = ref(0)              // seconds since log start
const duration = computed(() => props.parsed?.duration || 0)
let raf = null
let lastTick = 0
// Track data kept in module scope so the playback ticker can read it
// without rebuilding the whole plot every frame.
let trackXs = null, trackYs = null, trackZs = null, trackTRel = null

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
  trackXs = xs; trackYs = ys; trackZs = z; trackTRel = tr.trel

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
  // Playback marker — large cyan dot that the play button moves along
  // the path. Position updated by updatePlayMarker() each frame.
  const cursor = {
    type: 'scatter3d', mode: 'markers',
    x: [xs[0]], y: [ys[0]], z: [z[0]],
    marker: { size: 8, color: '#4a90e2', symbol: 'circle' },
    name: 'cursor', hovertemplate: 'T+%{customdata:.1f}s<extra></extra>',
    customdata: [trackTRel[0] || 0],
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
    await P.react(plotRef.value, [trace, start, end, cursor], layout, {
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

// Move the cursor marker to whatever time playT.value points to.
function updateCursor() {
  if (!Plotly || !plotRef.value || !trackTRel?.length) return
  const target = playT.value
  // Linear search the nearest sample; track is downsampled to ≤3000
  let bi = 0, bd = Infinity
  for (let i = 0; i < trackTRel.length; i++) {
    const d = Math.abs(trackTRel[i] - target)
    if (d < bd) { bd = d; bi = i }
  }
  try {
    Plotly.restyle(plotRef.value, {
      x: [[trackXs[bi]]],
      y: [[trackYs[bi]]],
      z: [[trackZs[bi]]],
      customdata: [[trackTRel[bi]]],
    }, [3])  // cursor is the 4th trace (index 3)
  } catch (_) {}
}

function tick(now) {
  if (!playing.value) return
  if (!lastTick) lastTick = now
  const dt = (now - lastTick) / 1000
  lastTick = now
  playT.value = Math.min(duration.value, playT.value + dt * speed.value)
  updateCursor()
  if (playT.value >= duration.value) { playing.value = false; raf = null; return }
  raf = requestAnimationFrame(tick)
}
function play() {
  if (playing.value) return
  if (playT.value >= duration.value) playT.value = 0
  playing.value = true
  lastTick = 0
  raf = requestAnimationFrame(tick)
}
function pause() {
  playing.value = false
  if (raf) { cancelAnimationFrame(raf); raf = null }
}
function reset() { pause(); playT.value = 0; updateCursor() }
watch(playT, () => { if (!playing.value) updateCursor() })

onMounted(() => {
  render()
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (raf) cancelAnimationFrame(raf)
  if (Plotly && plotRef.value) {
    try { Plotly.purge(plotRef.value) } catch (_) {}
  }
})
watch(() => props.parsed, () => { pause(); playT.value = 0; render() })
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

    <!-- Playback transport -->
    <div class="scrub" v-if="!noTrack && !loading">
      <button class="step" @click="reset" title="Reset to start">⏮</button>
      <button class="step play" @click="playing ? pause() : play()">
        {{ playing ? '❚❚ PAUSE' : '▶ PLAY' }}
      </button>
      <div class="speed-group">
        <button v-for="s in [0.5, 1, 2, 4, 8]" :key="s"
                class="speed-btn"
                :class="{ active: speed === s }"
                @click="speed = s">{{ s }}×</button>
      </div>
      <input type="range" min="0" :max="duration" step="0.05"
             v-model.number="playT" class="slider"
             @mousedown="pause"/>
      <div class="time mono">T+{{ playT.toFixed(1) }}s / {{ duration.toFixed(1) }}s</div>
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
.scrub {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  flex-shrink: 0;
}
.scrub .step {
  background: var(--bg-2);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 5px 12px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 1px;
  cursor: pointer;
}
.scrub .step:hover { color: var(--accent); border-color: var(--accent); }
.scrub .play {
  background: var(--accent);
  color: var(--bg-0);
  border-color: var(--accent);
  font-weight: 700;
  min-width: 88px;
}
.scrub .play:hover { background: var(--accent-2); border-color: var(--accent-2); color: var(--bg-0); }
.speed-group { display: flex; gap: 2px; background: var(--bg-2); border: 1px solid var(--border); padding: 2px; }
.speed-btn {
  background: transparent;
  border: none;
  color: var(--text-dim);
  padding: 4px 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  cursor: pointer;
}
.speed-btn:hover { color: var(--text); }
.speed-btn.active { background: var(--accent); color: var(--bg-0); font-weight: 700; }
.slider {
  flex: 1;
  -webkit-appearance: none; appearance: none;
  height: 4px;
  background: var(--bg-2);
  outline: none;
  border: 1px solid var(--border);
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 14px; height: 14px;
  background: var(--accent);
  cursor: pointer;
}
.time {
  color: var(--text-dim);
  font-size: 11px;
  min-width: 160px;
  text-align: right;
  font-family: var(--font-mono);
}
</style>
