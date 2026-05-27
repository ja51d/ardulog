<script setup>
// Comprehensive flight report — designed to look great on screen AND
// export cleanly to PNG / PDF. Pulls every useful signal we have:
// metrics, auto-review findings, alt/spd/batt charts, events, params.
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { detectFrameKind } from '../analyzers/frameKind.js'
import { extractTrack } from '../analyzers/extractTrack.js'
import { extractEvents } from '../analyzers/extractEvents.js'
import { autoReview } from '../analyzers/autoReview.js'

const props = defineProps({ parsed: Object })

const reportRef = ref(null)
const exporting = ref(false)
const exportLabel = ref('')

// ---- Computed data ----------------------------------------------------------

const meta = computed(() => {
  const p = props.parsed
  if (!p) return null
  return {
    frame:    detectFrameKind(p) || '—',
    duration: p.duration || 0,
    count:    p.count || 0,
    types:    Object.keys(p.data || {}).length,
    params:   Object.keys(p.params || {}).length,
    start:    p.t_start ? new Date(p.t_start * 1000) : null,
  }
})

const track = computed(() => props.parsed ? extractTrack(props.parsed) : null)

// Project the GPS track to a normalized 0..1 SVG coordinate space, so we
// can render a clean track preview right inside the report (no map tiles,
// no external network — keeps the export consistent + offline-friendly).
const trackSvg = computed(() => {
  const t = track.value
  if (!t?.coords?.length) return null
  const lats = t.coords.map(c => c[0])
  const lngs = t.coords.map(c => c[1])
  const lat0 = (Math.min(...lats) + Math.max(...lats)) / 2
  const cosLat = Math.cos(lat0 * Math.PI / 180)
  // Equirectangular projection in metres
  const xs = lngs.map(l => l * cosLat * 111320)
  const ys = lats.map(l => l * 111320)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const w = Math.max(maxX - minX, 1)
  const h = Math.max(maxY - minY, 1)
  // Fit to a 0..1000 × ~0..proportional viewBox with padding
  const PAD = 40, VW = 1000
  const aspect = h / w
  const VH = Math.min(560, Math.max(220, VW * aspect))
  const innerW = VW - PAD * 2
  const innerH = VH - PAD * 2
  const sx = innerW / w
  const sy = innerH / h
  const s = Math.min(sx, sy)
  const ox = PAD + (innerW - w * s) / 2
  const oy = PAD + (innerH - h * s) / 2
  const points = xs.map((x, i) => {
    const px = (x - minX) * s + ox
    // Flip Y so north is up
    const py = VH - ((ys[i] - minY) * s + oy)
    return [px, py]
  })
  // Color by altitude (cyan → orange) along the path
  const alts = t.alts
  const altMin = Math.min(...alts), altMax = Math.max(...alts)
  const altRange = Math.max(altMax - altMin, 1)
  return { vw: VW, vh: VH, points, alts, altMin, altMax, altRange }
})
const events = computed(() => props.parsed ? extractEvents(props.parsed) : [])
const review = computed(() => props.parsed ? autoReview(props.parsed) : [])

const reviewCounts = computed(() => {
  const c = { Good: 0, Marginal: 0, Bad: 0, Info: 0 }
  for (const r of review.value) if (c[r.verdict] != null) c[r.verdict]++
  return c
})

