<script setup>
import { computed } from 'vue'
import { detectFrameKind } from '../analyzers/frameKind.js'

const props = defineProps({ parsed: Object })

const kind = computed(() => detectFrameKind(props.parsed || {}))

const meta = computed(() => {
  if (!props.parsed) return []
  const p = props.parsed
  return [
    ['Vehicle kind',  kind.value.toUpperCase()],
    ['MAV type',      p.vehicle_type ?? '—'],
    ['Duration',      `${p.duration.toFixed(1)} s`],
    ['Total messages', p.count.toLocaleString()],
    ['Message types', Object.keys(p.data || {}).length],
    ['Parameters',    Object.keys(p.params || {}).length],
    ['Start (local)', p.t_start ? new Date(p.t_start * 1000).toLocaleString() : '—'],
    ['End (local)',   p.t_end   ? new Date(p.t_end * 1000).toLocaleString()   : '—'],
  ]
})

const modeTimeline = computed(() => {
  const m = props.parsed?.data?.MODE
  const t = props.parsed?.times?.MODE
  if (!m?.Mode || !t) return []
  const t0 = props.parsed.t_start || 0
  const out = []
  let last = null
  for (let i = 0; i < m.Mode.length; i++) {
    if (m.Mode[i] === last) continue
    last = m.Mode[i]
    out.push({ t: t[i] - t0, mode: m.Mode[i], rsn: m.Rsn?.[i] })
  }
  return out
})

const errors = computed(() => {
  const e = props.parsed?.data?.ERR
  const t = props.parsed?.times?.ERR
  if (!e?.Subsys || !t) return []
  const t0 = props.parsed.t_start || 0
  return e.Subsys.map((s, i) => ({
    t: t[i] - t0,
    subsys: s,
    ecode: e.ECode?.[i],
  }))
})
</script>

<template>
  <div class="info">
    <div class="title">INFO · LOG METADATA · MODE TIMELINE · ERRORS</div>

    <div class="row">
      <div class="card">
        <div class="kicker">LOG METADATA</div>
        <table>
          <tr v-for="[k, v] in meta" :key="k">
            <td class="k">{{ k }}</td>
            <td class="v">{{ v }}</td>
          </tr>
        </table>
      </div>

      <div class="card">
        <div class="kicker">MODE TIMELINE</div>
        <div v-if="!modeTimeline.length" class="empty">No MODE messages.</div>
        <table v-else>
          <thead><tr><th>T+ (s)</th><th>MODE</th><th>REASON</th></tr></thead>
          <tr v-for="m in modeTimeline" :key="m.t">
            <td class="v">{{ m.t.toFixed(1) }}</td>
            <td class="v accent">{{ m.mode }}</td>
            <td class="v dim">{{ m.rsn ?? '—' }}</td>
          </tr>
        </table>
      </div>
    </div>

    <div class="card" v-if="errors.length">
      <div class="kicker">ERR EVENTS · {{ errors.length }} entries</div>
      <table>
        <thead><tr><th>T+ (s)</th><th>SUBSYS</th><th>ECODE</th></tr></thead>
        <tr v-for="(e, i) in errors" :key="i">
          <td class="v">{{ e.t.toFixed(1) }}</td>
          <td class="v accent">{{ e.subsys }}</td>
          <td class="v">{{ e.ecode }}</td>
        </tr>
      </table>
    </div>
  </div>
</template>

<style scoped>
.info { display: flex; flex-direction: column; gap: 12px; }
.title {
  color: var(--text-dim); font-size: 11px; font-weight: 700; letter-spacing: 2px; padding: 0 2px 4px;
}
.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.card {
  background: var(--bg-1);
  border: 1px solid var(--border);
  padding: 14px 18px;
}
.kicker {
  color: var(--text-dim);
  font-size: 10px;
  letter-spacing: 2.5px;
  font-weight: 700;
  margin-bottom: 10px;
}
table { width: 100%; border-collapse: collapse; font-family: var(--font-mono); font-size: 11px; }
th {
  text-align: left;
  background: var(--bg-2);
  color: var(--text-dim);
  font-weight: 700; letter-spacing: 1.5px; font-size: 9px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  font-family: var(--font-ui);
}
td { padding: 4px 10px; border-bottom: 1px solid var(--border); }
.k { color: var(--text-dim); }
.v { color: var(--text); }
.accent { color: var(--accent); }
.dim { color: var(--text-dim); }
.empty { color: var(--text-dim); font-family: var(--font-mono); font-size: 11px; padding: 6px 0; }
</style>
