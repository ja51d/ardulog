<script setup>
import { computed } from 'vue'

const props = defineProps({ parsed: Object, frame: String })

const modes = computed(() => {
  const m = props.parsed?.data?.MODE?.Mode
  if (!m) return '—'
  const uniq = []
  for (const v of m) if (uniq[uniq.length-1] !== v) uniq.push(v)
  return String(uniq.length)
})
const altMax = computed(() => {
  const alts = props.parsed?.data?.POS?.Alt
  if (!alts || !alts.length) return '—'
  let lo = Infinity, hi = -Infinity
  for (const v of alts) { if (v < lo) lo = v; if (v > hi) hi = v }
  return `+${(hi - lo).toFixed(1)} m`
})
const start = computed(() => {
  if (!props.parsed?.t_start) return '—'
  const d = new Date(props.parsed.t_start * 1000)
  return d.toLocaleTimeString('en-GB', { hour12: false })
})

const METRICS = computed(() => [
  ['FRAME',    props.frame],
  ['DURATION', `${props.parsed.duration.toFixed(1)} s`],
  ['MESSAGES', props.parsed.count.toLocaleString()],
  ['MODES',    modes.value],
  ['ALT MAX',  altMax.value],
  ['START',    start.value],
])
</script>

<template>
  <div class="strip">
    <div class="cell" v-for="[k, v] in METRICS" :key="k">
      <div class="k">{{ k }}</div>
      <div class="v">{{ v }}</div>
    </div>
  </div>
</template>

<style scoped>
.strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: var(--panel-from);
  border-bottom: 1px solid var(--border);
  padding: 10px 24px;
  align-items: center;
  flex-shrink: 0;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 999px;
  transition: border-color 160ms var(--ease-out), background 160ms var(--ease-out);
}
.cell:hover {
  border-color: var(--border-strong);
  background: var(--surface-2);
}
.k {
  color: var(--text-mute);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 2px;
}
.v {
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
}
</style>