// Key flight stats
const stats = computed(() => {
  if (!props.parsed) return null
  const p = props.parsed
  const tr = track.value
  let altMin = null, altMax = null, altGain = null, dist = null
  if (tr?.alts?.length) {
    altMin = Math.min(...tr.alts); altMax = Math.max(...tr.alts)
    altGain = altMax - altMin
  }
  if (tr?.coords?.length) {
    let d = 0
    for (let i = 1; i < tr.coords.length; i++) {
      const [la1, ln1] = tr.coords[i - 1], [la2, ln2] = tr.coords[i]
      const dy = (la2 - la1) * 111320
      const dx = (ln2 - ln1) * 111320 * Math.cos(la1 * Math.PI / 180)
      d += Math.hypot(dx, dy)
    }
    dist = d
  }

  let battV = null, battSag = null, mAh = null
  const bat = p.data?.BAT || p.data?.CURR
  if (bat?.Volt || bat?.V) {
    const v = bat.Volt || bat.V
    let lo = Infinity, hi = -Infinity
    for (const x of v) { if (x < lo) lo = x; if (x > hi) hi = x }
    if (lo < Infinity) { battV = hi; battSag = hi - lo }
  }
  if (bat?.CurrTot || bat?.E) {
    const arr = bat.CurrTot || bat.E
    mAh = arr.length ? arr[arr.length - 1] : null
  }

  let gpsMin = null, gpsAvg = null, hdopMax = null
  const gps = p.data?.GPS
  if (gps?.NSats?.length) {
    let lo = Infinity, sum = 0, n = 0
    for (const v of gps.NSats) { if (v < lo) lo = v; sum += v; n++ }
    gpsMin = lo; gpsAvg = sum / n
  }
  if (gps?.HDop?.length) {
    let hi = -Infinity
    for (const v of gps.HDop) if (v > hi) hi = v
    hdopMax = hi
  }

  // Mode count
  let modes = 0
  const m = p.data?.MODE?.Mode
  if (m) {
    const uniq = []
    for (const v of m) if (uniq[uniq.length - 1] !== v) uniq.push(v)
    modes = uniq.length
  }

  // Peak speed (ARSP > CTUN > GPS)
  let peakSpd = null
  const arsp = p.data?.ARSP?.Airspeed || p.data?.ARSP?.Aspd
  if (arsp?.length) { peakSpd = Math.max(...arsp) }
  else if (p.data?.GPS?.Spd?.length) peakSpd = Math.max(...p.data.GPS.Spd)

  return { altMin, altMax, altGain, dist, battV, battSag, mAh, gpsMin, gpsAvg, hdopMax, modes, peakSpd }
})

// ---- Mini charts ------------------------------------------------------------

const altRef = ref(null)
const battRef = ref(null)
const attRef = ref(null)
let plots = []

function destroyPlots() {
  for (const p of plots) try { p.destroy() } catch (_) {}
  plots = []
}

const COMMON_AXES = (DIM, GRID) => [
  { stroke: DIM, grid: { stroke: GRID, width: 1 }, ticks: { stroke: GRID },
    values: (u, s) => s.map(v => v.toFixed(0) + 's') },
  { stroke: DIM, grid: { stroke: GRID, width: 1 }, ticks: { stroke: GRID } },
]

async function buildCharts() {
  await nextTick()
  destroyPlots()
  const DIM = '#7d8aa0', GRID = '#1f2733'
  const p = props.parsed
  if (!p) return

  // Altitude chart from POS.Alt
  if (altRef.value && p.data?.POS?.Alt?.length && p.times?.POS?.length) {
    const t0 = p.t_start || 0
    const trel = p.times.POS.map(t => t - t0)
    const alt = Array.from(p.data.POS.Alt)
    const a0 = alt[0] || 0
    const altRel = alt.map(v => v - a0)
    const w = altRef.value.clientWidth || 600
    plots.push(new uPlot({
      width: w, height: 160,
      axes: COMMON_AXES(DIM, GRID),
      cursor: { drag: { x: true, y: false } },
      scales: { x: { time: false } },
      legend: { show: true },
      series: [
        {},
        { label: 'Altitude (m AGL)', stroke: '#3da9fc', width: 1.6, fill: 'rgba(61,169,252,0.10)' },
      ],
    }, [trel, altRel], altRef.value))
  }

  // Battery chart (voltage)
  const bat = p.data?.BAT || p.data?.CURR
  const batT = p.times?.BAT || p.times?.CURR
  if (battRef.value && bat?.Volt && batT?.length) {
    const t0 = p.t_start || 0
    const trel = batT.map(t => t - t0)
    const w = battRef.value.clientWidth || 600
    plots.push(new uPlot({
      width: w, height: 160,
      axes: COMMON_AXES(DIM, GRID),
      cursor: { drag: { x: true, y: false } },
      scales: { x: { time: false } },
      legend: { show: true },
      series: [
        {},
        { label: 'Voltage (V)', stroke: '#34d399', width: 1.6, fill: 'rgba(52,211,153,0.10)' },
      ],
    }, [trel, Array.from(bat.Volt)], battRef.value))
  }

  // Attitude (roll + pitch)
  const att = p.data?.ATT
  const attT = p.times?.ATT
  if (attRef.value && att?.Roll && att?.Pitch && attT?.length) {
    const t0 = p.t_start || 0
    const trel = attT.map(t => t - t0)
    const w = attRef.value.clientWidth || 600
    plots.push(new uPlot({
      width: w, height: 180,
      axes: COMMON_AXES(DIM, GRID),
      cursor: { drag: { x: true, y: false } },
      scales: { x: { time: false } },
      legend: { show: true },
      series: [
        {},
        { label: 'Roll (°)',  stroke: '#3da9fc', width: 1.3 },
        { label: 'Pitch (°)', stroke: '#ff6b35', width: 1.3 },
      ],
    }, [trel, Array.from(att.Roll), Array.from(att.Pitch)], attRef.value))
  }
}

