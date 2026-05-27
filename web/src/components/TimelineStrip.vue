<script setup>
// Horizontal flight timeline — colored mode bands + event dots, with a
// playback cursor overlay. Click anywhere to jump to that time.
import { computed, ref } from 'vue'
import { extractEvents, extractModeBands } from '../analyzers/extractEvents.js'

const props = defineProps({
  parsed:  Object,
  playT:   { type: Number, default: 0 },
  duration: { type: Number, default: 0 },
})
const emit = defineEmits(['seek'])

const hoverEvent = ref(null)

const events = computed(() => extractEvents(props.parsed))
const modeBands = computed(() => extractModeBands(props.parsed))

const cursorPct = computed(() => {
  if (!props.duration) return 0
  return Math.min(100, Math.max(0, props.playT / props.duration * 100))
})

function pctOf(t) {
  if (!props.duration) return 0
  return Math.min(100, Math.max(0, t / props.duration * 100))
}
function onClick(e) {
  if (!props.duration) return
  if (e.target.closest('.event')) return
  const rect = e.currentTarget.getBoundingClientRect()
  const x = (e.clientX - rect.left) / rect.width
  emit('seek', Math.max(0, Math.min(1, x)) * props.duration)
}
</script>

<template>
  <div class="strip" v-if="duration > 0" @click="onClick">
    <div class="band" v-for="(b, i) in modeBands" :key="'b' + i"
         :style="{
           left:  pctOf(b.t0) + '%',
           width: Math.max(0, pctOf(b.t1) - pctOf(b.t0)) + '%',
           background: b.color,
         }">
      <span class="band-label" v-if="b.t1 - b.t0 > duration * 0.06">{{ b.label }}</span>
    </div>
    <div class="track"></div>
    <div class="event" v-for="(e, i) in events" :key="i"
         :style="{ left: pctOf(e.t) + '%', background: e.color }"
         @mouseenter="hoverEvent = e"
         @mouseleave="hoverEvent = null">
      <div class="dot"></div>
      <div class="tip" :class="'k-' + e.kind">
        <span class="lab">{{ e.label }}</span>
        <span class="ts">T+{{ e.t.toFixed(1) }}s</span>
      </div>
    </div>
    <div class="cursor" :style="{ left: cursorPct + '%' }"></div>
    <div class="ticks">
      <span v-for="n in 5" :key="n"></span>
    </div>
    <div class="meta">
      <span class="k">TIMELINE</span>
      <span class="v">{{ events.length }} events</span>
    </div>
  </div>
</template>

<style scoped>
.strip {
  position: relative;
  height: 38px;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  overflow: visible;
  flex-shrink: 0;
}
.band {
  position: absolute;
  top: 4px; bottom: 4px;
  opacity: 0.18;
  pointer-events: none;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  overflow: hidden;
}
.band + .band { border-left: 1px solid rgba(0,0,0,0.25); }
.band-label {
  color: #fff;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 1.5px;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0,0,0,0.6);
  opacity: 1;
  filter: brightness(2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 4px;
}
.track {
  position: absolute;
  top: 50%; left: 12px; right: 12px;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.10), transparent);
  transform: translateY(-50%);
  pointer-events: none;
  z-index: 2;
}
.ticks {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  display: flex;
  pointer-events: none;
  padding: 4px 12px;
}
.ticks span { flex: 1; border-left: 1px dashed var(--surface-2); }
.ticks span:first-child { border-left: none; }

.event {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 3;
}
.event .dot {
  width: 9px; height: 9px; border-radius: 50%;
  background: inherit;
  border: 2px solid #0e131c;
  box-shadow: 0 0 0 0 currentColor, 0 0 8px currentColor;
  cursor: pointer;
  transition: transform 120ms var(--ease-out);
}
.event .dot:hover { transform: scale(1.4); }
.event .tip {
  position: absolute;
  bottom: 18px;
  left: 50%;
  transform: translateX(-50%);
  background: #0e131c;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 6px 9px;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text);
  opacity: 0;
  pointer-events: none;
  transition: opacity 120ms var(--ease-out);
  box-shadow: var(--shadow-soft);
  z-index: 6;
}
.event:hover .tip { opacity: 1; }
.event .tip .ts { color: var(--text-mute); margin-left: 6px; }

.cursor {
  position: absolute;
  top: 4px; bottom: 4px;
  width: 2px;
  background: linear-gradient(180deg, transparent, var(--accent), transparent);
  box-shadow: 0 0 10px var(--accent);
  transform: translateX(-1px);
  pointer-events: none;
  z-index: 2;
}
.meta {
  position: absolute;
  top: 50%;
  right: 12px;
  transform: translateY(-50%);
  display: flex;
  gap: 8px;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-mute);
  letter-spacing: 1.5px;
  background: var(--panel-from);
  padding: 2px 8px;
  border-radius: 999px;
  pointer-events: none;
}
.meta .v { color: var(--text-dim); }

@media (max-width: 768px) { .meta { display: none; } }
</style>
