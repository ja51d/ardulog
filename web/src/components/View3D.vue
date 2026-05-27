<script setup>
// 3D flight track — Plotly scatter3d with the path coloured by altitude.
// Lat/Lng are projected to relative metres using an equirectangular
// approximation around the first valid coordinate.
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { extractTrack } from '../analyzers/extractTrack.js'
import { detectFrameKind } from '../analyzers/frameKind.js'
import { loadObj, prerotate, transformMesh } from '../utils/objLoader.js'
import { buildQuadcopter } from '../utils/proceduralModels.js'
import TimelineStrip from './TimelineStrip.vue'

const props = defineProps({ parsed: Object })

// Per-model orientation + visual config. baseRot re-aligns each OBJ so
// its canonical axes are +X forward, +Y left, +Z up. scaleMult scales the
// model relative to the auto-computed track-extent size, so big drones
// don't overshadow short hops.
const MODEL_CONFIG = {
  plane: {
    baseRot: { yaw: Math.PI },         // model nose was at -X; flip 180° → +X forward
    scaleMult: 1.0,
    color: '#dbe4f0',                  // clean aviation silver
  },
  copter: {
    procedural: 'quadcopter',          // clean low-poly mesh built in code
    baseRot: { yaw: 0 },               // already +X forward, +Z up
    scaleMult: 0.07,
    color: '#22d3ee',                  // vivid cyan — pops on dark scene
  },
}

// Cached base meshes — OBJ files are fetched once; procedural meshes
// are built once on first request.
const meshCache = {}
async function getModel(kind) {
  // kind comes from detectFrameKind — "Plane", "Copter", "Quad", etc.
  const isPlane = /plane|fixed/i.test(kind)
  const key = isPlane ? 'plane' : 'copter'
  const cfg = MODEL_CONFIG[key]
  if (!meshCache[key]) {
    let raw
    if (cfg.procedural === 'quadcopter') raw = buildQuadcopter()
    else raw = await loadObj(`/models/${key}.obj`)
    meshCache[key] = prerotate(raw, cfg.baseRot)
  }
  return { key, mesh: meshCache[key], config: cfg }
}
let baseMesh = null         // current model verts/faces (already prerotated)
let modelScale = 10         // chosen at render-time relative to track size
let modelColor = '#dbe4f0'  // per-model fill
let modelTrace = null       // index of mesh3d trace in plot data
let propPhase = 0           // accumulated propeller rotation (rad) for spinning

const plotRef = ref(null)
const noTrack = ref(false)
const loading = ref(true)
const errorMsg = ref('')
const colorBy = ref('alt')   // 'alt' | 'vibe'  — what colors the track
let Plotly = null