watch(() => props.parsed, () => { nextTick(buildCharts) })
onMounted(() => { nextTick(buildCharts) })

// Resize listener so charts fill new width on container changes
const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => {
  for (const p of plots) {
    const el = p?.root?.parentElement
    if (el) try { p.setSize({ width: el.clientWidth, height: p.height }) } catch (_) {}
  }
}) : null
onMounted(() => {
  if (!ro) return
  for (const el of [altRef.value, battRef.value, attRef.value]) if (el) ro.observe(el)
})

// ---- Export -----------------------------------------------------------------

async function exportPng() {
  await runExport(async (toPng) => {
    const dataUrl = await toPng(reportRef.value, {
      backgroundColor: '#0b1018',
      pixelRatio: 2,
      cacheBust: true,
      filter: node => !(node.classList && node.classList.contains('no-export')),
    })
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = `ardulog-report-${tsStamp()}.png`
    a.click()
  }, 'PNG')
}

async function exportPdf() {
  await runExport(async (toPng) => {
    const { jsPDF } = await import('jspdf')
    const dataUrl = await toPng(reportRef.value, {
      backgroundColor: '#0b1018',
      pixelRatio: 2,
      cacheBust: true,
      filter: node => !(node.classList && node.classList.contains('no-export')),
    })
    // Page = A4 portrait, mm. Slice the tall PNG into multiple pages.
    const pdf = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' })
    const pageW = pdf.internal.pageSize.getWidth()
    const pageH = pdf.internal.pageSize.getHeight()
    const img = new Image()
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = dataUrl })
    const imgW = img.width, imgH = img.height
    // Fit image width to page width
    const scale = pageW / imgW * 25.4 / 72 * 2.835    // px→mm via 72 DPI baseline
    // Simpler: compute mm height as proportional
    const totalH = imgH * (pageW / imgW)
    let y = 0, pageIdx = 0
    while (y < totalH) {
      if (pageIdx > 0) pdf.addPage()
      pdf.addImage(dataUrl, 'PNG', 0, -y, pageW, totalH, undefined, 'FAST')
      y += pageH
      pageIdx++
    }
    pdf.save(`ardulog-report-${tsStamp()}.pdf`)
  }, 'PDF')
}

async function runExport(fn, label) {
  if (exporting.value || !reportRef.value) return
  exporting.value = true
  exportLabel.value = `Generating ${label}…`
  try {
    const { toPng } = await import('html-to-image')
    await fn(toPng)
  } catch (e) {
    console.error('Export failed:', e)
    alert(`${label} export failed: ` + (e?.message || e))
  } finally {
    exporting.value = false
    exportLabel.value = ''
  }
}

function tsStamp() {
  return new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')
}

function fmt(v, d = 1, suffix = '') {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toFixed(d) + suffix
}
function fmtTime(s) {
  if (s == null || !Number.isFinite(s)) return '—'
  const sgn = s < 0 ? '-' : '+'
  return `${sgn}${Math.abs(s).toFixed(1)}s`
}
</script>

