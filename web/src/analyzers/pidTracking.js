// Port of analyze_pid_tracking() from app.py. Returns
//   { roll: {rms_err, peak_err, osc_hz, lag_ms, verdict, hint}, pitch:..., yaw:... }
import { nanmean, nanmax, median } from './helpers.js'

export function analyzePidTracking(parsed) {
  const out = {}
  const att = parsed?.data?.ATT
  const attT = parsed?.times?.ATT
  if (!att || !attT || attT.length < 50) return out
  const t = attT
  // Build a coarse "armed" mask if STAT has it
  let armedMask = null
  const stat = parsed?.data?.STAT
  const statT = parsed?.times?.STAT
  if (stat && stat.Armed && statT && stat.Armed.length === statT.length) {
    // Build per-ATT-time armed flag via piecewise nearest from STAT
    armedMask = new Array(t.length)
    let j = 0
    for (let i = 0; i < t.length; i++) {
      while (j + 1 < statT.length && statT[j + 1] <= t[i]) j++
      armedMask[i] = stat.Armed[j] > 0.5
    }
  }

  const pairs = [
    ['roll',  'Roll',  'DesRoll'],
    ['pitch', 'Pitch', 'DesPitch'],
    ['yaw',   'Yaw',   'DesYaw'],
  ]

  for (const [axis, actualKey, desiredKey] of pairs) {
    if (!att[actualKey] || !att[desiredKey]) continue
    const a0 = att[actualKey], d0 = att[desiredKey]
    if (a0.length !== t.length || d0.length !== t.length) continue
    // Filter to finite + armed
    const a = [], d = [], tt = []
    for (let i = 0; i < t.length; i++) {
      if (!Number.isFinite(a0[i]) || !Number.isFinite(d0[i])) continue
      if (armedMask && !armedMask[i]) continue
      a.push(a0[i]); d.push(d0[i]); tt.push(t[i])
    }
    if (a.length < 50) continue

    // Skip if commanded signal is essentially flat (e.g. yaw on a plane)
    const dMean = nanmean(d)
    let dStd = 0, n = 0
    for (const v of d) { dStd += (v - dMean) ** 2; n++ }
    dStd = Math.sqrt(dStd / n)
    if (dStd < 1) {
      out[axis] = {
        rms_err: 0, peak_err: 0, osc_hz: 0, lag_ms: 0,
        verdict: 'no-command',
        hint: `${axis.toUpperCase()} has no real command in this log (desired is flat). On a plane this is normal for yaw — the autopilot banks to turn instead of commanding heading.`,
      }
      continue
    }

    // err
    let err = new Array(a.length)
    for (let i = 0; i < a.length; i++) err[i] = a[i] - d[i]
    if (axis === 'yaw') err = err.map(e => ((e + 180) % 360 + 360) % 360 - 180)

    // RMS / peak
    let sumsq = 0, peak = 0
    for (const e of err) {
      sumsq += e * e
      const ae = Math.abs(e); if (ae > peak) peak = ae
    }
    const rms = Math.sqrt(sumsq / err.length)

    // Oscillation frequency: zero-crossings of (err - mean(err)) / 2 / duration
    const errMean = nanmean(err)
    let crossings = 0
    let lastSign = Math.sign(err[0] - errMean)
    for (let i = 1; i < err.length; i++) {
      const s = Math.sign(err[i] - errMean)
      if (s !== 0 && s !== lastSign && lastSign !== 0) crossings++
      if (s !== 0) lastSign = s
    }
    const duration = tt[tt.length - 1] - tt[0]
    const oscHz = duration > 0 ? (crossings / 2) / duration : 0

    // Lag via cross-correlation, up to 250 ms shift
    let lagMs = 0
    try {
      const dt = median(tt.slice(1).map((v, i) => v - tt[i])) || 0.02
      const maxShift = Math.max(1, Math.floor(0.25 / dt))
      // Center both signals
      const dMu = nanmean(d), aMu = nanmean(a)
      const dC = d.map(v => v - dMu), aC = a.map(v => v - aMu)
      let bestShift = 0, bestCorr = -Infinity
      for (let s = 0; s <= maxShift; s++) {
        let c = 0
        const N = a.length - s
        for (let i = 0; i < N; i++) c += dC[i] * aC[i + s]
        if (c > bestCorr) { bestCorr = c; bestShift = s }
      }
      lagMs = bestShift * dt * 1000
    } catch (_) { lagMs = 0 }

    // Verdict + hint (same rules as Python)
    let verdict, hint
    if (oscHz > 4.0 && rms > 1.5) {
      verdict = 'oscillating'
      hint = `${axis.toUpperCase()} error oscillates at ~${oscHz.toFixed(1)} Hz — P gain likely too high. Reduce *_RATE_P by ~20%.`
    } else if (rms > 8.0) {
      verdict = 'loose'
      hint = `${axis.toUpperCase()} tracking is loose (RMS ${rms.toFixed(1)}°). Increase *_RATE_P by ~20% or check FF gain.`
    } else if (rms > 4.0 || peak > 25) {
      verdict = 'loose'
      hint = `${axis.toUpperCase()} tracks but with delay/overshoot. Consider small P bump or check that *_RATE_I isn't 0.`
    } else if (lagMs > 150 && rms > 2.0) {
      verdict = 'lagging'
      hint = `${axis.toUpperCase()} lags command by ~${lagMs.toFixed(0)} ms — raise *_RATE_P or *_RATE_D slightly.`
    } else {
      verdict = 'good'
      hint = `${axis.toUpperCase()} tracks well (RMS ${rms.toFixed(1)}°, peak ${peak.toFixed(0)}°, ${oscHz.toFixed(1)} Hz, lag ${lagMs.toFixed(0)} ms).`
    }
    out[axis] = { rms_err: rms, peak_err: peak, osc_hz: oscHz, lag_ms: lagMs, verdict, hint }
  }
  return out
}
