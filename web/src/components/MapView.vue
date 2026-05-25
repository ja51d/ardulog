<script setup>
import { onMounted, onBeforeUnmount, watch, ref } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { extractTrack } from '../analyzers/extractTrack.js'

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
  layer.addTo(map)
  map.fitBounds(line.getBounds(), { padding: [40, 40] })
}

onMounted(() => {
  map = L.map(containerRef.value, {
    zoomControl: true,
    attributionControl: true,
  })
  // Dark tile layer (Carto Dark Matter — free, attribution required)
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    subdomains: 'abcd',
    attribution: '© OpenStreetMap contributors © CARTO',
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
}
.empty-msg {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  pointer-events: none;
}
.empty-msg .title {
  color: var(--text-dim);
  font-size: 14px;
  letter-spacing: 4px;
  font-weight: 700;
}
.empty-msg .sub {
  color: var(--text-dim);
  font-size: 11px;
  margin-top: 8px;
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
