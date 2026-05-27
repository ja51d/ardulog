<script setup>
import { onMounted, onBeforeUnmount, watch, ref } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { extractTrack } from '../analyzers/extractTrack.js'
import { extractMission } from '../analyzers/extractMission.js'
import { extractFence } from '../analyzers/extractFence.js'

const props = defineProps({ parsed: Object })
const containerRef = ref(null)
const noTrack = ref(false)
let map = null
let layer = null

function renderTrack() {
  if (!map) return
  if (layer) { map.removeLayer(layer); layer = null }
  const { coords } = extractTrack(props.parsed)
  if (!coords.length) { noTrack.value = true; return }
  noTrack.value = false
  layer = L.layerGroup()
  const line = L.polyline(coords, { color: '#4a90e2', weight: 3, opacity: 0.9 })
  layer.addLayer(line)
  // Start (green) + end (amber) markers
  const startIcon = L.divIcon({
    className: 'wp-marker',
    html: '<div class="dot start"></div>',
    iconSize: [16, 16], iconAnchor: [8, 8],
  })
  const endIcon = L.divIcon({
    className: 'wp-marker',
    html: '<div class="dot end"></div>',
    iconSize: [16, 16], iconAnchor: [8, 8],
  })
  layer.addLayer(L.marker(coords[0], { icon: startIcon }).bindTooltip('START'))
  layer.addLayer(L.marker(coords[coords.length - 1], { icon: endIcon }).bindTooltip('END'))

  // Mission waypoints — dashed line connecting them + numbered markers
  const mission = extractMission(props.parsed)
  if (mission.waypoints.length) {
    const wpCoords = mission.waypoints.map(w => [w.lat, w.lng])
    // Dashed planned-path polyline
    const planLine = L.polyline(wpCoords, {
      color: '#f0b75d', weight: 2.5, opacity: 0.85, dashArray: '6 6',
    }).bindTooltip('PLANNED MISSION', { permanent: false, sticky: true })
    layer.addLayer(planLine)
    // Numbered waypoint markers
    for (const w of mission.waypoints) {
      const icon = L.divIcon({
        className: 'wp-marker',
        html: `<div class="dot wp"><span class="num">${w.idx}</span></div>`,
        iconSize: [22, 22], iconAnchor: [11, 11],
      })
      layer.addLayer(L.marker([w.lat, w.lng], { icon })
        .bindTooltip(`${w.label} · #${w.idx}<br><span style="color:#7d8aa0">alt ${w.alt.toFixed(1)} m</span>`, { sticky: true }))
    }
  }
  // Geofence — inclusion polygons in green, exclusion in red, circles too
  const fence = extractFence(props.parsed)
  for (const poly of fence.polygons) {
    if (poly.points.length < 3) continue
    const isExclude = poly.kind === 'exclusion'
    const color = isExclude ? '#f87171' : '#34d399'
    const ring = L.polygon(poly.points, {
      color,
      weight: 2,
      opacity: 0.85,
      fillColor: color,
      fillOpacity: isExclude ? 0.18 : 0.06,
      dashArray: isExclude ? '8 6' : null,
    }).bindTooltip(isExclude ? 'EXCLUSION ZONE' : 'INCLUSION FENCE', { sticky: true })
    layer.addLayer(ring)
  }
  for (const c of fence.circles) {
    const isExclude = c.kind === 'exclusion'
    const color = isExclude ? '#f87171' : '#34d399'
    layer.addLayer(L.circle([c.lat, c.lng], {
      radius: c.radius,
      color, weight: 2, opacity: 0.85,
      fillColor: color, fillOpacity: isExclude ? 0.18 : 0.06,
      dashArray: isExclude ? '8 6' : null,
    }).bindTooltip(`${isExclude ? 'EXCLUSION' : 'INCLUSION'} CIRCLE · ${c.radius.toFixed(0)} m`, { sticky: true }))
  }

  if (mission.home) {
    const icon = L.divIcon({
      className: 'wp-marker',
      html: `<div class="dot home">H</div>`,
      iconSize: [22, 22], iconAnchor: [11, 11],
    })
    layer.addLayer(L.marker([mission.home.lat, mission.home.lng], { icon }).bindTooltip('HOME'))
  }

  layer.addTo(map)
  map.fitBounds(line.getBounds(), { padding: [40, 40] })
}

