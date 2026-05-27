<script setup>
// SVG instrument panel — attitude indicator, HSI, altitude tape, airspeed
// tape. The "time" slider lets you scrub through the log; values update
// reactively.
import { ref, computed, watch, onBeforeUnmount } from 'vue'

const props = defineProps({ parsed: Object })

const t = ref(0)            // seconds since log start
const duration = computed(() => props.parsed?.duration || 0)
const playing = ref(false)
const speed = ref(1)
let raf = null
let lastTick = 0

watch(() => props.parsed, () => { t.value = duration.value })

function tick(now) {
  if (!playing.value) return
  if (!lastTick) lastTick = now
  const dt = (now - lastTick) / 1000
  lastTick = now
  t.value = Math.min(duration.value, t.value + dt * speed.value)
  if (t.value >= duration.value) { playing.value = false; raf = null; return }
  raf = requestAnimationFrame(tick)
}
function play() {
  if (playing.value) return
  if (t.value >= duration.value) t.value = 0
  playing.value = true
  lastTick = 0
  raf = requestAnimationFrame(tick)
}
function pause() {
  playing.value = false
  if (raf) cancelAnimationFrame(raf); raf = null
}
function reset() { pause(); t.value = 0 }
onBeforeUnmount(() => { if (raf) cancelAnimationFrame(raf) })

// Helper: nearest-index sampler for a (times, values) pair.
// Uses binary search — log timestamps are monotonically increasing, so
// this is O(log n) instead of O(n). Big deal on a 60fps loop with
// 20k+ samples × 6 fields.
function sampleAt(timesArr, valuesArr, tSec) {
  const n = timesArr?.length
  if (!n || !valuesArr?.length) return null
  const target = (props.parsed?.t_start || 0) + tSec
  // Binary search for the largest index where times[i] <= target
  let lo = 0, hi = n - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (timesArr[mid] <= target) lo = mid
    else hi = mid - 1
  }
  // Pick whichever of lo / lo+1 is closer
  let bj = lo
  if (lo + 1 < n && Math.abs(timesArr[lo + 1] - target) < Math.abs(timesArr[lo] - target)) {
    bj = lo + 1
  }
  return valuesArr[bj] != null ? Number(valuesArr[bj]) : null
}

const att = computed(() => {
  const a = props.parsed?.data?.ATT
  const tt = props.parsed?.times?.ATT
  if (!a || !tt) return { roll: 0, pitch: 0, yaw: 0 }
  return {
    roll:  sampleAt(tt, a.Roll,  t.value) ?? 0,
    pitch: sampleAt(tt, a.Pitch, t.value) ?? 0,
    yaw:   sampleAt(tt, a.Yaw,   t.value) ?? 0,
  }
})
const altM = computed(() => {
  // POS.Alt minus the starting altitude → AGL
  const block = props.parsed?.data?.POS
  const tt = props.parsed?.times?.POS
  if (!block?.Alt || !tt) return null
  const alt = sampleAt(tt, block.Alt, t.value)
  const a0 = block.Alt[0]
  return alt != null && a0 != null ? alt - a0 : null
})
const aspd = computed(() => {
  // Try ARSP.Airspeed first, fall back to CTUN.As, else GPS.Spd
  const a = props.parsed?.data?.ARSP
  const tt = props.parsed?.times?.ARSP
  if (a && (a.Airspeed || a.Aspd) && tt) return sampleAt(tt, a.Airspeed || a.Aspd, t.value)
  const c = props.parsed?.data?.CTUN
  const tc = props.parsed?.times?.CTUN
  if (c?.As && tc) return sampleAt(tc, c.As, t.value)
  const g = props.parsed?.data?.GPS
  const tg = props.parsed?.times?.GPS
  if (g?.Spd && tg) return sampleAt(tg, g.Spd, t.value)
  return null
})
const thr = computed(() => {
  const c = props.parsed?.data?.CTUN
  const tc = props.parsed?.times?.CTUN
  return c?.ThO && tc ? sampleAt(tc, c.ThO, t.value) ?? 0 : 0
})

