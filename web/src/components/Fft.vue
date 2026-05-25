<script setup>
// Vibration spectrum — FFT of IMU acceleration on each axis.
// Mirrors the desktop FFT tab: three panels showing accel X / Y / Z
// magnitude vs frequency, plus a peak frequency readout.
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import FFT from 'fft.js'
import { median } from '../analyzers/helpers.js'

const props = defineProps({ parsed: Object })
const DIM = '#7a8699'

const xRef = ref(null), yRef = ref(null), zRef = ref(null)
const plots = { x: null, y: null, z: null }
const fs = ref(null), peakHz = ref({ x: 0, y: 0, z: 0 })
const imuSource = ref(null)

// Compute FFT magnitude in dB for one axis. Uses next-pow-of-2 size and
// a Hann window. Returns { freqs: [Hz...], mags: [dB...], fs }.
function computeFft(signal, sampleHz) {
  if (!signal?.length || !sampleHz) return null
  // Find next power of two ≥ length, cap at 16384 for browser performance
  let N = 1
  while (N < signal.length && N < 16384) N <<= 1
  if (N > signal.length) {
    // Truncate / pad: just use the latest 2^k samples (no zero-pad bias)
    N = 1
    while (N * 2 <= signal.length && N * 2 <= 16384) N <<= 1
  }
  if (N < 64) return null
  // Take the trailing N samples and Hann-window them
  const start = signal.length - N
  const buf = new Float64Array(N)
  for (let i = 0; i < N; i++) {
    const v = signal[start + i]
    const w = 0.5 * (1 - Math.cos(2 * Math.PI * i / (N - 1))) // Hann
    buf[i] = Number.isFinite(v) ? v * w : 0
  }
  // Remove DC
  let mean = 0
  for (let i = 0; i < N; i++) mean += buf[i]
  mean /= N
  for (let i = 0; i < N; i++) buf[i] -= mean

  const fft = new FFT(N)
  const out = fft.createComplexArray()
  fft.realTransform(out, buf)
  fft.completeSpectrum(out)

  const bins = N / 2
  const freqs = new Float64Array(bins)
  const mags  = new Float64Array(bins)
  for (let k = 0; k < bins; k++) {
    const re = out[k * 2], im = out[k * 2 + 1]
    const m = Math.sqrt(re * re + im * im) / N
    freqs[k] = k * sampleHz / N
    mags[k]  = 20 * Math.log10(Math.max(1e-9, m))
  }
  return { freqs, mags, fs: sampleHz }
}

const errorMsg = ref('')

// Find the best IMU-like message in the parsed log. ArduPilot historically
// has used IMU, IMU0, IMU1, IMU2, IMU3, IMT — we accept any of them.
function pickImu(parsed) {
  if (!parsed?.data) return { name: null, imu: null, times: null }
  const candidates = ['IMU', 'IMU0', 'IMU1', 'IMU2', 'IMU3']
  for (const name of candidates) {
    const imu = parsed.data[name]
    const t = parsed.times[name]
    if (imu && t?.length && imu.AccX) return { name, imu, times: t }
  }
  return { name: null, imu: null, times: null }
}

// Check what's available in the log up-front. This runs even if the
// canvases aren't laid out yet, so the banner shows a useful diagnostic.
function checkData() {
  const { name, imu, times: t } = pickImu(props.parsed)
  if (!imu || !t?.length) {
    const allTypes = Object.keys(props.parsed?.data || {})
    const imuish = allTypes.filter(k => /^(IMU|IMT|INS|RAW_IMU)/i.test(k))
    errorMsg.value = imuish.length
      ? `Found ${imuish.join(', ')} but no Acc{X,Y,Z} fields. ` +
        `Sample fields in ${imuish[0]}: ${Object.keys(props.parsed.data[imuish[0]] || {}).slice(0, 12).join(', ')}.`
      : `No IMU messages in this log. Top message types: ${allTypes.slice(0, 10).join(', ')}.`
    return null
  }
  imuSource.value = name
  return { imu, t }
}

function buildOne(axis, refEl, color) {
  if (!refEl) return false
  const rect = refEl.getBoundingClientRect()
  if (rect.width < 100) return false  // canvas not laid out yet — observer retries
  if (plots[axis]) { plots[axis].destroy(); plots[axis] = null }
  const picked = checkData()
  if (!picked) return true
  const { imu, t } = picked
  // Estimate sample rate from median delta-t
  const dts = []
  for (let i = 1; i < Math.min(200, t.length); i++) dts.push(t[i] - t[i-1])
  const dt = median(dts)
  if (!dt || dt <= 0) return
  const sampleHz = 1 / dt
  fs.value = sampleHz
  const key = { x: 'AccX', y: 'AccY', z: 'AccZ' }[axis]
  const sig = imu[key] || []
  if (!sig.length) { errorMsg.value = `IMU.${key} not present in this log.`; return true }
  const sp = computeFft(sig, sampleHz)
  if (!sp) { errorMsg.value = `Too few IMU samples for FFT (need ≥ 64).`; return true }
  // Find peak frequency (ignore DC / sub-2 Hz noise)
  let bi = 0, bv = -Infinity
  for (let i = 0; i < sp.freqs.length; i++) {
    if (sp.freqs[i] < 2) continue
    if (sp.mags[i] > bv) { bv = sp.mags[i]; bi = i }
  }
  peakHz.value[axis] = sp.freqs[bi]

  plots[axis] = new uPlot({
    width: Math.max(400, rect.width),
    height: Math.max(140, rect.height),
    series: [{},
      { label: `Acc${axis.toUpperCase()} magnitude (dB)`, stroke: color, width: 1.2, points: { show: false } }],
    axes: [
      { stroke: DIM, grid: { stroke: '#323a47', width: 1 }, ticks: { stroke: '#323a47' },
        values: (u, s) => s.map(v => v.toFixed(0) + ' Hz') },
      { stroke: DIM, grid: { stroke: '#323a47', width: 1 }, ticks: { stroke: '#323a47' },
        label: 'dB' },
    ],
    legend: { show: true },
    cursor: { drag: { x: true, y: false } },
    scales: { x: { range: [0, sampleHz / 2] } },
  }, [Array.from(sp.freqs), Array.from(sp.mags)], refEl)
  return true
}

