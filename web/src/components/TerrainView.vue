<script setup>
// 3D terrain map — flight track drawn over real satellite imagery with
// elevation. Uses MapLibre GL (open-source) + free Esri World Imagery
// tiles + AWS Open Data terrarium DEM tiles. Zero API keys needed.
import { ref, watch, onMounted, onBeforeUnmount, computed, nextTick } from 'vue'
import { extractTrack } from '../analyzers/extractTrack.js'
import { detectFrameKind } from '../analyzers/frameKind.js'
import TimelineStrip from './TimelineStrip.vue'

const props = defineProps({ parsed: Object })

const containerRef = ref(null)
const noTrack = ref(false)
const loading = ref(true)
const errorMsg = ref('')

// Playback state
const playing = ref(false)
const speed = ref(1)
const playT = ref(0)
const duration = computed(() => props.parsed?.duration || 0)
let raf = null
let lastTick = 0

let map = null              // MapLibre instance
let track = null            // { coords, alts, trel }
let lastBi = -1
let isPlane = false         // pick plane vs copter icon

// Top-down SVG icons rendered to canvas → loaded as map images. The map's
// icon-rotate property spins them per-feature to match heading.
function vehicleIconCanvas(kind) {
  const size = 64
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')
  ctx.clearRect(0, 0, size, size)
  const cx = size / 2, cy = size / 2
  if (kind === 'plane') {
    // Clean delta-wing silhouette pointing UP (+Y in canvas terms).
    // Map's icon-rotate=0 means image's +Y points east, so we draw nose
    // pointing right (+X in canvas) instead.
    ctx.fillStyle = '#dbe4f0'
    ctx.strokeStyle = '#0e131c'
    ctx.lineWidth = 1.5
    ctx.lineJoin = 'round'
    ctx.beginPath()
    // Nose (right), wings (top/bottom), fuselage
    ctx.moveTo(cx + 26, cy)        // nose
    ctx.lineTo(cx + 6, cy - 6)
    ctx.lineTo(cx + 2, cy - 22)    // wing tip top
    ctx.lineTo(cx - 6, cy - 22)
    ctx.lineTo(cx - 4, cy - 6)
    ctx.lineTo(cx - 18, cy - 4)
    ctx.lineTo(cx - 22, cy - 10)   // tail fin top
    ctx.lineTo(cx - 26, cy - 10)
    ctx.lineTo(cx - 22, cy)
    ctx.lineTo(cx - 26, cy + 10)   // tail fin bottom
    ctx.lineTo(cx - 22, cy + 10)
    ctx.lineTo(cx - 18, cy + 4)
    ctx.lineTo(cx - 4, cy + 6)
    ctx.lineTo(cx - 6, cy + 22)
    ctx.lineTo(cx + 2, cy + 22)    // wing tip bottom
    ctx.lineTo(cx + 6, cy + 6)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()
    // Canopy dot
    ctx.fillStyle = '#7dd3fc'
    ctx.beginPath(); ctx.arc(cx + 12, cy, 2.5, 0, Math.PI * 2); ctx.fill()
  } else {
    // Quadcopter — circle body + 4 arms with prop discs
    ctx.fillStyle = '#22d3ee'
    ctx.strokeStyle = '#0e131c'
    ctx.lineWidth = 1.5
    // Arms (X)
    ctx.lineCap = 'round'
    ctx.strokeStyle = '#22d3ee'
    ctx.lineWidth = 3
    for (const a of [Math.PI/4, -Math.PI/4, 3*Math.PI/4, -3*Math.PI/4]) {
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.lineTo(cx + Math.cos(a) * 22, cy + Math.sin(a) * 22)
      ctx.stroke()
    }
    // Prop discs at arm ends
    ctx.fillStyle = 'rgba(34, 211, 238, 0.45)'
    ctx.strokeStyle = '#22d3ee'
    ctx.lineWidth = 1.5
    for (const a of [Math.PI/4, -Math.PI/4, 3*Math.PI/4, -3*Math.PI/4]) {
      ctx.beginPath()
      ctx.arc(cx + Math.cos(a) * 22, cy + Math.sin(a) * 22, 9, 0, Math.PI * 2)
      ctx.fill(); ctx.stroke()
    }
    // Body
    ctx.fillStyle = '#22d3ee'
    ctx.strokeStyle = '#0e131c'
    ctx.lineWidth = 1.5
    ctx.beginPath(); ctx.arc(cx, cy, 7, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
    // Forward indicator (nose marker)
    ctx.fillStyle = '#ff6b35'
    ctx.beginPath(); ctx.arc(cx + 13, cy, 2.5, 0, Math.PI * 2); ctx.fill()
  }
  return c
}

async function render() {
  loading.value = true
  errorMsg.value = ''
  await nextTick()

  const tr = extractTrack(props.parsed)
  if (!tr.coords.length) { noTrack.value = true; loading.value = false; return }
  noTrack.value = false
  track = tr
  isPlane = /plane|fixed/i.test(detectFrameKind(props.parsed))

  let maplibregl
  try {
    const mod = await import('maplibre-gl')
    await import('maplibre-gl/dist/maplibre-gl.css')
    maplibregl = mod.default || mod
  } catch (e) {
    errorMsg.value = 'Failed to load MapLibre: ' + (e?.message || e)
    loading.value = false
    return
  }

  if (!containerRef.value) { loading.value = false; return }

  // Center on the start of the track
  const [lat0, lng0] = tr.coords[0]

  // Dispose any previous instance (component remounts between tab switches)
  if (map) { try { map.remove() } catch (_) {} map = null }

  map = new maplibregl.Map({
    container: containerRef.value,
    style: {
      version: 8,
      glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
      sources: {
        // Esri World Imagery — free satellite tiles, no key needed.
        // Attribution required per their terms of use.
        'sat': {
          type: 'raster',
          tiles: [
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          ],
          tileSize: 256,
          maxzoom: 19,
          attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
        },
        // AWS Terrarium PNG-encoded elevation tiles — free, no key.
        'terrain': {
          type: 'raster-dem',
          tiles: [
            'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
          ],
          encoding: 'terrarium',
          tileSize: 256,
          maxzoom: 14,
          attribution: 'Terrain © Mapzen / AWS Open Data',
        },
      },
      layers: [
        { id: 'sat-layer', type: 'raster', source: 'sat' },
      ],
      sky: {
        'sky-color':            '#1a2540',
        'sky-horizon-blend':    0.5,
        'horizon-color':        '#0e131c',
        'horizon-fog-blend':    0.4,
        'fog-color':            '#0e131c',
        'fog-ground-blend':     0.7,
      },
    },
    center: [lng0, lat0],
    zoom: 14,
    pitch: 62,
    bearing: 0,
    antialias: true,
    attributionControl: { compact: true },
  })

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right')
  map.scrollZoom.setWheelZoomRate(1 / 200)

  map.on('load', () => {
    // Enable terrain
    map.setTerrain({ source: 'terrain', exaggeration: 1.4 })

    // Flight track polyline (3D, drawn on top of terrain)
    const featureCoords = tr.coords.map(([lat, lng], i) => [lng, lat, tr.alts[i] || 0])
    map.addSource('track', {
      type: 'geojson',
      data: { type: 'Feature', geometry: { type: 'LineString', coordinates: featureCoords } },
    })
    map.addLayer({
      id: 'track-glow',
      type: 'line',
      source: 'track',
      paint: {
        'line-color':   '#3da9fc',
        'line-width':   10,
        'line-opacity': 0.20,
        'line-blur':    8,
      },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    })
    map.addLayer({
      id: 'track-line',
      type: 'line',
      source: 'track',
      paint: {
        'line-color':   '#5fbcff',
        'line-width':   3.5,
        'line-opacity': 0.95,
      },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    })

    // Start/end markers
    const lastCoord = tr.coords[tr.coords.length - 1]
    map.addSource('endpoints', {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: [
          { type: 'Feature', properties: { kind: 'start' }, geometry: { type: 'Point', coordinates: [lng0, lat0] } },
          { type: 'Feature', properties: { kind: 'end' },   geometry: { type: 'Point', coordinates: [lastCoord[1], lastCoord[0]] } },
        ],
      },
    })
    map.addLayer({
      id: 'endpoints',
      type: 'circle',
      source: 'endpoints',
      paint: {
        'circle-radius': 7,
        'circle-color': ['match', ['get', 'kind'], 'start', '#34d399', 'end', '#ff6b35', '#fff'],
        'circle-stroke-color': '#0b1018',
        'circle-stroke-width': 2,
      },
    })

    // Vehicle icon — top-down silhouette that flies along the track.
    // Heading is stored on the cursor feature and consumed by icon-rotate.
    const iconCanvas = vehicleIconCanvas(isPlane ? 'plane' : 'copter')
    if (!map.hasImage('vehicle-icon')) {
      const imgData = iconCanvas.getContext('2d').getImageData(0, 0, 64, 64)
      map.addImage('vehicle-icon', { width: 64, height: 64, data: new Uint8Array(imgData.data.buffer) })
    }

    // Cursor (playback marker)
    map.addSource('cursor', {
      type: 'geojson',
      data: { type: 'Feature', properties: { heading: 0 }, geometry: { type: 'Point', coordinates: [lng0, lat0] } },
    })
    // Soft glow halo so the icon stays visible on bright satellite tiles
    map.addLayer({
      id: 'cursor-glow',
      type: 'circle',
      source: 'cursor',
      paint: {
        'circle-radius': 22,
        'circle-color': isPlane ? '#5fbcff' : '#22d3ee',
        'circle-opacity': 0.20,
        'circle-blur':    1,
      },
    })
    // Vehicle icon, rotated by heading degrees (0 = nose right by our drawing)
    map.addLayer({
      id: 'cursor-icon',
      type: 'symbol',
      source: 'cursor',
      layout: {
        'icon-image': 'vehicle-icon',
        'icon-size': 0.85,
        'icon-rotate': ['get', 'heading'],
        'icon-rotation-alignment': 'map',
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
      },
    })

    // Frame the whole track
    const bounds = new maplibregl.LngLatBounds()
    for (const [lat, lng] of tr.coords) bounds.extend([lng, lat])
    map.fitBounds(bounds, { padding: 60, pitch: 62, duration: 1200 })

    loading.value = false
  })

  map.on('error', e => {
    if (e?.error?.message) errorMsg.value = 'Map error: ' + e.error.message
  })
}