<template>
  <div class="report-tab">
    <!-- Export bar (hidden from the snapshot) -->
    <div class="export-bar no-export">
      <div class="export-title">FLIGHT REPORT</div>
      <div class="export-actions">
        <button class="export-btn" :disabled="exporting" @click="exportPng">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <circle cx="9" cy="9" r="1.5"/>
            <path d="m21 15-5-5L5 21"/>
          </svg>
          {{ exporting ? exportLabel : 'EXPORT PNG' }}
        </button>
        <button class="export-btn primary" :disabled="exporting" @click="exportPdf">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2 H6 a2 2 0 0 0 -2 2 v16 a2 2 0 0 0 2 2 h12 a2 2 0 0 0 2 -2 V8 z"/>
            <path d="M14 2 v6 h6"/>
          </svg>
          {{ exporting ? exportLabel : 'EXPORT PDF' }}
        </button>
      </div>
    </div>

    <!-- The actual report content -->
    <div ref="reportRef" class="report" v-if="meta">
      <!-- Cover / hero -->
      <div class="hero">
        <div class="hero-left">
          <img src="/favicon.svg" alt="ardulog" class="logo"/>
          <div class="brand">
            <div class="brand-name">ARDULOG</div>
            <div class="brand-sub">FLIGHT REPORT</div>
          </div>
        </div>
        <div class="hero-right">
          <div class="hero-stat">
            <div class="hero-stat-k">VEHICLE</div>
            <div class="hero-stat-v">{{ meta.frame }}</div>
          </div>
          <div class="hero-stat">
            <div class="hero-stat-k">DURATION</div>
            <div class="hero-stat-v">{{ fmt(meta.duration, 1, ' s') }}</div>
          </div>
          <div class="hero-stat" v-if="meta.start">
            <div class="hero-stat-k">START · UTC</div>
            <div class="hero-stat-v small">{{ meta.start.toISOString().slice(0, 16).replace('T', ' ') }}</div>
          </div>
        </div>
      </div>

      <!-- Top metrics grid -->
      <div class="grid grid-4" v-if="stats">
        <div class="metric">
          <div class="m-k">DISTANCE</div>
          <div class="m-v">{{ stats.dist != null ? (stats.dist/1000).toFixed(2) : '—' }} <span class="unit">km</span></div>
        </div>
        <div class="metric">
          <div class="m-k">ALT GAIN</div>
          <div class="m-v">{{ fmt(stats.altGain, 0) }} <span class="unit">m</span></div>
        </div>
        <div class="metric">
          <div class="m-k">PEAK SPEED</div>
          <div class="m-v">{{ fmt(stats.peakSpd, 1) }} <span class="unit">m/s</span></div>
        </div>
        <div class="metric">
          <div class="m-k">MODES</div>
          <div class="m-v">{{ stats.modes || '—' }}</div>
        </div>
        <div class="metric">
          <div class="m-k">PEAK BATTERY</div>
          <div class="m-v">{{ fmt(stats.battV, 2) }} <span class="unit">V</span></div>
        </div>
        <div class="metric">
          <div class="m-k">BATTERY SAG</div>
          <div class="m-v">{{ fmt(stats.battSag, 2) }} <span class="unit">V</span></div>
        </div>
        <div class="metric">
          <div class="m-k">ENERGY USED</div>
          <div class="m-v">{{ fmt(stats.mAh, 0) }} <span class="unit">mAh</span></div>
        </div>
        <div class="metric">
          <div class="m-k">GPS · AVG SATS</div>
          <div class="m-v">{{ fmt(stats.gpsAvg, 1) }}<span class="unit" v-if="stats.gpsMin != null"> · min {{ stats.gpsMin }}</span></div>
        </div>
      </div>

      <!-- Auto-review summary -->
      <div class="section" v-if="review.length">
        <div class="section-title">FLIGHT HEALTH · AUTO-REVIEW</div>
        <div class="review-summary">
          <div class="chip chip-good">    <span class="num">{{ reviewCounts.Good }}</span>     <span class="lab">GOOD</span></div>
          <div class="chip chip-marginal"><span class="num">{{ reviewCounts.Marginal }}</span> <span class="lab">MARGINAL</span></div>
          <div class="chip chip-bad">     <span class="num">{{ reviewCounts.Bad }}</span>      <span class="lab">BAD</span></div>
          <div class="chip chip-info">    <span class="num">{{ reviewCounts.Info }}</span>     <span class="lab">INFO</span></div>
        </div>
        <div class="findings">
          <div v-for="(f, i) in review" :key="i" class="finding" :class="'verdict-' + (f.verdict || 'info').toLowerCase()">
            <div class="finding-head">
              <span class="finding-cat">{{ f.category }}</span>
              <span class="finding-verdict">{{ f.verdict }}</span>
            </div>
            <div class="finding-text" v-html="f.detail || f.headline"></div>
          </div>
        </div>
      </div>

      <!-- Track preview -->
      <div class="section" v-if="trackSvg">
        <div class="section-title">FLIGHT TRACK · ALTITUDE-COLOURED</div>
        <div class="chart-wrap">
          <svg :viewBox="`0 0 ${trackSvg.vw} ${trackSvg.vh}`" class="track-svg" preserveAspectRatio="xMidYMid meet">
            <defs>
              <linearGradient id="tg" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0"   stop-color="#3da9fc"/>
                <stop offset="0.4" stop-color="#6aa9e8"/>
                <stop offset="0.75" stop-color="#f0b75d"/>
                <stop offset="1"   stop-color="#ff6b35"/>
              </linearGradient>
            </defs>
            <!-- Subtle grid -->
            <g stroke="#1f2733" stroke-width="0.8">
              <line v-for="g in 11" :key="'gx' + g" :x1="(g - 1) / 10 * trackSvg.vw" y1="0" :x2="(g - 1) / 10 * trackSvg.vw" :y2="trackSvg.vh"/>
              <line v-for="g in 7"  :key="'gy' + g" x1="0" :y1="(g - 1) / 6 * trackSvg.vh" :x2="trackSvg.vw" :y2="(g - 1) / 6 * trackSvg.vh"/>
            </g>
            <!-- Glow under the path -->
            <polyline
              :points="trackSvg.points.map(p => p.join(',')).join(' ')"
              fill="none" stroke="#3da9fc" stroke-opacity="0.18"
              stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>
            <!-- Main track -->
            <polyline
              :points="trackSvg.points.map(p => p.join(',')).join(' ')"
              fill="none" stroke="url(#tg)"
              stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
            <!-- Start (green) -->
            <circle :cx="trackSvg.points[0][0]" :cy="trackSvg.points[0][1]" r="9" fill="#34d399" stroke="#0b1018" stroke-width="2.5"/>
            <text :x="trackSvg.points[0][0] + 14" :y="trackSvg.points[0][1] + 4" fill="#34d399" font-family="JetBrains Mono, monospace" font-size="14" font-weight="700">START</text>
            <!-- End (orange) -->
            <circle :cx="trackSvg.points[trackSvg.points.length - 1][0]" :cy="trackSvg.points[trackSvg.points.length - 1][1]" r="9" fill="#ff6b35" stroke="#0b1018" stroke-width="2.5"/>
            <text :x="trackSvg.points[trackSvg.points.length - 1][0] + 14" :y="trackSvg.points[trackSvg.points.length - 1][1] + 4" fill="#ff6b35" font-family="JetBrains Mono, monospace" font-size="14" font-weight="700">END</text>
            <!-- Altitude legend -->
            <g :transform="`translate(${trackSvg.vw - 200}, ${trackSvg.vh - 36})`">
              <rect x="0" y="0" width="180" height="12" fill="url(#tg)" rx="6"/>
              <text x="0"   y="28" fill="#9aa6b8" font-family="JetBrains Mono, monospace" font-size="11">{{ trackSvg.altMin.toFixed(0) }} m</text>
              <text x="180" y="28" fill="#9aa6b8" font-family="JetBrains Mono, monospace" font-size="11" text-anchor="end">{{ trackSvg.altMax.toFixed(0) }} m</text>
            </g>
          </svg>
        </div>
      </div>

      <!-- Charts -->
      <div class="section">
        <div class="section-title">ALTITUDE PROFILE</div>
        <div class="chart-wrap"><div ref="altRef" class="chart"></div></div>
      </div>

      <div class="section" v-if="parsed?.data?.ATT">
        <div class="section-title">ATTITUDE · ROLL &amp; PITCH</div>
        <div class="chart-wrap"><div ref="attRef" class="chart"></div></div>
      </div>

      <div class="section" v-if="parsed?.data?.BAT || parsed?.data?.CURR">
        <div class="section-title">BATTERY VOLTAGE</div>
        <div class="chart-wrap"><div ref="battRef" class="chart"></div></div>
      </div>

      <!-- Events timeline -->
      <div class="section" v-if="events.length">
        <div class="section-title">FLIGHT EVENTS · {{ events.length }} TOTAL</div>
        <div class="events">
          <div v-for="(e, i) in events" :key="i" class="event">
            <span class="event-dot" :style="{ background: e.color }"></span>
            <span class="event-time">{{ fmtTime(e.t) }}</span>
            <span class="event-kind">{{ e.kind.toUpperCase() }}</span>
            <span class="event-label">{{ e.label }}</span>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="footer">
        <span>GENERATED BY <a href="https://ardulog.app">ardulog.app</a></span>
        <span class="dot">·</span>
        <span>{{ new Date().toLocaleString() }}</span>
      </div>
    </div>

    <div class="empty" v-else>
      <div class="empty-t">NO LOG LOADED</div>
      <div class="empty-s">Load a flight log to generate a report.</div>
    </div>
  </div>
