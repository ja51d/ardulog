<script setup>
// SVG instrument panel — attitude indicator, HSI, altitude tape, airspeed
// tape. The "time" slider lets you scrub through the log; values update
// reactively.
import { ref, computed, watch } from 'vue'

const props = defineProps({ parsed: Object })

const t = ref(0)            // seconds since log start
const duration = computed(() => props.parsed?.duration || 0)

watch(() => props.parsed, () => { t.value = duration.value })

// Helper: nearest-index sampler for a (times, values) pair
function sampleAt(timesArr, valuesArr, tSec) {
  if (!timesArr?.length || !valuesArr?.length) return null
  const t0 = props.parsed?.t_start || 0
  const target = t0 + tSec
  let bj = 0, bd = Infinity
  for (let i = 0; i < timesArr.length; i++) {
    const d = Math.abs(timesArr[i] - target)
    if (d < bd) { bd = d; bj = i }
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
    </div>

    <!-- Scrubber -->
    <div class="scrub">
      <button class="step" @click="t = 0">⏮</button>
      <input type="range" min="0" :max="duration" step="0.1" v-model.number="t" class="slider"/>
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
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;
  flex: 1; min-height: 0;
}
.instr {
  background: var(--bg-1); border: 1px solid var(--border);
  display: flex; flex-direction: column; align-items: center; padding: 14px;
  min-height: 0;
}
.instr-label {
  color: var(--text-dim);
  font-size: 9px; letter-spacing: 2.5px; font-weight: 700;
  margin-bottom: 8px;
}
.ai-svg, .hsi-svg { width: 100%; max-width: 280px; height: auto; aspect-ratio: 1; }
.tape { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 0; }
.tape .big {
  font-family: var(--font-mono);
  color: var(--text);
  font-size: 38px; font-weight: 700; letter-spacing: 1px;
}
.tape .big .unit { font-size: 14px; color: var(--text-dim); letter-spacing: 1.5px; margin-left: 6px; }
.tape .sub { color: var(--text-dim); font-size: 10px; letter-spacing: 1.5px; }
.tape .mono { font-family: var(--font-mono); }
.thr-bar {
  width: 70%; height: 8px;
  background: var(--bg-2); border: 1px solid var(--border);
  position: relative; overflow: hidden;
}
.thr-fill { height: 100%; background: var(--accent); }

.scrub {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 14px;
  background: var(--bg-1);
  border: 1px solid var(--border);
}
.scrub .step {
  background: var(--bg-2);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 4px 10px;
  font-family: var(--font-mono);
  cursor: pointer;
}
.scrub .step:hover { color: var(--accent); border-color: var(--accent); }
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