onMounted(() => {
  map = L.map(containerRef.value, {
    zoomControl: true,
    attributionControl: true,
  })
  // Satellite imagery (Esri World Imagery — free, no API key required)
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19,
    attribution: '© Esri · Maxar · Earthstar Geographics',
  }).addTo(map)
  // Thin label overlay so place names stay readable on top of imagery
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    subdomains: 'abcd',
    attribution: '© CARTO',
    opacity: 0.8,
  }).addTo(map)
  map.setView([0, 0], 2)
  renderTrack()
})
onBeforeUnmount(() => { if (map) map.remove(); map = null })
watch(() => props.parsed, renderTrack)
</script>

<template>
  <div class="wrap">
    <div ref="containerRef" class="map" :class="{ empty: noTrack }"></div>
    <div v-if="noTrack" class="empty-msg">
      <div class="title">NO TRACK</div>
      <div class="sub">No valid POS/GPS coordinates found in this log.</div>
    </div>
  </div>
</template>

<style scoped>
.wrap { position: relative; height: 100%; min-height: 0; }
.map {
  width: 100%; height: 100%;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-soft);
  overflow: hidden;
}
.empty-msg {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  padding: 26px 38px;
  background: var(--panel-from);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  pointer-events: none;
}
.empty-msg .title {
  font-size: 14px;
  letter-spacing: 4px;
  font-weight: 700;
  background: var(--grad-accent);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.empty-msg .sub {
  color: var(--text-dim);
  font-size: 11px;
  margin-top: 10px;
  font-family: var(--font-mono);
}
</style>

<style>
/* Global (not scoped) so Leaflet's internal classes can be styled. */
.wp-marker .dot {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid var(--bg-0);
  box-shadow: 0 0 0 1px var(--border);
}
.wp-marker .dot.start { background: #5dba7c; }
.wp-marker .dot.end   { background: #d9a14a; }
.wp-marker .dot.wp {
  width: 22px; height: 22px;
  background: #f0b75d;
  border: 2px solid #0b1018;
  display: flex; align-items: center; justify-content: center;
  color: #0b1018;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 800;
  box-shadow: 0 0 0 1px #f0b75d, 0 0 8px rgba(240,183,93,0.6);
}
.wp-marker .dot.home {
  width: 22px; height: 22px;
  background: #34d399;
  border: 2px solid #0b1018;
  display: flex; align-items: center; justify-content: center;
  color: #0b1018;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 900;
  box-shadow: 0 0 0 1px #34d399, 0 0 10px rgba(52,211,153,0.7);
}
.leaflet-container { background: var(--bg-1); }
.leaflet-control-attribution {
  background: rgba(38, 45, 56, 0.85) !important;
  color: var(--text-dim) !important;
  font-family: var(--font-mono);
  font-size: 9px !important;
}
.leaflet-control-attribution a { color: var(--accent) !important; }
.leaflet-tooltip {
  background: var(--bg-2) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  font-family: var(--font-mono);
  font-size: 10px !important;
  letter-spacing: 1.5px;
  font-weight: 700;
  box-shadow: none !important;
}
.leaflet-tooltip-top:before,
.leaflet-tooltip-bottom:before,
.leaflet-tooltip-left:before,
.leaflet-tooltip-right:before { display: none !important; }
.leaflet-bar a {
  background: var(--bg-2) !important;
  color: var(--text) !important;
  border-color: var(--border) !important;
}
.leaflet-bar a:hover { background: var(--bg-3) !important; color: var(--accent) !important; }
</style>