</template>

<style scoped>
.report-tab { display: flex; flex-direction: column; gap: 14px; }
.export-bar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px;
  padding: 10px 14px;
  background: linear-gradient(180deg, var(--panel-from), var(--panel-to));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.export-title { font-weight: 700; letter-spacing: 2.5px; font-size: 12px; color: var(--text); }
.export-actions { display: flex; gap: 8px; }
.export-btn {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  color: var(--text-2);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 1.5px;
  padding: 8px 14px;
  border-radius: 999px;
  cursor: pointer;
  transition: color 160ms, border-color 160ms, background 160ms, transform 160ms;
}
.export-btn:hover:not(:disabled) {
  color: var(--accent-2);
  border-color: var(--accent);
  background: var(--accent-soft);
  transform: translateY(-1px);
}
.export-btn.primary {
  background: var(--grad-accent);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 4px 14px rgba(61,169,252,0.30);
}
.export-btn.primary:hover:not(:disabled) {
  filter: brightness(1.1);
  box-shadow: 0 4px 22px rgba(61,169,252,0.55);
}
.export-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ---- Report ---- */
.report {
  background: linear-gradient(180deg, #0e1320 0%, #0a0f1a 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 28px 30px 24px;
  display: flex;
  flex-direction: column;
  gap: 22px;
  box-shadow: var(--shadow-soft);
}

/* Hero */
.hero {
  display: flex; align-items: center; justify-content: space-between;
  gap: 22px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border);
}
.hero-left { display: flex; align-items: center; gap: 16px; }
.hero-left .logo { width: 56px; height: 56px; filter: drop-shadow(0 0 12px rgba(61,169,252,0.4)); }
.brand-name { font-size: 22px; letter-spacing: 4px; font-weight: 800; background: var(--grad-accent); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.brand-sub { color: var(--text-mute); font-family: var(--font-mono); font-size: 11px; letter-spacing: 3px; margin-top: 2px; }
.hero-right { display: flex; gap: 22px; flex-wrap: wrap; }
.hero-stat { text-align: right; }
.hero-stat-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: 2px; color: var(--text-mute); }
.hero-stat-v { font-family: var(--font-mono); font-size: 18px; font-weight: 700; color: var(--text); margin-top: 3px; letter-spacing: 0.5px; }
.hero-stat-v.small { font-size: 13px; }

