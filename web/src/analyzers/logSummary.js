// Build a compact text summary of a parsed log for feeding to the AI.
// We send a few hundred tokens of useful context — vehicle type, durations,
// modes, event timeline, key extrema, battery stats, FFT peaks, review
// findings — so the model can answer questions without re-uploading the
// full ArrayBuffer.

import { extractEvents } from './extractEvents.js'
import { autoReview } from './autoReview.js'
import { extractTrack } from './extractTrack.js'
import { detectFrameKind } from './frameKind.js'

function fmt(v, d = 1, suffix = '') {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toFixed(d) + suffix
}

function stats(arr) {
  if (!arr?.length) return null
  let lo = Infinity, hi = -Infinity, sum = 0, n = 0
  for (const v of arr) {
    if (!Number.isFinite(v)) continue
    if (v < lo) lo = v
    if (v > hi) hi = v
    sum += v; n++
  }
  return n ? { min: lo, max: hi, avg: sum / n, n } : null
}

export function buildLogSummaryForAI(parsed) {
  if (!parsed) return '(no log loaded)'

  const lines = []
  const frame = detectFrameKind(parsed) || 'Unknown'
  lines.push(`Vehicle: ${frame}`)
  lines.push(`Duration: ${fmt(parsed.duration, 1, ' s')}`)
  lines.push(`Messages: ${parsed.count?.toLocaleString?.() || parsed.count}`)
  if (parsed.t_start) {
    const d = new Date(parsed.t_start * 1000)
    lines.push(`Start time (UTC): ${d.toISOString()}`)
  }

  // Track stats
  const tr = extractTrack(parsed)
  if (tr?.coords?.length) {
    const altStats = stats(tr.alts)
    if (altStats) {
      lines.push(`Altitude: min ${fmt(altStats.min, 1)} m, max ${fmt(altStats.max, 1)} m, gain ${fmt(altStats.max - altStats.min, 1)} m`)
    }
    // Rough distance traveled
    let dist = 0
    for (let i = 1; i < tr.coords.length; i++) {
      const [la1, ln1] = tr.coords[i - 1], [la2, ln2] = tr.coords[i]
      const dy = (la2 - la1) * 111320
      const dx = (ln2 - ln1) * 111320 * Math.cos(la1 * Math.PI / 180)
      dist += Math.hypot(dx, dy)
    }
    lines.push(`Track distance: ${fmt(dist, 0, ' m')} (${(dist / 1000).toFixed(2)} km)`)
  } else {
    lines.push(`Track: no valid GPS coordinates`)
  }

  // Modes
  const mode = parsed.data?.MODE
  if (mode?.Mode) {
    const uniq = []
    for (const v of mode.Mode) if (uniq[uniq.length - 1] !== v) uniq.push(v)
    lines.push(`Mode transitions: ${uniq.length} (${uniq.slice(0, 12).join('→')}${uniq.length > 12 ? '…' : ''})`)
  }

  // Events (mode changes, arm/disarm, failsafes)
  const events = extractEvents(parsed)
  if (events.length) {
    lines.push(`\nEvents (T+s):`)
    for (const e of events.slice(0, 40)) {
      lines.push(`  T+${e.t.toFixed(1)}s — ${e.label} [${e.kind}]`)
    }
    if (events.length > 40) lines.push(`  … and ${events.length - 40} more`)
  }

  // Battery
  const bat = parsed.data?.BAT || parsed.data?.CURR
  if (bat) {
    const v = stats(bat.Volt || bat.V), c = stats(bat.Curr || bat.C)
    const mAh = bat.CurrTot || bat.E
    if (v) lines.push(`Battery V: min ${fmt(v.min, 2)}, max ${fmt(v.max, 2)}, avg ${fmt(v.avg, 2)}, sag ${fmt(v.max - v.min, 2)} V`)
    if (c) lines.push(`Current A: peak ${fmt(c.max, 1)}, avg ${fmt(c.avg, 1)}`)
    if (mAh?.length) lines.push(`Energy used: ${fmt(mAh[mAh.length - 1], 0, ' mAh')}`)
  }

  // GPS quality
  const gps = parsed.data?.GPS
  if (gps?.NSats) {
    const s = stats(gps.NSats)
    if (s) lines.push(`GPS NSats: min ${s.min}, max ${s.max}, avg ${fmt(s.avg, 1)}`)
  }
  if (gps?.HDop) {
    const s = stats(gps.HDop)
    if (s) lines.push(`GPS HDop: min ${fmt(s.min, 2)}, max ${fmt(s.max, 2)}`)
  }

  // Attitude
  const att = parsed.data?.ATT
  if (att) {
    const r = stats(att.Roll), p = stats(att.Pitch)
    if (r) lines.push(`Roll range: ${fmt(r.min, 0)}° to ${fmt(r.max, 0)}°`)
    if (p) lines.push(`Pitch range: ${fmt(p.min, 0)}° to ${fmt(p.max, 0)}°`)
  }

  // Airspeed / groundspeed
  const arsp = parsed.data?.ARSP, ctun = parsed.data?.CTUN
  if (arsp?.Airspeed || arsp?.Aspd) {
    const s = stats(arsp.Airspeed || arsp.Aspd)
    if (s) lines.push(`Airspeed: min ${fmt(s.min, 1)} m/s, max ${fmt(s.max, 1)} m/s, avg ${fmt(s.avg, 1)} m/s`)
  } else if (ctun?.As) {
    const s = stats(ctun.As)
    if (s) lines.push(`Airspeed (CTUN.As): max ${fmt(s.max, 1)} m/s`)
  }

  // Available message types
  const types = Object.keys(parsed.data || {})
  if (types.length) {
    lines.push(`\nAvailable message types: ${types.join(', ')}`)
  }

  // Auto-review findings
  const review = autoReview(parsed)
  if (review?.length) {
    lines.push(`\nAuto-review findings:`)
    for (const f of review.slice(0, 12)) {
      // detail can contain HTML — strip tags for the AI
      const detail = String(f.detail || f.headline || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
      lines.push(`  [${f.verdict}] ${f.category}: ${detail.slice(0, 200)}`)
    }
    if (review.length > 12) lines.push(`  … and ${review.length - 12} more`)
  }

  return lines.join('\n')
}
