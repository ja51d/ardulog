// Port of auto_review() from app.py — runs a plain-English health check
// across the parsed log. Returns an array of review cards.
import { nanmean, nanmax, nanmin, nanstd, median } from './helpers.js'
import { detectFrameKind } from './frameKind.js'
import { analyzePidTracking } from './pidTracking.js'

// Palette constants — match the desktop app + style.css
const SUCCESS = '#5dba7c'
const WARN    = '#d9a14a'
const DANGER  = '#d96666'
const ACCENT  = '#4a90e2'
const TEXT_DIM = '#7a8699'

const TIPS = {
  'Vibration':
    "ArduPilot's VIBE message records 3-axis acceleration variance from the IMU. " +
    "Under 30 m/s² is fine, over 60 m/s² degrades EKF and position hold.",
  'IMU clipping':
    "Counter that increments whenever the accelerometer hits its measurement-range " +
    "limit. Any clipping at all means vibration spikes — usually unbalanced props.",
  'GPS':
    "Quality of the GPS fix. HDop is geometric dilution of precision (lower = better).",
  'Battery':
    "LiPo cells should stay above 3.5V each under load and never drop below 3.3V.",
  'Compass':
    "Magnetic-field magnitude variance. Steady = good. >15% swing usually means a " +
    "power cable is too close to the compass.",
  'EKF (state estimator)':
    "ArduPilot's EKF fuses IMU+GPS+compass+baro. Innovation spikes >1.0 indicate " +
    "the filter is struggling.",
  'Errors':
    "ERR messages logged by ArduPilot subsystems.",
  'Altitude':
    "AGL (above takeoff) altitude profile. Vertical speed peaks above 8 m/s " +
    "indicate aggressive throttle inputs.",
  'Attitude':
    "Peak roll/pitch angles. Under 25° = calm, 25-45° = sport, >45° = acro.",
  'Motor balance':
    "PWM output across motors. Should be within ~60 µs of each other. Large spreads " +
    "point to CG offset, bent arm, prop imbalance, or one worn-out motor.",
  'Power used':
    "Total milliamp-hours drawn during the flight.",
  'RC link':
    "Stability of the RC receiver signal.",
  'Autopilot CPU':
    "Max main-loop execution time vs the budget.",
  'IMU temperature':
    "Temperature drift across the flight. Big swings shift gyro bias.",
  'Flight modes':
    "Sequence of flight modes used.",
  'Takeoff health':
    "Per-takeoff analysis for fixed-wing TAKEOFF mode entries. Checks throttle " +
    "ramp speed, rotation airspeed vs stall, roll divergence, and TKOFF_* params.",
  'PID tracking':
    "Compares commanded with actual attitude. Loose tracking → raise P. " +
    "Oscillation → lower P. Lag → raise D.",
  'CPU loop overruns':
    "Plane main loop 20 000 µs budget; copter 2 500 µs. Overruns = brief 'blind' " +
    "moments. Usually slow SD card stalls.",
}

