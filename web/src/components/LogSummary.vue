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
    <!-- Status card -->
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

    <!-- Top message types -->
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

    <!-- Phase note -->
    <div class="phase-note">
      <b>PHASE 1 LIVE.</b>
      The .bin parser runs entirely in your browser. Next sessions will port the
      PLOT, REVIEW, MOTORS, PARAMS, 3D, and Cockpit views from the desktop app.
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; gap: 14px; }

.card {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  padding: 18px 22px;
}
.head { display: flex; align-items: baseline; gap: 16px; margin-bottom: 16px; }
.kicker {
  color: var(--text-dim);
  font-size: 10px;
  letter-spacing: 2.5px;
  font-weight: 700;
}
.verdict {
  color: var(--accent);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 2px;
  font-family: var(--font-mono);
}
.hint {
  color: var(--text-dim);
  font-size: 11px;
  font-family: var(--font-mono);
}
.grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.stat {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-top: 2px solid var(--accent);
  padding: 12px 14px;
}
.stat .k { color: var(--text-dim); font-size: 9px; font-weight: 700; letter-spacing: 2px; }
.stat .v { color: var(--text); font-family: var(--font-mono); font-size: 18px; margin-top: 4px; font-weight: 600; }

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th, td {
  text-align: left;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
th {
  background: var(--bg-2);
  color: var(--text-dim);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1.5px;
  border-bottom: 1px solid var(--border);
}
.r { text-align: right; }
.mono { font-family: var(--font-mono); }
.accent { color: var(--accent); }
.dim { color: var(--text-dim); }

.phase-note {
  margin-top: 6px;
  padding: 12px 16px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-left: 3px solid var(--warn);
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.5;
}
.phase-note b { color: var(--warn); font-family: var(--font-mono); letter-spacing: 1.5px; }
</style>