// Wind — ArduPilot publishes its own estimate as WIND.{VelX, VelY, VelZ}
// (North/East/Down components in m/s). If absent, fall back to nothing.
const wind = computed(() => {
  const w = props.parsed?.data?.WIND
  const tw = props.parsed?.times?.WIND
  if (!w || !tw?.length) return null
  // Some firmwares use Direction (deg) + Speed (m/s) instead of components.
  if (w.Speed != null && w.Direction != null) {
    const spd = sampleAt(tw, w.Speed, t.value)
    const dir = sampleAt(tw, w.Direction, t.value)
    if (spd == null || dir == null) return null
    return { speed: spd, dirDeg: dir }
  }
  const vx = sampleAt(tw, w.VelX || w.WN, t.value)  // North component
  const vy = sampleAt(tw, w.VelY || w.WE, t.value)  // East  component
  if (vx == null || vy == null) return null
  const speed = Math.hypot(vx, vy)
  // Wind direction: meteorological convention is "where the wind is coming FROM"
  // Components are "where it's going TO", so flip 180°.
  let dirDeg = (Math.atan2(vy, vx) * 180 / Math.PI + 180 + 360) % 360
  return { speed, dirDeg }
})

// RC stick positions (Mode 2): Ch1=Roll, Ch2=Pitch, Ch3=Throttle, Ch4=Yaw.
// PWM range is normally 1000–2000 with 1500 = neutral. We normalize to
// -1..+1 so the SVG knobs translate by a unit-length percent of radius.
function normPwm(v) {
  if (v == null) return 0
  // Auto-detect 1000-2000 vs 0-100 vs already-normalized
  if (v > 100) return Math.max(-1, Math.min(1, (v - 1500) / 500))
  if (v > 1)   return Math.max(-1, Math.min(1, (v - 50) / 50))
  return Math.max(-1, Math.min(1, v))
}
const sticks = computed(() => {
  const rc = props.parsed?.data?.RCIN
  const tt = props.parsed?.times?.RCIN
  if (!rc || !tt) return { left: { x: 0, y: 0 }, right: { x: 0, y: 0 } }
  const roll  = sampleAt(tt, rc.C1, t.value)
  const pitch = sampleAt(tt, rc.C2, t.value)
  const throt = sampleAt(tt, rc.C3, t.value)
  const yaw   = sampleAt(tt, rc.C4, t.value)
  // Right stick (Mode 2): X=roll, Y=pitch (push forward = pitch-down, so invert)
  // Left stick (Mode 2):  X=yaw,  Y=throttle (push forward = full throttle, invert)
  return {
    left:  { x: normPwm(yaw),  y: -normPwm(throt) },
    right: { x: normPwm(roll), y: -normPwm(pitch) },
  }
})
const hasRC = computed(() => !!props.parsed?.data?.RCIN)

// Attitude indicator viewport: horizon line + pitch ladder + roll bezel
const aiRoll = computed(() => att.value.roll || 0)
const aiPitch = computed(() => att.value.pitch || 0)
const horizonY = computed(() => aiPitch.value * 3)   // 3 px per degree of pitch

const yawDeg = computed(() => ((att.value.yaw || 0) % 360 + 360) % 360)

function fmtNum(v, d = 1) { return v == null ? '—' : v.toFixed(d) }
</script>