export function autoReview(parsed) {
  const items = []
  const data = parsed?.data || {}
  const times = parsed?.times || {}
  const kind = detectFrameKind(parsed)

  const add = (category, verdict, color, headline, detail) => items.push({
    category, verdict, color, headline, detail,
    tip: TIPS[category] || '',
  })

  // ===== Vibration =====
  const vibe = data.VIBE
  if (vibe && vibe.VibeX && vibe.VibeY && vibe.VibeZ) {
    const peak = Math.max(nanmax(vibe.VibeX), nanmax(vibe.VibeY), nanmax(vibe.VibeZ))
    const mags = vibe.VibeX.map((x, i) => Math.sqrt(x*x + (vibe.VibeY[i]||0)**2 + (vibe.VibeZ[i]||0)**2))
    const mean = nanmean(mags)
    if (peak < 30 && mean < 15) {
      add('Vibration', 'Good', SUCCESS, 'Vibration levels are healthy.',
        `Peak axis vibration was ${peak.toFixed(1)} m/s²; average magnitude ${mean.toFixed(1)} m/s². ArduPilot considers <30 m/s² fine.`)
    } else if (peak < 60 && mean < 30) {
      add('Vibration', 'Marginal', WARN, 'Vibration is acceptable but on the higher side.',
        `Peak ${peak.toFixed(1)} m/s² (advisory: <30). Consider balancing props, tightening motor mounts, or improving FC foam.`)
    } else {
      add('Vibration', 'Bad', DANGER, 'Vibration is high and may degrade EKF / position hold.',
        `Peak ${peak.toFixed(1)} m/s², average ${mean.toFixed(1)} m/s². ArduPilot warns above 60.`)
    }
  }
  // IMU clipping
  if (vibe && (vibe.Clip0 || vibe.Clip1 || vibe.Clip2)) {
    let total = 0
    for (const k of ['Clip0', 'Clip1', 'Clip2']) {
      const a = vibe[k]; if (!a || !a.length) continue
      total += (a[a.length - 1] - a[0]) | 0
    }
    if (total === 0) add('IMU clipping', 'Good', SUCCESS, 'No accelerometer clipping events.',
      'Clip counters did not increase — the IMU never saturated.')
    else if (total < 100) add('IMU clipping', 'Marginal', WARN, `${total} clipping events.`,
      'A few events are usually fine but indicate occasional vibration spikes.')
    else add('IMU clipping', 'Bad', DANGER, `${total} clipping events — IMU saturated repeatedly.`,
      'This usually points to severe vibration.')
  }

  // ===== GPS =====
  const gps = data.GPS
  if (gps) {
    const status = gps.Status
    const nsats  = gps.NSats
    const hdop   = gps.HDop
    if (status && status.length) {
      let fix3d = 0, satSum = 0, satN = 0, hsum = 0, hN = 0
      for (let i = 0; i < status.length; i++) {
        if (status[i] >= 3) {
          fix3d++
          if (nsats && Number.isFinite(nsats[i])) { satSum += nsats[i]; satN++ }
          if (hdop && hdop[i] > 0 && hdop[i] < 50) { hsum += hdop[i]; hN++ }
        }
      }
      const pct = fix3d / status.length * 100
      const avgSats = satN ? satSum / satN : 0
      const avgHdop = hN ? hsum / hN : 99
      if (pct > 70 && avgSats >= 8 && avgHdop < 1.5) {
        add('GPS', 'Good', SUCCESS, 'GPS reception was strong throughout the flight.',
          `3D fix held ${pct.toFixed(0)}% of the time, average ${avgSats.toFixed(0)} satellites, average HDop ${avgHdop.toFixed(2)} (under 1.5 is excellent).`)
      } else if (pct > 50 && avgSats >= 6 && avgHdop < 2.5) {
        add('GPS', 'Marginal', WARN, 'GPS reception was acceptable but not great.',
          `3D fix ${pct.toFixed(0)}% of time, ~${avgSats.toFixed(0)} sats, HDop ${avgHdop.toFixed(2)}.`)
      } else {
        add('GPS', 'Bad', DANGER, 'GPS reception was poor.',
          `3D fix only ${pct.toFixed(0)}% of time, ~${avgSats.toFixed(0)} sats, HDop ${avgHdop.toFixed(2)}.`)
      }
    }
  }

  // ===== Battery =====
  let bat = null
  for (const k of ['BAT', 'BAT1', 'BATT']) if (data[k] && data[k].Volt) { bat = data[k]; break }
  if (bat) {
    const v = bat.Volt.filter(x => x > 1)
    if (v.length) {
      const n = Math.max(1, Math.floor(v.length / 20))
      const vStart = median(v.slice(0, n))
      const vEnd   = median(v.slice(-n))
      const vMin   = nanmin(v)
      const cells  = vStart > 5 ? Math.round(vStart / 3.85) : 0
      const perCell = cells ? vMin / cells : 0
      if (cells && perCell >= 3.6) {
        add('Battery', 'Good', SUCCESS, `Battery healthy (${vStart.toFixed(1)}V → ${vEnd.toFixed(1)}V, ~${cells}S pack).`,
          `Minimum voltage ${vMin.toFixed(2)}V (${perCell.toFixed(2)}V/cell). Above 3.6V/cell is comfortable.`)
      } else if (cells && perCell >= 3.3) {
        add('Battery', 'Marginal', WARN, `Battery dipped low: ${vMin.toFixed(2)}V minimum (~${perCell.toFixed(2)}V/cell).`,
          `Started at ${vStart.toFixed(1)}V, ended at ${vEnd.toFixed(1)}V. Below 3.5V/cell under load is approaching the safe limit.`)
      } else {
        add('Battery', 'Bad', DANGER, `Battery sagged badly: ${vMin.toFixed(2)}V minimum${cells ? ` (~${perCell.toFixed(2)}V/cell)` : ''}.`,
          'Below 3.3V/cell under load damages LiPo cells.')
      }
    }
  }

  // ===== Compass =====
  const mag = data.MAG
  if (mag && mag.MagX && mag.MagY && mag.MagZ) {
    const magn = mag.MagX.map((x, i) => Math.sqrt(x*x + (mag.MagY[i]||0)**2 + (mag.MagZ[i]||0)**2))
    if (magn.length) {
      const m = nanmean(magn), s = nanstd(magn)
      const ratio = m > 0 ? s / m : 1
      if (ratio < 0.05) add('Compass', 'Good', SUCCESS, 'Magnetic field looks stable — no obvious interference.',
        `Mean field ${m.toFixed(0)} mGauss, variation ±${s.toFixed(0)} (${(ratio*100).toFixed(1)}%).`)
      else if (ratio < 0.15) add('Compass', 'Marginal', WARN, 'Magnetic field shows some variation.',
        `Mean ${m.toFixed(0)} mGauss, ±${s.toFixed(0)} (${(ratio*100).toFixed(1)}%).`)
      else add('Compass', 'Bad', DANGER, 'Magnetic field is unstable — likely interference.',
        `Variation ${(ratio*100).toFixed(0)}% of the mean field. Check for power cables / ESCs near the compass, or run Compass-Motor calibration.`)
    }
  }

  // ===== EKF =====
  const xkf = data.XKF4 || data.NKF4
  if (xkf && xkf.SV && xkf.SP) {
    const svMax = nanmax(xkf.SV), spMax = nanmax(xkf.SP)
    if (svMax < 0.5 && spMax < 0.5) add('EKF (state estimator)', 'Good', SUCCESS, 'EKF was confident throughout the flight.',
      `Velocity / position innovation peaks ${svMax.toFixed(2)} / ${spMax.toFixed(2)} (under 0.5 is healthy).`)
    else if (svMax < 1.0 && spMax < 1.0) add('EKF (state estimator)', 'Marginal', WARN, 'EKF saw moderate uncertainty at times.',
      `Innovation peaks vel ${svMax.toFixed(2)}, pos ${spMax.toFixed(2)}. Above 1.0 the EKF can refuse to arm.`)
    else add('EKF (state estimator)', 'Bad', DANGER, 'EKF flagged high uncertainty.',
      `Innovation peaks vel ${svMax.toFixed(2)}, pos ${spMax.toFixed(2)}.`)
  }

  // ===== Altitude =====
  const pos = data.POS
  if (pos && pos.Alt) {
    const alt = pos.Alt.filter(Number.isFinite)
    if (alt.length > 10) {
      const alt0 = median(alt.slice(0, 10))
      const agl = alt.map(a => a - alt0)
      const maxH = nanmax(agl), minH = nanmin(agl)
      let climb = 0
      const t = times.POS
      if (t && t.length === alt.length && t.length > 1) {
        for (let i = 1; i < t.length; i++) {
          const dt = t[i] - t[i-1]
          if (dt > 0) {
            const r = Math.abs((alt[i] - alt[i-1]) / dt)
            if (r > climb) climb = r
          }
        }
      }
      add('Altitude', 'Info', ACCENT,
        `Max height ${maxH.toFixed(1)} m AGL, lowest ${minH.toFixed(1)} m, peak vertical speed ${climb.toFixed(1)} m/s.`,
        `Heights are relative to the takeoff altitude. Vertical speed peaks above 8 m/s indicate aggressive throttle response.`)
    }
  }

  // ===== Attitude =====
  const att = data.ATT
  if (att && att.Roll && att.Pitch) {
    const peakR = nanmax(att.Roll.map(Math.abs))
    const peakP = nanmax(att.Pitch.map(Math.abs))
    const peak = Math.max(peakR, peakP)
    if (peak < 25) add('Attitude', 'Good', SUCCESS, `Gentle flight envelope (peak tilt ${peak.toFixed(0)}°).`,
      `Maximum roll ${peakR.toFixed(0)}°, pitch ${peakP.toFixed(0)}°.`)
    else if (peak < 45) add('Attitude', 'Info', ACCENT, `Moderate manoeuvres (peak tilt ${peak.toFixed(0)}°).`,
      `Roll ${peakR.toFixed(0)}°, pitch ${peakP.toFixed(0)}°. Normal sport flying.`)
    else add('Attitude', 'Marginal', WARN, `Aggressive tilt angles (peak ${peak.toFixed(0)}°).`,
      `Roll ${peakR.toFixed(0)}°, pitch ${peakP.toFixed(0)}°. Above 45° the drone needs more throttle just to stay level.`)
  }

  // ===== Motor balance (copter only) =====
  const rcou = data.RCOU
  if (rcou && (kind === 'copter' || kind === 'heli')) {
    const chKeys = Object.keys(rcou).filter(k => /^C\d+$/.test(k))
      .sort((a, b) => parseInt(a.slice(1)) - parseInt(b.slice(1))).slice(0, 8)
    if (chKeys.length >= 4) {
      const named = []
      for (const k of chKeys) {
        const a = rcou[k].filter(v => v > 1050 && v < 2000)
        if (a.length) named.push([k, nanmean(a)])
      }
      if (named.length >= 4) {
        const means = named.map(([, m]) => m)
        const spread = nanmax(means) - nanmin(means)
        const avg = means.reduce((a, b) => a + b, 0) / means.length
        let worstK = named[0][0], worstM = named[0][1], worstDelta = means[0] - avg
        for (const [k, m] of named) if (Math.abs(m - avg) > Math.abs(worstDelta)) { worstK = k; worstM = m; worstDelta = m - avg }
        const sign = worstDelta >= 0 ? '+' : ''
        const role = worstDelta > 0 ? 'working harder' : 'underloaded / weaker'
        const worstStr = `${worstK} (${sign}${worstDelta.toFixed(0)} µs vs avg — ${role})`
        if (spread < 60) add('Motor balance', 'Good', SUCCESS,
          `Motors well balanced (spread ${spread.toFixed(0)} µs across ${means.length} motors).`,
          `Average PWM ${avg.toFixed(0)} µs. Largest deviation: ${worstStr}.`)
        else if (spread < 150) add('Motor balance', 'Marginal', WARN,
          `Motors slightly uneven (spread ${spread.toFixed(0)} µs). Worst: ${worstK}.`,
          `Outlier: ${worstStr}. Check that motor's prop, bell, and arm.`)
        else add('Motor balance', 'Bad', DANGER,
          `Motor output spread is large (${spread.toFixed(0)} µs). Worst: ${worstK}.`,
          `${worstStr}. Inspect ${worstK} first.`)
      }
    }
  }

  // ===== Power used =====
  let batBlock = null
  for (const k of ['BAT', 'BAT1', 'BATT']) if (data[k]) { batBlock = data[k]; break }
  if (batBlock && batBlock.CurrTot) {
    const ct = batBlock.CurrTot.filter(v => v >= 0)
    if (ct.length) {
      const mah = nanmax(ct)
      add('Power used', 'Info', ACCENT, `Consumed ${mah.toFixed(0)} mAh during the flight.`,
        `Compare to your pack capacity: try to land before using ~80%.`)
    }
  }

  // ===== RC link =====
  const rcin = data.RCIN
  if (rcin) {
    const c1 = rcin.C1 || rcin.Chan1
    if (c1) {
      let lo = 0, ok = 0
      for (const v of c1) { if (v < 900) lo++; else if (v >= 900) ok++ }
      if (ok) {
        const pct = lo / (lo + ok) * 100
        if (pct === 0) add('RC link', 'Good', SUCCESS, 'RC signal stable for the entire flight.', '')
        else if (pct < 1) add('RC link', 'Marginal', WARN, `${lo} brief RC dropouts (${pct.toFixed(1)}% of samples).`,
          'A few short losses are common at long range.')
        else add('RC link', 'Bad', DANGER, `RC signal lost ${pct.toFixed(1)}% of the time.`,
          'Significant link issues — check transmitter antenna, receiver placement.')
      }
    }
  }

  // ===== Autopilot CPU (PM.MaxT) =====
  const pm = data.PM
  if (pm && pm.MaxT) {
    const maxT = pm.MaxT.filter(v => v > 0)
    if (maxT.length) {
      const peakUs = nanmax(maxT), avgUs = nanmean(maxT)
      if (peakUs < 2500) add('Autopilot CPU', 'Good', SUCCESS, `Main loop ran on time (peak ${peakUs.toFixed(0)} µs).`,
        'Flight controller had headroom throughout the flight.')
      else if (peakUs < 4000) add('Autopilot CPU', 'Marginal', WARN,
        `Occasional loop overruns (peak ${peakUs.toFixed(0)} µs, avg ${avgUs.toFixed(0)}).`,
        'If this gets worse, consider reducing logging rate.')
      else add('Autopilot CPU', 'Bad', DANGER,
        `Loop overruns are significant (peak ${peakUs.toFixed(0)} µs).`,
        'Reduce logging, disable unused sensors.')
    }
  }

  // ===== IMU temperature =====
  const imu = data.IMU
  if (imu && imu.T) {
    const T = imu.T.filter(v => v > -40 && v < 120)
    if (T.length) {
      const tMin = nanmin(T), tMax = nanmax(T)
      const spread = tMax - tMin
      if (spread < 5) add('IMU temperature', 'Good', SUCCESS,
        `IMU stayed thermally stable (${tMin.toFixed(0)}–${tMax.toFixed(0)} °C).`, '')
      else if (spread < 15) add('IMU temperature', 'Info', ACCENT,
        `IMU temperature swung ${spread.toFixed(0)} °C (${tMin.toFixed(0)}–${tMax.toFixed(0)} °C).`,
        'Mild drift is normal during a flight.')
      else add('IMU temperature', 'Marginal', WARN,
        `Large IMU temperature swing (${spread.toFixed(0)} °C).`,
        'Big temperature shifts shift gyro bias.')
    }
  }

  // ===== Takeoff health (plane only) =====
  const params = parsed.params || {}
  if (kind === 'plane') {
    const modeMsgs = data.MODE, modeT = times.MODE
    const ctun = data.CTUN, ctunT = times.CTUN
    const attT = times.ATT
    if (modeMsgs && modeMsgs.Mode && modeT && att && attT && ctun && ctunT) {
      const takeoffs = []
      for (let i = 0; i < modeMsgs.Mode.length; i++) {
        if ((modeMsgs.Mode[i] | 0) === 13) {
          const tIn = modeT[i]
          const tOut = i + 1 < modeT.length ? modeT[i + 1] : modeT[modeT.length - 1] + 30
          if (tOut - tIn > 1) takeoffs.push([tIn, tOut])
        }
      }
      if (takeoffs.length) {
        const ta = attT, roll = att.Roll || [], desr = att.DesRoll || []
        const tc = ctunT, tho = ctun.ThO || []
        const gpsT = times.GPS, gpsSpd = (data.GPS?.Spd || data.GPS?.GroundSpeed)
        const t0 = parsed.t_start || 0

        const pSlew = params.TKOFF_THR_SLEW
        const pRotSpd = params.TKOFF_ROTATE_SPD
        const pArspUse = params.ARSPD_USE
        const pAspdMin = params.AIRSPEED_MIN
        const pLvlPit = params.TKOFF_LVL_PITCH
        const pRddr = params.KFF_RDDRMIX

        const lines = []
        let worst = 0
        let idx = 0
        for (const [ti, tf] of takeoffs) {
          idx++
          const winA = ta.map((t, i) => (t >= ti && t <= tf) ? i : -1).filter(i => i >= 0)
          const winC = tc.map((t, i) => (t >= ti && t <= tf) ? i : -1).filter(i => i >= 0)
          if (winA.length < 5 || winC.length < 5) continue

          const thoW = winC.map(i => tho[i])
          const tcW  = winC.map(i => tc[i])
          let above10 = -1, above80 = -1, above60 = -1
          for (let i = 0; i < thoW.length; i++) {
            if (thoW[i] > 10 && above10 < 0) above10 = i
            if (thoW[i] > 60 && above60 < 0) above60 = i
            if (thoW[i] > 80 && above80 < 0) above80 = i
          }
          const rampS = (above10 >= 0 && above80 >= 0) ? tcW[above80] - tcW[above10] : null

          let peakDev = 0
          if (roll.length === desr.length) {
            for (const i of winA) {
              const d = Math.abs(roll[i] - desr[i])
              if (d > peakDev) peakDev = d
            }
          }

          let rotateSpd = null
          if (gpsT && gpsSpd && above60 >= 0) {
            const tRot = tcW[above60]
            // nearest GPS sample
            let bj = 0, bd = Infinity
            for (let j = 0; j < gpsT.length; j++) {
              const d = Math.abs(gpsT[j] - tRot)
              if (d < bd) { bd = d; bj = j }
            }
            rotateSpd = gpsSpd[bj]
          }

          const wallDate = new Date((t0 + ti) * 1000)
          const wall = wallDate.toLocaleTimeString('en-GB', { hour12: false })
          const bits = [`<b>Takeoff #${idx}</b> at ${wall}`]
          if (rampS != null) {
            if (rampS < 0.3) { worst = Math.max(worst, 2); bits.push(`throttle slammed 0→80% in <b style="color:${DANGER}">${rampS.toFixed(2)}s</b> (torque roll risk)`) }
            else if (rampS < 1.0) { worst = Math.max(worst, 1); bits.push(`throttle ramp ${rampS.toFixed(2)}s (marginal)`) }
            else bits.push(`throttle ramp ${rampS.toFixed(2)}s`)
          }
          if (rotateSpd != null && pAspdMin) {
            const margin = rotateSpd - Number(pAspdMin)
            if (margin < 0) { worst = Math.max(worst, 2); bits.push(`rotated at <b style="color:${DANGER}">${rotateSpd.toFixed(1)} m/s</b> — ${Math.abs(margin).toFixed(1)} m/s BELOW stall (${Number(pAspdMin).toFixed(0)})`) }
            else if (margin < 3) { worst = Math.max(worst, 1); bits.push(`rotated at ${rotateSpd.toFixed(1)} m/s (only ${margin.toFixed(1)} m/s stall margin)`) }
            else bits.push(`rotated at ${rotateSpd.toFixed(1)} m/s (${margin >= 0 ? '+' : ''}${margin.toFixed(1)} m/s vs stall)`)
          }
          if (peakDev > 90) { worst = Math.max(worst, 2); bits.push(`Roll diverged <b style="color:${DANGER}">${peakDev.toFixed(0)}°</b> from command — likely tumble`) }
          else if (peakDev > 30) { worst = Math.max(worst, 1); bits.push(`Roll diverged ${peakDev.toFixed(0)}° from command`) }
          lines.push(bits.join(' · '))
        }

        const paramWarns = []
        if (pSlew != null && Number(pSlew) < 1) { worst = Math.max(worst, 2); paramWarns.push(`TKOFF_THR_SLEW=${Number(pSlew).toFixed(1)} (set to ~50 = 2s ramp)`) }
        if (pRotSpd != null && Number(pRotSpd) < 1) { worst = Math.max(worst, 1); paramWarns.push(`TKOFF_ROTATE_SPD=${Number(pRotSpd).toFixed(1)} (set to ≥ AIRSPEED_MIN + 3 for ground, 0 for hand-launch)`) }
        if (pArspUse != null && Number(pArspUse) === 0 && pAspdMin) paramWarns.push(`ARSPD_USE=0 (no airspeed sensor — launch into the wind!)`)
        if (pLvlPit != null && Number(pLvlPit) > 14) { worst = Math.max(worst, 1); paramWarns.push(`TKOFF_LVL_PITCH=${Number(pLvlPit).toFixed(0)}° (drop to 12° for safer climb)`) }
        if (pRddr != null && Number(pRddr) < 0.5) paramWarns.push(`KFF_RDDRMIX=${Number(pRddr).toFixed(2)} (raise to 0.5–0.7 to fight torque roll)`)

        let detailHtml = lines.join('<br/>')
        if (paramWarns.length) detailHtml += `${lines.length ? '<br/><br/>' : ''}<b>Param suggestions:</b><br/>• ${paramWarns.join('<br/>• ')}`
        if (lines.length || paramWarns.length) {
          const verdict = worst === 0 ? 'Good' : (worst === 1 ? 'Marginal' : 'Bad')
          const color = worst === 0 ? SUCCESS : (worst === 1 ? WARN : DANGER)
          add('Takeoff health', verdict, color,
            `${takeoffs.length} TAKEOFF mode entry / entries analysed.`,
            detailHtml)
        }
      }
    }
  }

  // ===== PID tracking =====
  const pidStats = analyzePidTracking(parsed)
  if (Object.keys(pidStats).length) {
    let worstV = 'good'
    const rank = { good: 0, 'no-command': 0, lagging: 1, loose: 1, oscillating: 2 }
    const lines = []
    for (const axis of ['roll', 'pitch', 'yaw']) {
      const s = pidStats[axis]; if (!s) continue
      if ((rank[s.verdict] || 0) > (rank[worstV] || 0)) worstV = s.verdict
      const badge = { good: SUCCESS, loose: WARN, lagging: WARN, oscillating: DANGER, 'no-command': TEXT_DIM }[s.verdict]
      if (s.verdict === 'no-command') {
        lines.push(`<b style="color:${badge}">${axis.toUpperCase()}</b> · <span style="color:${TEXT_DIM}">${s.hint}</span>`)
      } else {
        lines.push(`<b style="color:${badge}">${axis.toUpperCase()}</b> · RMS err ${s.rms_err.toFixed(1)}° · peak ${s.peak_err.toFixed(0)}° · err osc ${s.osc_hz.toFixed(1)} Hz · lag ${s.lag_ms.toFixed(0)} ms<br/><span style="color:${TEXT_DIM}">  ${s.hint}</span>`)
      }
    }
    if (lines.length) {
      const verdictLbl = { good: 'Good', loose: 'Marginal', lagging: 'Marginal', oscillating: 'Bad', 'no-command': 'Good' }[worstV]
      const verdictClr = { good: SUCCESS, loose: WARN, lagging: WARN, oscillating: DANGER, 'no-command': SUCCESS }[worstV]
      const tracked = Object.values(pidStats).filter(s => s.verdict !== 'no-command').length
      add('PID tracking', verdictLbl, verdictClr,
        `Attitude controller — ${worstV} tracking (${tracked} axis/axes actively commanded).`,
        lines.join('<br/>'))
    }
  }

  // ===== CPU loop overruns (PM.MaxT vs frame-specific budget) =====
  if (pm) {
    const loopBudget = kind === 'copter' ? 2500 : 20000
    const maxT = pm.MaxT
    const nLon = pm.NLon || pm.nlon || pm.NLoop
    const load = pm.Load
    if (maxT && maxT.length) {
      const m = nanmax(maxT)
      const ratio = m / loopBudget
      const nLong = nLon ? nLon.reduce((a, b) => a + b, 0) | 0 : 0
      const loadPct = load && load.length ? nanmax(load) / 10 : null
      let extra = nLong ? ` · ${nLong} long-loop event(s)` : ''
      if (loadPct != null) extra += ` · peak CPU load ${loadPct.toFixed(0)}%`
      if (ratio < 1.2) add('CPU loop overruns', 'Good', SUCCESS,
        `Max loop ${m.toFixed(0)} µs (budget ${loopBudget} µs).${extra}`,
        'Autopilot is keeping up comfortably.')
      else if (ratio < 2.0) add('CPU loop overruns', 'Marginal', WARN,
        `Max loop ${m.toFixed(0)} µs — ${ratio.toFixed(1)}× the ${loopBudget} µs budget.${extra}`,
        'Occasional overruns. Usually slow SD card stalls on log writes.')
      else add('CPU loop overruns', 'Bad', DANGER,
        `Max loop ${m.toFixed(0)} µs — ${ratio.toFixed(1)}× the ${loopBudget} µs budget.${extra}`,
        'Significant overruns mean the autopilot is briefly "blind". Primary fix: replace the SD card and lower LOG_BITMASK.')
    }
  }

  // ===== Flight modes summary =====
  const modeBlock = data.MODE
  if (modeBlock && modeBlock.Mode) {
    const uniq = []
    for (const m of modeBlock.Mode) if (uniq[uniq.length - 1] !== m) uniq.push(m)
    if (uniq.length) add('Flight modes', 'Info', ACCENT,
      `${uniq.length} mode change(s): ${uniq.join(' → ')}`, '')
  }

  if (!items.length) add('No data', 'Info', TEXT_DIM,
    "Couldn't run the auto-review.",
    'Standard message types (VIBE, GPS, BAT, MAG) were not found in this log.')

  return items
}
