<script setup>
import { computed } from 'vue'
const props = defineProps({ parsed: Object, frame: String })

const topTypes = computed(() => {
  const arr = []
  for (const [k, fields] of Object.entries(props.parsed.times || {})) {
    arr.push([k, fields.length])
  }
  arr.sort((a, b) => b[1] - a[1])
  return arr.slice(0, 20)
})

const paramCount = computed(() => Object.keys(props.parsed.params || {}).length)
const typeCount = computed(() => Object.keys(props.parsed.data || {}).length)
</script>

<template>
  <div class="wrap">
    <div class="card">
      <div class="head">
        <div class="kicker">LOG PARSED</div>
        <div class="verdict">{{ frame }} · {{ parsed.count.toLocaleString() }} MESSAGES</div>
      </div>
      <div class="grid">
        <div class="stat"><div class="k">FRAME TYPE</div><div class="v">{{ frame }}</div></div>
        <div class="stat"><div class="k">DURATION</div><div class="v">{{ parsed.duration.toFixed(1) }} s</div></div>
        <div class="stat"><div class="k">MESSAGE TYPES</div><div class="v">{{ typeCount }}</div></div>
        <div class="stat"><div class="k">PARAMETERS</div><div class="v">{{ paramCount }}</div></div>
      </div>
    </div>

    <div class="card">
      <div class="head">
        <div class="kicker">TOP MESSAGE TYPES</div>
        <div class="hint">{{ topTypes.length }} of {{ typeCount }} types · by count</div>
      </div>
      <table>
        <thead><tr><th>TYPE</th><th class="r">COUNT</th><th>RATE (HZ)</th></tr></thead>
        <tbody>
          <tr v-for="[name, count] in topTypes" :key="name">
            <td class="mono accent">{{ name }}</td>
            <td class="mono r">{{ count.toLocaleString() }}</td>
            <td class="mono dim">{{ (count / parsed.duration).toFixed(1) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="phase-note">
      <b>100% LOCAL.</b>
      Every byte of this log was parsed in your browser — nothing was uploaded.
      Use the rail on the left to explore plots, map, 3D playback, motors, PID tuning, FFT, and more.
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; gap: 14px; }

.card {
  position: relative;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(10px) saturate(140%);
  -webkit-backdrop-filter: blur(10px) saturate(140%);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 22px;
  box-shadow: var(--shadow-soft);
  overflow: hidden;
}
.card::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--grad-accent);
  box-shadow: 0 0 14px rgba(61,169,252,0.5);
}
.head { display: flex; align-items: baseline; gap: 16px; margin-bottom: 18px; flex-wrap: wrap; }
.kicker { color: var(--text-mute); font-size: 10px; letter-spacing: 2.5px; font-weight: 700; }
.verdict {
  font-size: 18px; font-weight: 700; letter-spacing: 2px;
  font-family: var(--font-mono);
  background: var(--grad-accent);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.hint { color: var(--text-dim); font-size: 11px; font-family: var(--font-mono); }

.grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.stat {
  position: relative;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  transition: border-color 200ms var(--ease-out), transform 200ms var(--ease-out), background 200ms var(--ease-out);
  overflow: hidden;
}
.stat::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--grad-accent);
  opacity: 0.55;
}
.stat:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
  background: var(--surface-2);
}
.stat .k { color: var(--text-mute); font-size: 9px; font-weight: 700; letter-spacing: 2px; }
.stat .v { color: var(--text); font-family: var(--font-mono); font-size: 20px; margin-top: 6px; font-weight: 700; letter-spacing: 0.5px; }

table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td {
  text-align: left; padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
tbody tr { transition: background 120ms var(--ease-out); }
tbody tr:hover td { background: var(--surface-1); }
th {
  background: var(--surface-1);
  color: var(--text-mute);
  font-size: 9px; font-weight: 700; letter-spacing: 1.8px;
  border-bottom: 1px solid var(--border-strong);
}
.r { text-align: right; }
.mono { font-family: var(--font-mono); }
.accent { color: var(--accent-2); }
.dim { color: var(--text-mute); }

.phase-note {
  margin-top: 6px;
  padding: 14px 18px;
  background: linear-gradient(180deg, rgba(240,183,93,0.08) 0%, rgba(240,183,93,0.02) 100%);
  border: 1px solid rgba(240,183,93,0.20);
  border-radius: var(--radius-sm);
  color: var(--text-2);
  font-size: 12px; line-height: 1.55;
}
.phase-note b { color: var(--warn); font-family: var(--font-mono); letter-spacing: 1.5px; }

@media (max-width: 900px) {
  .grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 480px) {
  .grid { grid-template-columns: 1fr; }
  .card { padding: 16px; }
  .verdict { font-size: 16px; }
  table { font-size: 11px; }
  th, td { padding: 6px 8px; }
}
</style>
