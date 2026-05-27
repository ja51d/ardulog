<script setup>
import { computed } from 'vue'
import { autoReview } from '../analyzers/autoReview.js'

const props = defineProps({ parsed: Object })

const items = computed(() => autoReview(props.parsed))

const counts = computed(() => {
  const c = { Good: 0, Marginal: 0, Bad: 0, Info: 0 }
  for (const it of items.value) c[it.verdict] = (c[it.verdict] || 0) + 1
  return c
})

const overall = computed(() => {
  if (counts.value.Bad > 0)      return { color: '#d96666', label: 'NEEDS ATTENTION', blurb: 'Some flight data points to issues that should be looked at before the next flight.' }
  if (counts.value.Marginal > 0) return { color: '#d9a14a', label: 'ACCEPTABLE',      blurb: 'The flight was usable, but a few things are on the marginal side.' }
  if (counts.value.Good > 0)     return { color: '#5dba7c', label: 'HEALTHY FLIGHT',  blurb: 'All measured systems behaved well throughout the flight.' }
  return { color: '#7a8699', label: 'LIMITED DATA', blurb: 'Not enough standard data to grade the flight.' }
})
</script>

<template>
  <div class="review">
    <!-- Overall score card -->
    <div class="score-card" :style="{ borderLeftColor: overall.color }">
      <div class="icon" :style="{ color: overall.color }">◼</div>
      <div class="text">
        <div class="kicker">OVERALL FLIGHT HEALTH</div>
        <div class="verdict" :style="{ color: overall.color }">{{ overall.label }}</div>
        <div class="blurb">{{ overall.blurb }}</div>
      </div>
      <div class="tally">
        <div class="chip" :style="{ borderTopColor: '#5dba7c' }">
          <div class="num" style="color:#5dba7c">{{ counts.Good }}</div>
          <div class="lab">GOOD</div>
        </div>
        <div class="chip" :style="{ borderTopColor: '#d9a14a' }">
          <div class="num" style="color:#d9a14a">{{ counts.Marginal }}</div>
          <div class="lab">MARGINAL</div>
        </div>
        <div class="chip" :style="{ borderTopColor: '#d96666' }">
          <div class="num" style="color:#d96666">{{ counts.Bad }}</div>
          <div class="lab">BAD</div>
        </div>
        <div class="chip" :style="{ borderTopColor: '#4a90e2' }">
          <div class="num" style="color:#4a90e2">{{ counts.Info }}</div>
          <div class="lab">INFO</div>
        </div>
      </div>
    </div>

    <div class="findings-title">DETAILED FINDINGS</div>

    <!-- Per-finding cards -->
    <div
      class="card"
      v-for="(it, idx) in items"
      :key="idx"
      :style="{ borderLeftColor: it.color }"
      :title="it.tip"
    >
      <div class="card-top">
        <div class="category">{{ it.category }}<span class="info" v-if="it.tip"> ⓘ</span></div>
        <div class="badge" :style="{ background: it.color }">{{ it.verdict.toUpperCase() }}</div>
      </div>
      <div class="headline">{{ it.headline }}</div>
      <div class="detail" v-if="it.detail" v-html="it.detail"></div>
    </div>
  </div>
</template>

<style scoped>
.review { display: flex; flex-direction: column; gap: 12px; }

.score-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 22px;
  padding: 20px 24px;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(10px) saturate(140%);
  -webkit-backdrop-filter: blur(10px) saturate(140%);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-soft);
  overflow: hidden;
}
.score-card::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--grad-accent);
  box-shadow: 0 0 14px rgba(61,169,252,0.5);
}
.score-card .icon {
  font-size: 22px;
  font-weight: 600;
  width: 30px;
  text-align: center;
}
.score-card .text { flex: 1; min-width: 0; }
.score-card .kicker {
  color: var(--text-dim);
  font-size: 10px;
  letter-spacing: 2.5px;
  font-weight: 700;
}
.score-card .verdict {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 2px;
  margin-top: 4px;
}
.score-card .blurb {
  color: var(--text-dim);
  font-size: 12px;
  margin-top: 4px;
}
.tally { display: flex; gap: 8px; }
.chip {
  position: relative;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 14px 10px;
  min-width: 68px;
  text-align: center;
  overflow: hidden;
  transition: border-color 200ms, transform 200ms;
}
.chip::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--grad-accent);
  opacity: 0.6;
}
.chip:hover { border-color: var(--border-strong); transform: translateY(-1px); }
.chip .num {
  font-family: var(--font-mono);
  font-size: 22px;
  font-weight: 700;
}
.chip .lab {
  font-size: 9px;
  letter-spacing: 1.5px;
  font-weight: 600;
  color: var(--text-dim);
}

.findings-title {
  color: var(--text-dim);
  font-size: 10px;
  letter-spacing: 2.5px;
  font-weight: 700;
  margin-top: 4px;
  padding: 0 4px;
}

.card {
  position: relative;
  background: linear-gradient(180deg, var(--panel-from) 0%, var(--panel-to) 100%);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 18px 14px 22px;
  transition: border-color 180ms var(--ease-out), transform 180ms var(--ease-out);
  overflow: hidden;
}
.card::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--accent);
}
.card:hover { border-color: var(--border-strong); transform: translateY(-1px); }
.card-top {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}
.category {
  flex: 1;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}
.info { color: var(--text-dim); }
.badge {
  color: var(--bg-0);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  padding: 2px 10px;
}
.headline {
  color: var(--text);
  font-size: 13px;
}
.detail {
  color: var(--text-dim);
  font-size: 12px;
  margin-top: 4px;
  line-height: 1.5;
}
.detail :deep(b) { color: var(--text); }
</style>
