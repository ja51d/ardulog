<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const props = defineProps({ parsed: Object })

// --- Tree state ---
const filter = ref('')
const expanded = ref(new Set())     // expanded message type names
const selected = ref(new Map())     // 'TYPE.FIELD' -> color

const COLORS = [
  '#4a90e2', '#d9a14a', '#5dba7c', '#d96666',
  '#6aa9e8', '#a78bfa', '#f472b6', '#facc15',
  '#4ade80', '#fb923c',
]

const types = computed(() => {
  if (!props.parsed?.data) return []
  const out = []
  for (const [name, fields] of Object.entries(props.parsed.data)) {
    const fieldNames = Object.keys(fields).filter(k => k !== 'TimeUS')
    out.push({ name, fieldCount: fieldNames.length, fields: fieldNames.sort() })
  }
  return out.sort((a, b) => a.name.localeCompare(b.name))
})

const filtered = computed(() => {
  const f = filter.value.trim().toUpperCase()
  if (!f) return types.value
  return types.value
    .map(t => {
      if (t.name.toUpperCase().includes(f)) return t
      const matched = t.fields.filter(fn => fn.toUpperCase().includes(f))
      if (matched.length) return { ...t, fields: matched, _matchedFields: true }
      return null
    })
    .filter(Boolean)
})

function toggleExpand(name) {
  if (expanded.value.has(name)) expanded.value.delete(name)
  else expanded.value.add(name)
  // trigger reactivity since Set mutations aren't tracked
  expanded.value = new Set(expanded.value)
}

function toggleField(typeName, fieldName) {
  const key = `${typeName}.${fieldName}`
  if (selected.value.has(key)) {
    selected.value.delete(key)
  } else {
    // assign next free color
    const used = new Set(selected.value.values())
    const color = COLORS.find(c => !used.has(c)) || COLORS[selected.value.size % COLORS.length]
    selected.value.set(key, color)
  }
  selected.value = new Map(selected.value)
}

function clearAll() { selected.value = new Map() }

// --- Plot ---
const plotRef = ref(null)
let plot = null

function buildSeriesData() {
  if (!props.parsed) return null
  const keys = [...selected.value.keys()]
  if (!keys.length) return null

  // Union all message-type timestamps so we have a single x-axis. Per-series
  // values are interpolated/aligned by nearest sample (uPlot expects every
  // series to share the same x array length).
  // For simplicity in v1: pick the longest time array across the selected
  // message types and use that. Each series is interpolated to it.
  let xRef = null, xRefName = null
  for (const k of keys) {
    const [tn] = k.split('.')
    const t = props.parsed.times[tn] || []
    if (!xRef || t.length > xRef.length) { xRef = t; xRefName = tn }
  }
  if (!xRef || !xRef.length) return null

  // x in seconds-since-start
  const t0 = props.parsed.t_start || 0
  const xs = xRef.map(t => t - t0)

  const series = [{}] // first is x slot
  const data = [xs]
  for (const [key, color] of selected.value.entries()) {
    const [tn, fn] = key.split('.')
    const tArr = props.parsed.times[tn] || []
    const vArr = props.parsed.data[tn]?.[fn] || []
    let ys
    if (tn === xRefName) {
      ys = vArr.map(Number)
    } else {
      // Nearest-neighbor align: for each xRef time, pick the closest tArr index
      ys = new Array(xRef.length)
      let j = 0
      for (let i = 0; i < xRef.length; i++) {
        const target = xRef[i]
        while (j + 1 < tArr.length && Math.abs(tArr[j + 1] - target) <= Math.abs(tArr[j] - target)) j++
        ys[i] = j < vArr.length ? Number(vArr[j]) : null
      }
    }
    series.push({
      label: key,
      stroke: color,
      width: 1.2,
      points: { show: false },
    })
    data.push(ys)
  }
  return { data, series }
}

function rebuildPlot() {
  if (!plotRef.value) return
  const rect = plotRef.value.getBoundingClientRect()
  if (rect.width < 100) return  // canvas not laid out yet — ResizeObserver will retry
  if (plot) { plot.destroy(); plot = null }
  const built = buildSeriesData()
  if (!built) return
  const opts = {
    width: Math.max(400, rect.width),
    height: Math.max(300, rect.height),
    series: built.series,
    axes: [
      { stroke: '#7a8699', grid: { stroke: '#323a47', width: 1 }, ticks: { stroke: '#323a47' },
        values: (u, splits) => splits.map(s => s.toFixed(1) + 's') },
      { stroke: '#7a8699', grid: { stroke: '#323a47', width: 1 }, ticks: { stroke: '#323a47' } },
    ],
    legend: { show: true },
    cursor: { drag: { x: true, y: false } },
  }
  plot = new uPlot(opts, built.data, plotRef.value)
}

function handleResize() {
  if (!plot || !plotRef.value) return
  const rect = plotRef.value.getBoundingClientRect()
  plot.setSize({ width: Math.max(400, rect.width), height: Math.max(300, rect.height) })
}