// Sample VIBE magnitude at each track timestamp. Linear-search the
// VIBE message stream once, monotonic, so this is O(N+M). Returns null
// if no usable VIBE data.
function sampleVibration(parsed, tRelArr) {
  const vibe = parsed?.data?.VIBE
  const vt   = parsed?.times?.VIBE
  if (!vibe?.VibeX || !vt?.length) return null
  const t0 = parsed.t_start || 0
  const absT = tRelArr.map(t => t + t0)
  const vmag = new Float32Array(tRelArr.length)
  let j = 0
  for (let i = 0; i < absT.length; i++) {
    const target = absT[i]
    while (j + 1 < vt.length && vt[j + 1] <= target) j++
    const vx = vibe.VibeX[j] || 0
    const vy = vibe.VibeY[j] || 0
    const vz = vibe.VibeZ[j] || 0
    vmag[i] = Math.sqrt(vx * vx + vy * vy + vz * vz)
  }
  return vmag
}

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
let vibrationMags = null  // Float32Array, same length as track

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
  vibrationMags = sampleVibration(props.parsed, tr.trel)
  // If no vibe data is available, force colorBy to 'alt'
  if (!vibrationMags) colorBy.value = 'alt'
  lastBi = -1  // force first updateCursor to actually restyle

  // Load the right 3D model and size it relative to track extent.
  // Base mesh is normalized to a 2-unit cube; pick a scale so the model
  // is roughly 4% of the longest track dimension (clamped to a sane range).
  const frameKind = detectFrameKind(props.parsed)
  let model = null
  try { model = await getModel(frameKind) } catch (_) { /* missing OBJ → just skip */ }
  baseMesh = model?.mesh || null
  modelColor = model?.config?.color || '#dbe4f0'
  if (baseMesh) {
    const dx = Math.max(...xs) - Math.min(...xs)
    const dy = Math.max(...ys) - Math.min(...ys)
    const dz = Math.max(...z) - Math.min(...z)
    const extent = Math.max(dx, dy, dz, 1)
    const base = Math.min(Math.max(extent * 0.04, 5), 60)
    modelScale = base * (model.config.scaleMult || 1)
  }

  // Color array — either altitude or vibration magnitude. Plotly's
  // scatter3d line `color` only accepts a colorscale-driven array; pick
  // the source based on the toggle.
  const useVibe = (colorBy.value === 'vibe') && vibrationMags
  const colorArr = useVibe ? Array.from(vibrationMags) : z
  const colorScale = useVibe ? [
    [0,    '#34d399'],   // green — calm
    [0.4,  '#facc15'],   // yellow — moderate
    [0.7,  '#fb923c'],   // orange — high
    [1,    '#f87171'],   // red — extreme
  ] : [
    [0,    '#3da9fc'],
    [0.4,  '#6aa9e8'],
    [0.75, '#f0b75d'],
    [1,    '#ff6b35'],
  ]
  const trace = {
    type: 'scatter3d',
    mode: 'lines',
    x: xs, y: ys, z,
    line: {
      width: 6,
      color: colorArr,
      colorscale: colorScale,
    },
    hovertemplate: useVibe
      ? 'E %{x:.1f} m · N %{y:.1f} m · Z %{z:.1f} m · vibe %{customdata:.1f}<extra></extra>'
      : 'E %{x:.1f} m · N %{y:.1f} m · Z %{z:.1f} m<extra></extra>',
    customdata: useVibe ? colorArr : undefined,
    name: 'track',
  }
  const start = {
    type: 'scatter3d', mode: 'markers',
    x: [xs[0]], y: [ys[0]], z: [z[0]],
    marker: {
      size: 8, color: '#5dba7c',
      line: { color: '#0e131c', width: 1.5 },
    },
    name: 'start', hovertemplate: 'START<extra></extra>',
  }
  const end = {
    type: 'scatter3d', mode: 'markers',
    x: [xs[xs.length - 1]], y: [ys[ys.length - 1]], z: [z[z.length - 1]],
    marker: {
      size: 8, color: '#ff6b35',
      line: { color: '#0e131c', width: 1.5 },
    },
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

  // 3D vehicle model — mesh3d positioned at the cursor, rotated by heading.
  let modelTraceObj = null
  if (baseMesh) {
    // Initial heading = direction of travel from sample 0 → 1
    const yaw0 = (xs.length > 1)
      ? Math.atan2(ys[1] - ys[0], xs[1] - xs[0])
      : 0
    const t0 = transformMesh(baseMesh, {
      yaw: yaw0, scale: modelScale,
      tx: xs[0], ty: ys[0], tz: z[0],
    })
    modelTraceObj = {
      type: 'mesh3d',
      x: t0.x, y: t0.y, z: t0.z,
      i: baseMesh.i, j: baseMesh.j, k: baseMesh.k,
      color: modelColor,
      opacity: 1.0,
      flatshading: true,
      // Brighter ambient + soft specular gives a clean studio-render
      // feel that holds up at low poly counts.
      lighting: {
        ambient: 0.75,
        diffuse: 0.95,
        specular: 0.45,
        roughness: 0.35,
        fresnel: 0.4,
        vertexnormalsepsilon: 1e-12,
        facenormalsepsilon: 1e-6,
      },
      lightposition: { x: 800, y: 1200, z: 2400 },
      hoverinfo: 'skip',
      name: 'vehicle',
      showscale: false,
    }
  }

  // Subtly different background tones for each wall give the cube a
  // sense of depth without screaming "I am Plotly".
  const layout = {
    paper_bgcolor: '#0e131c',
    plot_bgcolor:  '#0e131c',
    margin: { l: 0, r: 0, t: 0, b: 0 },
    showlegend: false,
    autosize: true,
    scene: {
      bgcolor: '#0e131c',
      aspectmode: 'data',
      camera: {
        eye:    { x: 1.4, y: 1.4, z: 0.85 },
        center: { x: 0,   y: 0,   z: 0 },
        up:     { x: 0,   y: 0,   z: 1 },
      },
      xaxis: {
        title: { text: 'East (m)',  font: { size: 11, color: '#9aa6b8' } },
        color: '#9aa6b8',
        gridcolor:        '#1f2733',
        backgroundcolor:  '#141a24',
        showbackground:   true,
        zerolinecolor:    '#2a3340',
        zerolinewidth:    1,
        showspikes:       false,
      },
      yaxis: {
        title: { text: 'North (m)', font: { size: 11, color: '#9aa6b8' } },
        color: '#9aa6b8',
        gridcolor:        '#1f2733',
        backgroundcolor:  '#11161f',
        showbackground:   true,
        zerolinecolor:    '#2a3340',
        zerolinewidth:    1,
        showspikes:       false,
      },
      zaxis: {
        title: { text: 'Alt (m)',   font: { size: 11, color: '#9aa6b8' } },
        color: '#9aa6b8',
        gridcolor:        '#1f2733',
        backgroundcolor:  '#0e131c',
        showbackground:   true,
        zerolinecolor:    '#2a3340',
        zerolinewidth:    1,
        showspikes:       false,
      },
    },
    font: { family: 'Inter, sans-serif', color: '#cdd6e0', size: 11 },
  }

  const traces = [trace, start, end, cursor]
  if (modelTraceObj) { traces.push(modelTraceObj); modelTrace = 4 } else { modelTrace = -1 }
  try {
    await P.react(plotRef.value, traces, layout, {
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

// Cached sample index — lets us skip restyles when nothing's moved.
let lastBi = -1

// Binary search for the largest index where trackTRel[i] <= target,
// then pick the nearer of lo / lo+1. O(log n) — fast at 60fps even on
// huge downsampled tracks.
function findNearestIdx(target) {
  const n = trackTRel.length
  if (!n) return 0
  let lo = 0, hi = n - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (trackTRel[mid] <= target) lo = mid
    else hi = mid - 1
  }
  if (lo + 1 < n && Math.abs(trackTRel[lo + 1] - target) < Math.abs(trackTRel[lo] - target)) {
    return lo + 1
  }
  return lo
}

// Move the cursor marker to whatever time playT.value points to.
function updateCursor() {
  if (!Plotly || !plotRef.value || !trackTRel?.length) return
  const bi = findNearestIdx(playT.value)
  const sampleChanged = (bi !== lastBi)
  // Models with spinning props need updating every frame even when the
  // cursor sample hasn't advanced — otherwise props look frozen.
  const propsAlive = playing.value && baseMesh?.propellers && modelTrace >= 0
  if (!sampleChanged && !propsAlive) return
  lastBi = bi

  if (sampleChanged) {
    try {
      Plotly.restyle(plotRef.value, {
        x: [[trackXs[bi]]],
        y: [[trackYs[bi]]],
        z: [[trackZs[bi]]],
        customdata: [[trackTRel[bi]]],
      }, [3])  // cursor is the 4th trace (index 3)
    } catch (_) {}
  }

  // Move + orient the 3D vehicle model. Heading = direction of motion
  // between the current sample and the next (or prev at the very end).
  if (modelTrace >= 0 && baseMesh) {
    const ni = Math.min(bi + 1, trackXs.length - 1)
    const pi = Math.max(bi - 1, 0)
    const dx = trackXs[ni] - trackXs[pi]
    const dy = trackYs[ni] - trackYs[pi]
    const yaw = (dx === 0 && dy === 0) ? 0 : Math.atan2(dy, dx)
    // Approximate pitch from altitude rate vs horizontal speed
    const dz = trackZs[ni] - trackZs[pi]
    const hor = Math.hypot(dx, dy) || 1
    const pitch = Math.atan2(dz, hor)
    // Spin propellers — phase advances faster at faster playback speeds
    if (baseMesh.propellers) propPhase += 0.55 * Math.max(speed.value, 1)
    const t = transformMesh(baseMesh, {
      yaw, pitch, scale: modelScale,
      tx: trackXs[bi], ty: trackYs[bi], tz: trackZs[bi],
      propSpin: propPhase,
    })
    try {
      Plotly.restyle(plotRef.value, { x: [t.x], y: [t.y], z: [t.z] }, [modelTrace])
    } catch (_) {}
  }
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
watch(colorBy, () => render())
</script>

<template>
  <div class="three-d">
    <div class="title-bar">
      <div class="title">3D · FLIGHT TRACK · {{ colorBy === 'vibe' ? 'VIBRATION HEATMAP' : 'ALTITUDE-COLOURED' }}</div>
      <div class="color-toggle" v-if="vibrationMags">
        <button :class="{ active: colorBy === 'alt' }"  @click="colorBy = 'alt'">ALT</button>
        <button :class="{ active: colorBy === 'vibe' }" @click="colorBy = 'vibe'">VIBE</button>
      </div>
    </div>
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

    <TimelineStrip v-if="!noTrack && !loading" :parsed="parsed"
                   :play-t="playT" :duration="duration"
                   @seek="playT = $event"/>

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
.title-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 2px 4px; }
.title {
  color: var(--text-dim);
  font-size: 11px; font-weight: 700; letter-spacing: 2px;
}
.color-toggle {
  display: flex; gap: 2px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  padding: 3px;
  border-radius: 999px;
}
.color-toggle button {
  background: transparent; border: none;
  color: var(--text-dim);
  padding: 4px 12px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.5px;
  cursor: pointer;
  border-radius: 999px;
  transition: color 120ms, background 120ms;
}
.color-toggle button:hover { color: var(--text); }
.color-toggle button.active { background: var(--grad-accent); color: #fff; font-weight: 700; }
.canvas-wrap {
  flex: 1; min-height: 400px;
  position: relative;
  border: 1px solid var(--border);
  background: #0e131c;
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: var(--shadow-soft);
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
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  flex-shrink: 0;
}
.scrub .step {
  background: var(--surface-1);
  color: var(--text-2);
  border: 1px solid var(--border);
  padding: 7px 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 1px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color 160ms var(--ease-out), border-color 160ms var(--ease-out), background 160ms var(--ease-out);
}
.scrub .step:hover { color: var(--accent-2); border-color: var(--accent); background: var(--accent-soft); }
.scrub .play {
  background: var(--grad-accent);
  color: #fff;
  border-color: transparent;
  font-weight: 700;
  min-width: 96px;
  box-shadow: 0 4px 16px rgba(61,169,252,0.35);
}
.scrub .play:hover {
  filter: brightness(1.1);
  box-shadow: 0 4px 22px rgba(61,169,252,0.55);
  color: #fff;
}
.speed-group {
  display: flex; gap: 2px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  padding: 3px;
  border-radius: 999px;
}
.speed-btn {
  background: transparent;
  border: none;
  color: var(--text-dim);
  padding: 4px 10px;
  font-family: var(--font-mono);
  font-size: 10px;
  cursor: pointer;
  border-radius: 999px;
  transition: color 120ms, background 120ms;
}
.speed-btn:hover { color: var(--text); }
.speed-btn.active { background: var(--grad-accent); color: #fff; font-weight: 700; }
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

/* ===== Mobile ===== */
@media (max-width: 768px) {
  .canvas-wrap { min-height: 320px; }
  .scrub { flex-wrap: wrap; row-gap: 10px; padding: 10px 12px; }
  .scrub .slider { flex: 1 1 100%; order: 10; }
  .scrub .time { flex: 1 1 100%; text-align: left; order: 11; min-width: 0; font-size: 10px; }
  .speed-group .speed-btn { padding: 4px 8px; font-size: 9px; }
}
</style>
