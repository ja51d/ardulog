<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ parsed: Object })
const filter = ref('')

const sorted = computed(() => {
  const params = props.parsed?.params || {}
  return Object.entries(params).sort(([a], [b]) => a.localeCompare(b))
})

const filtered = computed(() => {
  const f = filter.value.trim().toUpperCase()
  if (!f) return sorted.value
  return sorted.value.filter(([name]) => name.toUpperCase().includes(f))
})

function fmtValue(v) {
  if (typeof v !== 'number') return String(v)
  if (!Number.isFinite(v)) return String(v)
  // Mirror the desktop's "%.6g" formatting
  const a = Math.abs(v)
  if (a === 0) return '0'
  if (a < 1e-4 || a >= 1e6) return v.toExponential(4)
  // Trim trailing zeros after up-to-6 significant digits
  return parseFloat(v.toPrecision(6)).toString()
}
</script>

<template>
  <div class="params">
    <div class="header-row">
      <div class="title">PARAMS · FLIGHT CONTROLLER PARAMETERS FROM THE LOG</div>
    </div>
    <input
      class="search"
      v-model="filter"
      type="text"
      placeholder="Search parameters (e.g. TKOFF, COMPASS, ARSPD)…"
    />
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>NAME</th><th>VALUE</th></tr>
        </thead>
        <tbody>
          <tr v-for="[name, val] in filtered" :key="name">
            <td class="name">{{ name }}</td>
            <td class="value">{{ fmtValue(val) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="status">
      {{ filter ? `${filtered.length} of ${sorted.length} match '${filter.toUpperCase()}'` : `${sorted.length} parameter(s)` }}
    </div>
  </div>
</template>

<style scoped>
.params { display: flex; flex-direction: column; gap: 8px; height: 100%; min-height: 0; }
.header-row .title {
  color: var(--text-dim);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 2px;
  padding: 0 4px 4px;
}
.search {
  background: var(--bg-2);
  border: 1px solid var(--border);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 8px 12px;
  outline: none;
}
.search:focus { border-color: var(--accent); }
.table-wrap {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--border);
  background: var(--bg-1);
  min-height: 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono);
  font-size: 11px;
}
thead { position: sticky; top: 0; z-index: 1; }
th {
  text-align: left;
  background: var(--bg-2);
  color: var(--text-dim);
  font-weight: 700;
  letter-spacing: 1.5px;
  font-size: 9px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  font-family: var(--font-ui);
}
td {
  padding: 5px 12px;
  border-bottom: 1px solid var(--border);
}
td.name { color: var(--accent); }
td.value { color: var(--text); }
tbody tr:hover { background: var(--bg-2); }
.status {
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 4px 6px;
}
</style>
