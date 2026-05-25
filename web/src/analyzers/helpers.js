// Small numeric helpers — JS replacements for the numpy operations used
// throughout the analyzers.

export function nanmax(arr) {
  let m = -Infinity
  for (const v of arr) if (Number.isFinite(v) && v > m) m = v
  return m === -Infinity ? NaN : m
}

export function nanmin(arr) {
  let m = Infinity
  for (const v of arr) if (Number.isFinite(v) && v < m) m = v
  return m === Infinity ? NaN : m
}

export function nansum(arr) {
  let s = 0
  for (const v of arr) if (Number.isFinite(v)) s += v
  return s
}

export function nanmean(arr) {
  let s = 0, n = 0
  for (const v of arr) { if (Number.isFinite(v)) { s += v; n++ } }
  return n ? s / n : NaN
}

export function nanstd(arr) {
  const m = nanmean(arr)
  if (!Number.isFinite(m)) return NaN
  let s = 0, n = 0
  for (const v of arr) { if (Number.isFinite(v)) { s += (v - m) ** 2; n++ } }
  return n ? Math.sqrt(s / n) : NaN
}

export function median(arr) {
  const a = []
  for (const v of arr) if (Number.isFinite(v)) a.push(v)
  if (!a.length) return NaN
  a.sort((x, y) => x - y)
  const mid = a.length >> 1
  return a.length % 2 ? a[mid] : (a[mid - 1] + a[mid]) / 2
}

export function clampPositive(arr) {
  const out = []
  for (const v of arr) if (Number.isFinite(v) && v > 0) out.push(v)
  return out
}

export function abs(arr) { return arr.map(Math.abs) }

// argmax over |arr - ref|
export function argmaxAbsDelta(arr, ref) {
  let bi = 0, best = -Infinity
  for (let i = 0; i < arr.length; i++) {
    const d = Math.abs(arr[i] - ref)
    if (d > best) { best = d; bi = i }
  }
  return bi
}
