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

function buildOne(axis, refEl, color) {
  if (!refEl) return
  if (plots[axis]) { plots[axis].destroy(); plots[axis] = null }
  const imu = props.parsed?.data?.IMU
  const t = props.parsed?.times?.IMU
  if (!imu || !t?.length) return
  // Estimate sample rate from median delta-t
  const dts = []
  for (let i = 1; i < Math.min(200, t.length); i++) dts.push(t[i] - t[i-1])
  const dt = median(dts)
  if (!dt || dt <= 0) return
  const sampleHz = 1 / dt
  fs.value = sampleHz
  const key = { x: 'AccX', y: 'AccY', z: 'AccZ' }[axis]
  const sig = imu[key] || []
  if (!sig.length) return
  const sp = computeFft(sig, sampleHz)
  if (!sp) return
  // Find peak frequency (ignore DC / sub-2 Hz noise)
  let bi = 0, bv = -Infinity
  for (let i = 0; i < sp.freqs.length; i++) {
    if (sp.freqs[i] < 2) continue
    if (sp.mags[i] > bv) { bv = sp.mags[i]; bi = i }
  }
  peakHz.value[axis] = sp.freqs[bi]

  const rect = refEl.getBoundingClientRect()
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
}

function buildAll() {
  buildOne('x', xRef.value, '#4a90e2')
  buildOne('y', yRef.value, '#d9a14a')
  buildOne('z', zRef.value, '#5dba7c')
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
onMounted(() => { nextTick(buildAll); window.addEventListener('resize', handleResize) })
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  for (const k of Object.keys(plots)) if (plots[k]) plots[k].destroy()
})
watch(() => props.parsed, () => nextTick(buildAll))
</script>

<template>
  <div class="fft">
    <div class="title">FFT · IMU ACCELERATION SPECTRUM PER AXIS</div>
    <div class="banner">
      <div v-if="fs">Sample rate: <b>{{ fs.toFixed(0) }} Hz</b> (Nyquist {{ (fs/2).toFixed(0) }} Hz)</div>
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
.banner .hint { color: var(--text-dim); font-size: 11px; margin-top: 4px; font-family: var(--font-ui); }
.panes { flex: 1; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.pane { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.pane-label { color: var(--text-dim); font-size: 9px; letter-spacing: 2px; font-weight: 700; padding: 0 4px 2px; }
.pane-label .peak { color: var(--accent); font-family: var(--font-mono); margin-left: 8px; }
.pane-canvas { flex: 1; min-height: 0; border: 1px solid var(--border); background: var(--bg-1); }
</style>
