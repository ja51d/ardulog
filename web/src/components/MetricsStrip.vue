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
  background: var(--bg-0);
  border-bottom: 1px solid var(--border);
  height: 34px;
  padding: 0 20px;
  align-items: center;
  flex-shrink: 0;
}
.cell {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-right: 22px;
  margin-right: 20px;
  border-right: 1px solid var(--border);
  height: 22px;
}
.cell:last-child { border-right: none; }
.k {
  color: var(--text-dim);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 2px;
}
.v {
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
}
</style>
