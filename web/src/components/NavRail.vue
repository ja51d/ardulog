<script setup>
const props = defineProps({
  active: String,
  enabled: Boolean,
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['update:active'])

const SECTIONS = [
  { title: 'VISUALIZE', items: [
    { key: 'summary',  label: 'SUMMARY',    icon: '◐' },
    { key: 'plot',     label: 'PLOT',       icon: '∿' },
    { key: 'map',      label: 'MAP',        icon: '◎' },
    { key: 'terrain',  label: 'TERRAIN',    icon: '◬' },
    { key: '3d',       label: '3D',         icon: '◢' },
    { key: 'cockpit',  label: 'COCKPIT',    icon: '◉' },
  ]},
  { title: 'ANALYZE', items: [
    { key: 'ai',       label: 'COPILOT',    icon: '✦' },
    { key: 'fft',      label: 'FFT',        icon: '≋' },
    { key: 'pid',      label: 'PID TUNING', icon: '∿' },
    { key: 'motors',   label: 'MOTORS',     icon: '◰' },
    { key: 'battery',  label: 'BATTERY',    icon: '⚡' },
    { key: 'review',   label: 'REVIEW',     icon: '◇' },
  ]},
  { title: 'DATA', items: [
    { key: 'report',   label: 'REPORT',     icon: '📄' },
    { key: 'params',   label: 'PARAMS',     icon: '☰' },
    { key: 'info',     label: 'INFO',       icon: 'ⓘ' },
  ]},
]
</script>

<template>
  <nav class="nav" :class="{ open }">
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
      </button>
    </template>
  </nav>
</template>

<style scoped>
.nav {
  width: 212px;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-right: 1px solid var(--border);
  padding: 14px 10px;
  overflow-y: auto;
  flex-shrink: 0;
}
.section {
  color: var(--text-mute);
  font-size: 9px;
  letter-spacing: 2.8px;
  font-weight: 700;
  padding: 16px 14px 6px;
}
.section:first-child { padding-top: 4px; }
.item {
  position: relative;
  display: flex; align-items: center; gap: 12px;
  width: 100%;
  padding: 9px 12px;
  margin: 2px 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-dim);
  border: none;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 1.6px;
  text-align: left;
  cursor: pointer;
  transition: background 160ms var(--ease-out), color 160ms var(--ease-out);
}
.item:hover:not(.disabled) { background: var(--surface-2); color: var(--text); }
.item:hover:not(.disabled) .icon { opacity: 1; color: var(--accent-2); }
.item.active { background: var(--accent-soft); color: var(--accent-2); }
.item.active::before {
  content: '';
  position: absolute;
  left: -10px;
  top: 6px; bottom: 6px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--grad-accent);
  box-shadow: 0 0 10px rgba(61,169,252,0.6);
}
.item.disabled { opacity: 0.35; cursor: not-allowed; }
.item .icon {
  width: 16px;
  text-align: center;
  opacity: 0.65;
  font-size: 13px;
  transition: opacity 160ms, color 160ms;
}
.item .label { flex: 1; }

@media (max-width: 768px) {
  .nav {
    position: absolute;
    top: 0; bottom: 0; left: 0;
    z-index: 10;
    width: 248px;
    max-width: 80vw;
    transform: translateX(-100%);
    transition: transform 260ms var(--ease-out);
    box-shadow: 8px 0 32px rgba(0,0,0,0.5);
    padding-top: 18px;
  }
  .nav.open { transform: translateX(0); }
  .item { padding: 12px 14px; font-size: 13px; }
  .section { padding: 18px 16px 8px; }
}
</style>