// Cursor update — binary search the nearest track sample, push new point
function findNearestIdx(target) {
  const arr = track?.trel
  const n = arr?.length
  if (!n) return 0
  let lo = 0, hi = n - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (arr[mid] <= target) lo = mid
    else hi = mid - 1
  }
  if (lo + 1 < n && Math.abs(arr[lo + 1] - target) < Math.abs(arr[lo] - target)) return lo + 1
  return lo
}
function updateCursor() {
  if (!map || !track) return
  const src = map.getSource('cursor')
  if (!src) return
  const bi = findNearestIdx(playT.value)
  if (bi === lastBi) return
  lastBi = bi
  const [lat, lng] = track.coords[bi]
  // Heading from direction of travel (lat/lng deltas around bi).
  // We sample neighbors and convert to compass bearing (0 = north).
  const ni = Math.min(bi + 1, track.coords.length - 1)
  const pi = Math.max(bi - 1, 0)
  const [latN, lngN] = track.coords[ni]
  const [latP, lngP] = track.coords[pi]
  const dLat = latN - latP
  const dLng = (lngN - lngP) * Math.cos(lat * Math.PI / 180)
  // MapLibre icon-rotate is clockwise from "image up". Our drawing has
  // the nose pointing +X (east). Heading offset = atan2(dLng, dLat) gives
  // compass bearing from N; subtract 90° to convert to "from east" angle.
  let headingDeg = 0
  if (dLat !== 0 || dLng !== 0) {
    headingDeg = (Math.atan2(dLng, dLat) * 180 / Math.PI) - 90
  }
  src.setData({
    type: 'Feature',
    properties: { heading: headingDeg },
    geometry: { type: 'Point', coordinates: [lng, lat] },
  })
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

onMounted(() => render())
onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  if (map) { try { map.remove() } catch (_) {} map = null }
})
watch(() => props.parsed, () => { pause(); playT.value = 0; lastBi = -1; render() })
</script>