<template>
  <div class="cockpit">
    <div class="title">COCKPIT · ATTITUDE · HEADING · ALTITUDE · AIRSPEED</div>

    <div class="grid">
      <!-- Attitude indicator -->
      <div class="instr">
        <div class="instr-label">ATTITUDE</div>
        <svg viewBox="-100 -100 200 200" class="ai-svg">
          <defs>
            <clipPath id="ai-clip"><circle cx="0" cy="0" r="80" /></clipPath>
          </defs>
          <!-- Bezel ring -->
          <circle cx="0" cy="0" r="82" fill="#1a1f29" stroke="#323a47" stroke-width="2" />
          <!-- Inner clipped sky/ground rotated by roll -->
          <g clip-path="url(#ai-clip)">
            <g :transform="`rotate(${-aiRoll})`">
              <g :transform="`translate(0, ${horizonY})`">
                <!-- Sky -->
                <rect x="-200" y="-300" width="400" height="300" fill="#2f3f5a"/>
                <!-- Ground -->
                <rect x="-200" y="0" width="400" height="300" fill="#3f3025"/>
                <!-- Horizon -->
                <line x1="-200" y1="0" x2="200" y2="0" stroke="#cdd6e0" stroke-width="1.5"/>
                <!-- Pitch ladder -->
                <g v-for="p in [-30,-20,-10,10,20,30]" :key="p" :transform="`translate(0, ${-p*3})`" stroke="#cdd6e0" stroke-width="0.8">
                  <line :x1="p % 20 === 0 ? -28 : -16" :x2="p % 20 === 0 ? 28 : 16" y1="0" y2="0"/>
                  <text v-if="p % 20 === 0" x="-34" y="3" font-size="8" fill="#cdd6e0" text-anchor="end">{{ Math.abs(p) }}</text>
                  <text v-if="p % 20 === 0" x="34" y="3" font-size="8" fill="#cdd6e0">{{ Math.abs(p) }}</text>
                </g>
              </g>
            </g>
          </g>
          <!-- Roll arc + ticks -->
          <g stroke="#cdd6e0" stroke-width="1" fill="none">
            <path d="M -65 -45 A 80 80 0 0 1 65 -45" />
            <g v-for="r in [-60,-45,-30,-20,-10,0,10,20,30,45,60]" :key="r" :transform="`rotate(${r})`">
              <line x1="0" :y1="-80" x2="0" :y2="r % 30 === 0 ? -72 : -76" />
            </g>
          </g>
          <!-- Roll pointer (triangle, rotated by negative roll so it stays on top) -->
          <g :transform="`rotate(${-aiRoll})`">
            <polygon points="0,-78 -4,-70 4,-70" fill="#d9a14a"/>
          </g>
          <!-- Static aircraft symbol on top -->
          <g stroke="#d9a14a" stroke-width="3" fill="none" stroke-linecap="round">
            <line x1="-30" y1="0" x2="-10" y2="0"/>
            <line x1="30"  y1="0" x2="10"  y2="0"/>
            <line x1="0"   y1="0" x2="0"   y2="6"/>
            <circle cx="0" cy="0" r="2.5" fill="#d9a14a" stroke="none"/>
          </g>
          <!-- Roll/pitch readout -->
          <text x="0" y="92" font-size="9" fill="#7a8699" text-anchor="middle" font-family="JetBrains Mono, monospace">
            R {{ fmtNum(aiRoll, 0) }}°  ·  P {{ fmtNum(aiPitch, 0) }}°
          </text>
        </svg>
      </div>

      <!-- HSI / heading -->
      <div class="instr">
        <div class="instr-label">HEADING</div>
        <svg viewBox="-100 -100 200 200" class="hsi-svg">
          <circle cx="0" cy="0" r="82" fill="#1a1f29" stroke="#323a47" stroke-width="2"/>
          <g :transform="`rotate(${-yawDeg})`" stroke="#cdd6e0">
            <g v-for="h in [0,30,60,90,120,150,180,210,240,270,300,330]" :key="h" :transform="`rotate(${h})`">
              <line x1="0" :y1="-78" x2="0" :y2="h % 90 === 0 ? -64 : -70" stroke-width="1"/>
              <text v-if="h % 90 === 0" x="0" y="-52" font-size="11" fill="#cdd6e0" text-anchor="middle" font-weight="700">
                {{ { 0:'N', 90:'E', 180:'S', 270:'W' }[h] }}
              </text>
              <text v-else-if="h % 30 === 0" x="0" y="-56" font-size="8" fill="#7a8699" text-anchor="middle">
                {{ (h / 10).toString().padStart(2, '0') }}
              </text>
            </g>
          </g>
          <!-- Fixed aircraft symbol -->
          <g fill="#d9a14a" stroke="#1a1f29" stroke-width="0.5">
            <polygon points="0,-30 -6,-15 -2,-15 -2,8 -10,12 -10,16 0,12 10,16 10,12 2,8 2,-15 6,-15"/>
          </g>
          <!-- Pointer top -->
          <polygon points="0,-86 -5,-78 5,-78" fill="#4a90e2"/>
          <text x="0" y="92" font-size="9" fill="#7a8699" text-anchor="middle" font-family="JetBrains Mono, monospace">
            HDG {{ fmtNum(yawDeg, 0) }}°
          </text>
        </svg>
      </div>

      <!-- Altitude tape -->
      <div class="instr">
        <div class="instr-label">ALT (m AGL)</div>
        <div class="tape">
          <div class="big">{{ altM == null ? '—' : (altM >= 0 ? '+' : '') + altM.toFixed(1) }}</div>
          <div class="sub">metres above takeoff</div>
        </div>
      </div>

      <!-- Airspeed + throttle -->
      <div class="instr">
        <div class="instr-label">SPD / THR</div>
        <div class="tape">
          <div class="big">{{ fmtNum(aspd, 1) }} <span class="unit">m/s</span></div>
          <div class="sub">throttle</div>
          <div class="thr-bar"><div class="thr-fill" :style="{ width: Math.max(0, Math.min(100, thr)) + '%' }"></div></div>
          <div class="sub mono">{{ fmtNum(thr, 0) }}%</div>
        </div>
      </div>

      <!-- Wind -->
      <div class="instr" v-if="wind">
        <div class="instr-label">WIND</div>
        <svg viewBox="-100 -100 200 200" class="wind-svg">
          <circle cx="0" cy="0" r="78" fill="#11161f" stroke="#2a3340" stroke-width="2"/>
          <!-- Compass ticks -->
          <g stroke="#2a3340" stroke-width="1">
            <g v-for="h in [0,90,180,270]" :key="h" :transform="`rotate(${h})`">
              <line x1="0" y1="-78" x2="0" y2="-68"/>
            </g>
          </g>
          <text y="-58" text-anchor="middle" font-size="10" fill="#cdd6e0" font-family="JetBrains Mono">N</text>
          <text x="58" y="3" text-anchor="middle" font-size="10" fill="#7d8aa0">E</text>
          <text y="65" text-anchor="middle" font-size="10" fill="#7d8aa0">S</text>
          <text x="-58" y="3" text-anchor="middle" font-size="10" fill="#7d8aa0">W</text>
          <!-- Wind arrow (rotated, points "from" direction) -->
          <g :transform="`rotate(${wind.dirDeg})`">
            <path d="M 0 -45 L -10 -20 L -3 -20 L -3 30 L 3 30 L 3 -20 L 10 -20 Z"
                  fill="#3da9fc" stroke="#0e131c" stroke-width="1"/>
          </g>
          <text x="0" y="86" text-anchor="middle" font-size="10" fill="#7d8aa0" font-family="JetBrains Mono">
            {{ wind.speed.toFixed(1) }} m/s · {{ wind.dirDeg.toFixed(0) }}°
          </text>
        </svg>
      </div>

      <!-- Stick inputs -->
      <div class="instr sticks-instr">
        <div class="instr-label">STICKS · RC INPUT (MODE 2)</div>
        <div v-if="!hasRC" class="no-rc">No RCIN messages in this log.</div>
        <div v-else class="sticks-row">
          <div class="stick-box">
            <svg viewBox="-100 -100 200 200" class="stick-svg">
              <rect x="-90" y="-90" width="180" height="180" rx="14"
                    fill="#11161f" stroke="#2a3340" stroke-width="2"/>
              <line x1="-90" y1="0" x2="90" y2="0" stroke="#1f2733" stroke-width="1"/>
              <line x1="0" y1="-90" x2="0" y2="90" stroke="#1f2733" stroke-width="1"/>
              <circle cx="0" cy="0" r="78" fill="none" stroke="#1f2733" stroke-width="1" stroke-dasharray="2 4"/>
              <!-- Knob -->
              <g :style="{ transform: `translate(${sticks.left.x * 78}px, ${sticks.left.y * 78}px)` }" class="stick-knob">
                <circle cx="0" cy="0" r="16" fill="#3da9fc" stroke="#0e131c" stroke-width="2"/>
                <circle cx="0" cy="0" r="6"  fill="#0e131c"/>
              </g>
              <text x="0" y="-78" text-anchor="middle" font-size="9" fill="#7a8699" font-family="JetBrains Mono, monospace">THR</text>
              <text x="0" y="86"  text-anchor="middle" font-size="9" fill="#7a8699" font-family="JetBrains Mono, monospace">YAW</text>
            </svg>
            <div class="stick-label">LEFT</div>
          </div>
          <div class="stick-box">
            <svg viewBox="-100 -100 200 200" class="stick-svg">
              <rect x="-90" y="-90" width="180" height="180" rx="14"
                    fill="#11161f" stroke="#2a3340" stroke-width="2"/>
              <line x1="-90" y1="0" x2="90" y2="0" stroke="#1f2733" stroke-width="1"/>
              <line x1="0" y1="-90" x2="0" y2="90" stroke="#1f2733" stroke-width="1"/>
              <circle cx="0" cy="0" r="78" fill="none" stroke="#1f2733" stroke-width="1" stroke-dasharray="2 4"/>
              <g :style="{ transform: `translate(${sticks.right.x * 78}px, ${sticks.right.y * 78}px)` }" class="stick-knob">
                <circle cx="0" cy="0" r="16" fill="#ff6b35" stroke="#0e131c" stroke-width="2"/>
                <circle cx="0" cy="0" r="6"  fill="#0e131c"/>
              </g>
              <text x="0" y="-78" text-anchor="middle" font-size="9" fill="#7a8699" font-family="JetBrains Mono, monospace">PITCH</text>
              <text x="0" y="86"  text-anchor="middle" font-size="9" fill="#7a8699" font-family="JetBrains Mono, monospace">ROLL</text>
            </svg>
            <div class="stick-label">RIGHT</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Scrubber + transport controls -->
    <div class="scrub">
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
             v-model.number="t" class="slider"
             @mousedown="pause"/>
      <div class="time mono">T+{{ t.toFixed(1) }}s / {{ duration.toFixed(1) }}s</div>
    </div>
  </div>
