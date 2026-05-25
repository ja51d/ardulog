<script setup>
const props = defineProps({
  active: String,
  enabled: Boolean,
})
const emit = defineEmits(['update:active'])

const SECTIONS = [
  { title: 'VISUALIZE', items: [
    { key: 'summary',  label: 'SUMMARY',    icon: '◐' },
    { key: 'plot',     label: 'PLOT',       icon: '∿' },
    { key: 'map',      label: 'MAP',        icon: '◎' },
    { key: '3d',       label: '3D',         icon: '◢' },
    { key: 'cockpit',  label: 'COCKPIT',    icon: '◉' },
  ]},
  { title: 'ANALYZE', items: [
    { key: 'fft',      label: 'FFT',        icon: '≋' },
    { key: 'pid',      label: 'PID TUNING', icon: '∿' },
    { key: 'motors',   label: 'MOTORS',     icon: '◰' },
    { key: 'review',   label: 'REVIEW',     icon: '◇' },
  ]},
  { title: 'DATA', items: [
    { key: 'params',   label: 'PARAMS',     icon: '☰' },
    { key: 'info',     label: 'INFO',       icon: 'ⓘ' },
  ]},
]
</script>

<template>
  <nav class="nav">
    <template v-for="(sec, si) in SECTIONS" :key="si">
      <div class="section">{{ sec.title }}</div>
      <button
        v-for="it in sec.items" :key="it.key"
        class="item"
        :class="{ active: active === it.key, disabled: !enabled || it.soon }"
        :disabled="!enabled || it.soon"
        @click="emit('update:active', it.key)"
      >
        <span class="icon">{{ it.icon }}</span>
        <span class="label">{{ it.label }}</span>
        <span class="soon" v-if="it.soon">SOON</span>
      </button>
    </template>
  </nav>
</template>

<style scoped>
.nav {
  width: 200px;
  background: var(--bg-1);
  border-right: 1px solid var(--border);
  padding: 8px 0;
  overflow-y: auto;
  flex-shrink: 0;
}
.section {
  color: var(--text-dim);
  font-size: 9px;
  letter-spacing: 3px;
  font-weight: 700;
  padding: 14px 22px 4px;
}
.item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 9px 18px 9px 22px;
  background: transparent;
  color: var(--text-dim);
  border: none;
  border-left: 2px solid transparent;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 1.5px;
  text-align: left;
  cursor: pointer;
}
.item:hover:not(.disabled) {
  background: var(--bg-2);
  color: var(--text);
}
.item.active {
  background: var(--bg-2);
  color: var(--accent);
  border-left-color: var(--accent);
}
.item.disabled { opacity: 0.4; cursor: not-allowed; }
.item .icon { width: 14px; text-align: center; opacity: 0.7; }
.item .label { flex: 1; }
.item .soon {
  font-size: 8px;
  font-family: var(--font-mono);
  color: var(--warn);
  background: var(--bg-0);
  border: 1px solid var(--border);
  padding: 1px 5px;
  letter-spacing: 1px;
}
</style>