/* Metrics grid */
.grid { display: grid; gap: 10px; }
.grid-4 { grid-template-columns: repeat(4, 1fr); }
.metric {
  position: relative;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  overflow: hidden;
}
.metric::after { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--grad-accent); opacity: 0.6; }
.m-k { color: var(--text-mute); font-family: var(--font-mono); font-size: 9px; letter-spacing: 2px; font-weight: 700; }
.m-v { color: var(--text); font-family: var(--font-mono); font-size: 19px; font-weight: 700; margin-top: 5px; }
.m-v .unit { color: var(--text-mute); font-size: 12px; margin-left: 4px; font-weight: 500; }

/* Sections */
.section { display: flex; flex-direction: column; gap: 10px; }
.section-title {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 2.5px;
  color: var(--text-mute);
  font-weight: 700;
  padding-left: 10px;
  border-left: 3px solid var(--accent);
}

/* Review */
.review-summary { display: flex; gap: 8px; flex-wrap: wrap; }
.chip {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 14px;
  border-radius: 999px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 1.5px;
}
.chip .num { font-size: 14px; font-weight: 800; }
.chip .lab { color: var(--text-mute); font-size: 9px; letter-spacing: 2px; }
.chip-good     { color: #34d399; border-color: rgba(52,211,153,0.40); }
.chip-marginal { color: #facc15; border-color: rgba(250,204,21,0.40); }
.chip-bad      { color: #f87171; border-color: rgba(248,113,113,0.40); }
.chip-info     { color: #9aa6b8; }

.findings { display: flex; flex-direction: column; gap: 8px; }
.finding {
  position: relative;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 14px 12px 18px;
  overflow: hidden;
}
.finding::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #9aa6b8; }
.finding.verdict-good::before     { background: #34d399; }
.finding.verdict-marginal::before { background: #facc15; }
.finding.verdict-bad::before      { background: #f87171; }
.finding-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 4px; }
.finding-cat { color: var(--text); font-weight: 700; font-size: 12px; letter-spacing: 0.5px; }
.finding-verdict { color: var(--text-mute); font-family: var(--font-mono); font-size: 9px; letter-spacing: 1.5px; }
.finding-text { color: var(--text-2); font-size: 12px; line-height: 1.5; }
.finding-text :deep(b) { color: var(--text); }

/* Charts */
.chart-wrap {
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px;
}
.chart { width: 100%; min-height: 160px; }
.track-svg { width: 100%; height: auto; max-height: 480px; display: block; background: #0b1018; border-radius: 4px; }

/* Events */
.events { display: flex; flex-direction: column; gap: 4px; max-height: 360px; overflow-y: auto; padding-right: 4px; }
.event {
  display: grid;
  grid-template-columns: 12px 64px 90px 1fr;
  align-items: center;
  gap: 10px;
  padding: 4px 8px;
  font-size: 12px;
  border-radius: 4px;
}
.event:hover { background: var(--surface-1); }
.event-dot { width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 6px currentColor; }
.event-time { color: var(--text-mute); font-family: var(--font-mono); font-size: 10px; }
.event-kind { color: var(--text); font-family: var(--font-mono); font-size: 9px; letter-spacing: 1.5px; font-weight: 700; }
.event-label { color: var(--text-2); font-family: var(--font-mono); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Footer */
.footer {
  display: flex; align-items: center; justify-content: center;
  gap: 8px;
  margin-top: 6px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-mute);
  letter-spacing: 1.5px;
}
.footer a { color: var(--accent-2); text-decoration: none; }
.footer .dot { opacity: 0.5; }

/* Empty */
.empty { padding: 60px; text-align: center; }
.empty-t { font-size: 16px; letter-spacing: 4px; font-weight: 700; color: var(--text-dim); }
.empty-s { color: var(--text-mute); margin-top: 10px; font-family: var(--font-mono); font-size: 12px; }

/* ---- Responsive ---- */
@media (max-width: 900px) {
  .grid-4 { grid-template-columns: repeat(2, 1fr); }
  .hero { flex-direction: column; align-items: flex-start; gap: 14px; }
  .hero-right { gap: 16px; }
  .hero-stat { text-align: left; }
  .report { padding: 20px; }
}
@media (max-width: 480px) {
  .grid-4 { grid-template-columns: 1fr; }
  .event { grid-template-columns: 8px 56px 1fr; }
  .event-kind { display: none; }
}
</style>