</template>

<style scoped>
.cockpit { display: flex; flex-direction: column; gap: 12px; height: 100%; min-height: 0; }
.title {
  color: var(--text-dim); font-size: 11px; font-weight: 700; letter-spacing: 2px; padding: 0 2px 4px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  grid-auto-rows: minmax(0, auto);
  gap: 10px;
  flex: 1; min-height: 0;
}
.sticks-instr {
  grid-column: 1 / -1;     /* span full width below the 2x2 */
}
.sticks-row {
  display: flex;
  gap: 24px;
  justify-content: center;
  width: 100%;
  padding: 6px 0 2px;
}
.stick-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.stick-svg {
  width: 100%;
  max-width: 180px;
  height: auto;
  aspect-ratio: 1;
}
/* Smooth the knob between sample updates. transform-origin must be the
 * SVG origin (0,0) since we translate from there. */
.stick-knob {
  transition: transform 90ms cubic-bezier(0.22, 1, 0.36, 1);
  transform-origin: 0 0;
  transform-box: fill-box;
  will-change: transform;
}
.stick-label {
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 2px;
}
.no-rc {
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 22px 0;
  text-align: center;
}

/* ===== Mobile ===== */
@media (max-width: 768px) {
  .grid { grid-template-columns: 1fr; gap: 10px; }
  .ai-svg, .hsi-svg { max-width: 220px; }
  .tape .big { font-size: 30px; }
  .sticks-row { gap: 12px; }
  .stick-svg { max-width: 140px; }
}
@media (max-width: 768px) {
  .scrub { flex-wrap: wrap; row-gap: 10px; }
  .scrub .slider { flex: 1 1 100%; order: 10; }
  .scrub .time { flex: 1 1 100%; text-align: left; order: 11; min-width: 0; font-size: 10px; }
}
.instr {
  position: relative;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(10px) saturate(140%);
  -webkit-backdrop-filter: blur(10px) saturate(140%);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex; flex-direction: column; align-items: center;
  padding: 18px 16px;
  min-height: 0;
  box-shadow: var(--shadow-soft);
  transition: border-color 200ms var(--ease-out);
  overflow: hidden;
}
.instr:hover { border-color: var(--border-strong); }
.instr::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(61,169,252,0.35), transparent);
}
.instr-label {
  color: var(--text-mute);
  font-size: 9px; letter-spacing: 2.5px; font-weight: 700;
  margin-bottom: 10px;
}
.ai-svg, .hsi-svg, .wind-svg { width: 100%; max-width: 280px; height: auto; aspect-ratio: 1; }
.tape { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 0; }
.tape .big {
  font-family: var(--font-mono);
  font-size: 38px; font-weight: 700; letter-spacing: 1px;
  color: var(--text);
}
.tape .big .unit { font-size: 14px; color: var(--text-dim); letter-spacing: 1.5px; margin-left: 6px; }
.tape .sub { color: var(--text-dim); font-size: 10px; letter-spacing: 1.5px; }
.tape .mono { font-family: var(--font-mono); }
.thr-bar {
  width: 70%; height: 8px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  position: relative; overflow: hidden;
}
.thr-fill {
  height: 100%;
  background: var(--grad-accent);
  border-radius: 999px;
  box-shadow: 0 0 8px rgba(61,169,252,0.4);
  transition: width 220ms var(--ease-out);
}

.scrub {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
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
  transition: color 160ms, border-color 160ms, background 160ms;
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
.scrub .slider {
  flex: 1;
  -webkit-appearance: none; appearance: none;
  height: 4px;
  background: var(--bg-2);
  outline: none;
  border: 1px solid var(--border);
}
.scrub .slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 14px; height: 14px;
  background: var(--accent);
  cursor: pointer;
}
.scrub .time {
  color: var(--text-dim);
  font-size: 11px;
  min-width: 160px;
  text-align: right;
}
</style>