<template>
  <div class="terrain">
    <div class="title">TERRAIN · SATELLITE + 3D ELEVATION</div>
    <div class="canvas-wrap">
      <div ref="containerRef" class="canvas"></div>
      <div v-if="loading && !noTrack && !errorMsg" class="overlay">
        <div class="t">LOADING TERRAIN ENGINE…</div>
        <div class="s">Satellite imagery + DEM streaming · first load fetches ~2 MB.</div>
      </div>
      <div v-else-if="noTrack" class="overlay">
        <div class="t">NO TRACK</div>
        <div class="s">No valid POS/GPS coordinates found in this log.</div>
      </div>
      <div v-else-if="errorMsg" class="overlay error">
        <div class="t">MAP ERROR</div>
        <div class="s">{{ errorMsg }}</div>
      </div>
    </div>

    <TimelineStrip v-if="!noTrack && !loading" :parsed="parsed"
                   :play-t="playT" :duration="duration"
                   @seek="playT = $event"/>
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
.terrain { display: flex; flex-direction: column; gap: 10px; height: 100%; min-height: 0; }
.title {
  color: var(--text-mute);
  font-size: 11px; font-weight: 700; letter-spacing: 2px;
  padding: 0 2px 4px;
}
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
  background: var(--panel-from);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  padding: 24px 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  max-width: 80%;
}
.overlay.error { border-color: rgba(248,113,113,0.6); }
.overlay .t {
  font-size: 14px; letter-spacing: 4px; font-weight: 700;
  background: var(--grad-accent);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.overlay.error .t {
  background: none;
  -webkit-text-fill-color: var(--danger);
  color: var(--danger);
}
.overlay .s {
  color: var(--text-dim);
  font-size: 11px; margin-top: 10px;
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
.step {
  background: var(--surface-1);
  color: var(--text-2);
  border: 1px solid var(--border);
  padding: 7px 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 1px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color 160ms, border-color 160ms, background 160ms;
}
.step:hover { color: var(--accent-2); border-color: var(--accent); background: var(--accent-soft); }
.play {
  background: var(--grad-accent);
  color: #fff;
  border-color: transparent;
  font-weight: 700;
  min-width: 96px;
  box-shadow: 0 4px 16px rgba(61,169,252,0.35);
}
.play:hover { filter: brightness(1.1); box-shadow: 0 4px 22px rgba(61,169,252,0.55); }
.speed-group {
  display: flex; gap: 2px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  padding: 3px;
  border-radius: 999px;
}
.speed-btn {
  background: transparent; border: none;
  color: var(--text-dim);
  padding: 4px 10px;
  font-family: var(--font-mono);
  font-size: 10px;
  cursor: pointer;
  border-radius: 999px;
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
  border-radius: 999px;
}
.slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 14px; height: 14px; border-radius: 50%;
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

@media (max-width: 768px) {
  .scrub { flex-wrap: wrap; row-gap: 10px; padding: 10px 12px; }
  .slider { flex: 1 1 100%; order: 10; }
  .time   { flex: 1 1 100%; text-align: left; order: 11; font-size: 10px; min-width: 0; }
}
</style>
