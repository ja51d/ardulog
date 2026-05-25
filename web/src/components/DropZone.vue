<script setup>
import { ref } from 'vue'

const emit = defineEmits(['file'])
const hover = ref(false)
const input = ref(null)

function onDrop(e) {
  hover.value = false
  const f = e.dataTransfer.files?.[0]
  if (f) emit('file', f)
}
function onPick(e) {
  const f = e.target.files?.[0]
  if (f) emit('file', f)
}
</script>

<template>
  <div class="dropzone-wrap">
    <div
      class="dropzone"
      :class="{ hover }"
      @dragover.prevent="hover = true"
      @dragleave.prevent="hover = false"
      @drop.prevent="onDrop"
    >
      <div class="icon">▼</div>
      <div class="title">DROP FLIGHT LOG TO LOAD</div>
      <div class="hint">.bin &nbsp;·&nbsp; .tlog &nbsp;·&nbsp; .log</div>
    </div>
    <div class="alt-actions">
      <button class="btn-primary" @click="input.click()">◉  BROWSE FOR A LOG</button>
      <input ref="input" type="file" accept=".bin,.tlog,.log" style="display:none" @change="onPick" />
    </div>
    <div class="note">
      All parsing happens in your browser. The log file is never uploaded anywhere.
    </div>
  </div>
</template>

<style scoped>
.dropzone-wrap {
  max-width: 600px;
  margin: 60px auto 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 22px;
}
.dropzone {
  width: 100%;
  background: var(--bg-1);
  border: 1px dashed var(--border);
  padding: 48px 36px;
  text-align: center;
  transition: border-color 80ms;
}
.dropzone.hover {
  border-color: var(--accent);
  background: var(--bg-2);
}
.icon {
  color: var(--accent);
  font-size: 26px;
  margin-bottom: 14px;
}
.title {
  color: var(--text);
  font-size: 13px;
  letter-spacing: 3px;
  font-weight: 600;
}
.hint {
  color: var(--text-dim);
  font-size: 11px;
  letter-spacing: 3px;
  font-weight: 600;
  margin-top: 8px;
}
.alt-actions { display: flex; gap: 10px; }
.btn-primary {
  background: var(--accent);
  color: var(--bg-0);
  border: 1px solid var(--accent);
  padding: 8px 16px;
  font-weight: 700;
  font-size: 11px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
}
.btn-primary:hover { background: var(--accent-2); border-color: var(--accent-2); }
.note {
  color: var(--text-dim);
  font-size: 11px;
  font-family: var(--font-mono);
  margin-top: 16px;
  text-align: center;
}
</style>