function buildAll() {
  errorMsg.value = ''
  // Run the data check first so the banner has a diagnostic even before
  // (or if) the canvases get sized.
  checkData()
  buildOne('x', xRef.value, '#4a90e2')
  buildOne('y', yRef.value, '#d9a14a')
  buildOne('z', zRef.value, '#5dba7c')
}

// uPlot can render at 0×0 if the flex container hasn't sized yet on the
// initial mount. ResizeObserver catches the layout pass and rebuilds any
// pane that hasn't been drawn yet once its canvas has real pixels.
let ro = null
function setupResizeObserver() {
  if (typeof ResizeObserver === 'undefined') return
  ro = new ResizeObserver(() => {
    handleResize()
    // Retry any axis that hasn't been plotted yet — buildOne refuses to
    // create at <100 px wide, so it can come back as a no-op on first
    // mount and needs to fire again once flex is settled.
    if (!plots.x) buildOne('x', xRef.value, '#4a90e2')
    if (!plots.y) buildOne('y', yRef.value, '#d9a14a')
    if (!plots.z) buildOne('z', zRef.value, '#5dba7c')
  })
  for (const el of [xRef.value, yRef.value, zRef.value]) if (el) ro.observe(el)
}
function handleResize() {
  for (const axis of ['x', 'y', 'z']) {
    const el = { x: xRef.value, y: yRef.value, z: zRef.value }[axis]
    if (plots[axis] && el) {
      const r = el.getBoundingClientRect()
      plots[axis].setSize({ width: Math.max(400, r.width), height: Math.max(140, r.height) })
    }
  }
}
onMounted(() => {
  nextTick(() => { buildAll(); setupResizeObserver() })
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (ro) { ro.disconnect(); ro = null }
  for (const k of Object.keys(plots)) if (plots[k]) plots[k].destroy()
})
watch(() => props.parsed, () => nextTick(buildAll))
</script>

<template>
  <div class="fft">
    <div class="title">FFT · IMU ACCELERATION SPECTRUM PER AXIS</div>
    <div class="banner">
      <div v-if="errorMsg" class="err">{{ errorMsg }}</div>
      <div v-else-if="fs">Source: <b>{{ imuSource }}</b> · Sample rate: <b>{{ fs.toFixed(0) }} Hz</b> (Nyquist {{ (fs/2).toFixed(0) }} Hz)</div>
      <div v-else>Open a log with IMU messages to see motor / airframe resonance peaks.</div>
      <div class="hint">Peaks near motor RPM/60 = resonance. Broad shoulders = airframe flex.</div>
    </div>

    <div class="panes">
      <div class="pane">
        <div class="pane-label">ACC X<span class="peak"> · peak {{ peakHz.x.toFixed(1) }} Hz</span></div>
        <div ref="xRef" class="pane-canvas"></div>
      </div>
      <div class="pane">
        <div class="pane-label">ACC Y<span class="peak"> · peak {{ peakHz.y.toFixed(1) }} Hz</span></div>
        <div ref="yRef" class="pane-canvas"></div>
      </div>
      <div class="pane">
        <div class="pane-label">ACC Z<span class="peak"> · peak {{ peakHz.z.toFixed(1) }} Hz</span></div>
        <div ref="zRef" class="pane-canvas"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fft { display: flex; flex-direction: column; gap: 10px; height: 100%; min-height: 0; }
.title { color: var(--text-dim); font-size: 11px; font-weight: 700; letter-spacing: 2px; padding: 0 2px 4px; }
.banner {
  background: var(--bg-1);
  border: 1px solid var(--border);
  padding: 8px 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text);
}
.banner b { color: var(--accent); }
.banner .err { color: var(--danger); font-family: var(--font-mono); }
.banner .hint { color: var(--text-dim); font-size: 11px; margin-top: 4px; font-family: var(--font-ui); }
.panes { flex: 1; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.pane { flex: 1; min-height: 180px; display: flex; flex-direction: column; }
.pane-label { color: var(--text-dim); font-size: 9px; letter-spacing: 2px; font-weight: 700; padding: 0 4px 2px; }
.pane-label .peak { color: var(--accent); font-family: var(--font-mono); margin-left: 8px; }
.pane-canvas { flex: 1; min-height: 150px; border: 1px solid var(--border); background: var(--bg-1); }
</style>