let ro = null
onMounted(() => {
  nextTick(() => {
    rebuildPlot()
    if (typeof ResizeObserver !== 'undefined' && plotRef.value) {
      ro = new ResizeObserver(() => {
        handleResize()
        if (!plot && selected.value.size) rebuildPlot()
      })
      ro.observe(plotRef.value)
    }
  })
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (ro) { ro.disconnect(); ro = null }
  if (plot) plot.destroy()
})
watch(selected, () => nextTick(rebuildPlot), { deep: true })
watch(() => props.parsed, () => nextTick(rebuildPlot))
</script>

<template>
  <div class="plot-tab">
    <!-- Messages panel -->
    <div class="messages">
      <div class="m-header">MESSAGES · FIELDS</div>
      <input class="m-search" type="text" v-model="filter" placeholder="Filter messages or fields…" />
      <div class="m-tree">
        <template v-for="t in filtered" :key="t.name">
          <button class="type-row" @click="toggleExpand(t.name)">
            <span class="caret">{{ expanded.has(t.name) || t._matchedFields ? '▾' : '▸' }}</span>
            <span class="type-name">{{ t.name }}</span>
            <span class="type-count">{{ t.fieldCount }}</span>
          </button>
          <div v-if="expanded.has(t.name) || t._matchedFields" class="fields">
            <button
              v-for="fn in t.fields" :key="fn"
              class="field-row"
              :class="{ active: selected.has(`${t.name}.${fn}`) }"
              :style="selected.has(`${t.name}.${fn}`) ? { color: selected.get(`${t.name}.${fn}`) } : {}"
              @click="toggleField(t.name, fn)"
            >
              <span class="check">{{ selected.has(`${t.name}.${fn}`) ? '◼' : '◻' }}</span>
              <span>{{ fn }}</span>
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- Plot area -->
    <div class="plot-pane">
      <div class="plot-header">
        <div class="count">{{ selected.size }} series</div>
        <div class="grow"></div>
        <button v-if="selected.size" class="clear" @click="clearAll">× CLEAR ALL</button>
      </div>
      <div ref="plotRef" class="plot-canvas">
        <div v-if="!selected.size" class="hint">
          <div class="hint-title">SELECT FIELDS FROM THE TREE</div>
          <div class="hint-sub">Click any field name to plot it. Add multiple to overlay.</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plot-tab {
  display: flex;
  gap: 10px;
  height: 100%;
  min-height: 0;
}

/* Messages panel */
.messages {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
}
.m-header {
  color: var(--text-dim);
  font-size: 10px;
  letter-spacing: 2px;
  font-weight: 700;
  padding: 0 2px 4px;
  border-bottom: 1px solid var(--border);
}
.m-search {
  background: var(--bg-2);
  border: 1px solid var(--border);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 6px 10px;
  outline: none;
}
.m-search:focus { border-color: var(--accent); }
.m-tree {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--border);
  background: var(--bg-1);
  padding: 4px 0;
  min-height: 0;
}
.type-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  background: transparent;
  color: var(--text);
  border: none;
  padding: 4px 10px;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
  text-align: left;
}
.type-row:hover { background: var(--bg-2); }
.caret { color: var(--text-dim); width: 10px; }
.type-name { flex: 1; }
.type-count {
  color: var(--text-dim);
  font-size: 10px;
  background: var(--bg-2);
  padding: 1px 6px;
  border: 1px solid var(--border);
}
.fields { padding: 2px 0 6px; }
.field-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  background: transparent;
  color: var(--text-dim);
  border: none;
  padding: 3px 10px 3px 28px;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 11px;
  text-align: left;
}
.field-row:hover { color: var(--text); background: var(--bg-2); }
.field-row.active { color: var(--accent); }
.check { width: 12px; }

/* Plot pane */
.plot-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  min-height: 0;
}
.plot-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 4px;
}
.plot-header .count {
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 11px;
}
.plot-header .grow { flex: 1; }
.plot-header .clear {
  background: var(--bg-2);
  border: 1px solid var(--border);
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 4px 10px;
  letter-spacing: 1px;
  cursor: pointer;
}
.plot-header .clear:hover { color: var(--danger); border-color: var(--danger); }
.plot-canvas {
  flex: 1;
  border: 1px solid var(--border);
  background: var(--bg-1);
  position: relative;
  min-height: 360px;
}
.hint {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}
.hint-title {
  color: var(--text-dim);
  font-size: 12px;
  letter-spacing: 3px;
  font-weight: 700;
}
.hint-sub {
  color: var(--text-dim);
  font-size: 11px;
  margin-top: 8px;
  font-family: var(--font-mono);
}
</style>

<style>
/* uPlot dark overrides */
.uplot .u-legend { color: var(--text-dim) !important; font-family: var(--font-mono) !important; font-size: 11px !important; }
.uplot .u-legend .u-marker { border-radius: 0 !important; }
.uplot .u-select { background: rgba(74, 144, 226, 0.15) !important; }
</style>
