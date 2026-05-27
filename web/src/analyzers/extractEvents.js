// Extract notable timeline events from a parsed ArduPilot log:
// mode changes, arm/disarm, failsafes, RTL triggers, GPS fix changes,
// and key warning MSGs. Each event has { t, label, kind, color }.
//
// `t` is seconds relative to log start. `kind` is one of:
//   'mode'    — mode change (e.g. MANUAL → AUTO)
//   'arm'     — arm
//   'disarm'  — disarm
//   'warn'    — generic warning from MSG
//   'failsafe'— failsafe trigger
//   'land'    — landing detected
// Colors give the timeline strip a clear visual language.

const COLORS = {
  mode:      '#3da9fc',
  arm:       '#34d399',
  disarm:    '#7d8aa0',
  warn:      '#f0b75d',
  failsafe:  '#f87171',
  land:      '#a78bfa',
}

// ArduPilot mode numbers per vehicle. We just use the mode number to label
// "MODE n" when we don't recognize it.
const MODE_NAMES = {
  // Plane (vehicle == 1)
  plane: {
    0:'MANUAL',1:'CIRCLE',2:'STABILIZE',3:'TRAINING',4:'ACRO',5:'FBWA',6:'FBWB',7:'CRUISE',
    8:'AUTOTUNE',10:'AUTO',11:'RTL',12:'LOITER',13:'TAKEOFF',14:'AVOID_ADSB',15:'GUIDED',
    17:'QSTABILIZE',18:'QHOVER',19:'QLOITER',20:'QLAND',21:'QRTL',22:'QAUTOTUNE',23:'QACRO',24:'THERMAL',
  },
  // Copter (vehicle == 2)
  copter: {
    0:'STABILIZE',1:'ACRO',2:'ALT_HOLD',3:'AUTO',4:'GUIDED',5:'LOITER',6:'RTL',7:'CIRCLE',
    9:'LAND',11:'DRIFT',13:'SPORT',14:'FLIP',15:'AUTOTUNE',16:'POSHOLD',17:'BRAKE',18:'THROW',
    19:'AVOID_ADSB',20:'GUIDED_NOGPS',21:'SMART_RTL',22:'FLOWHOLD',23:'FOLLOW',24:'ZIGZAG',
    25:'SYSTEMID',26:'AUTOROTATE',27:'AUTO_RTL',
  },
  rover: {
    0:'MANUAL',1:'ACRO',3:'STEERING',4:'HOLD',5:'LOITER',6:'FOLLOW',7:'SIMPLE',10:'AUTO',
    11:'RTL',12:'SMART_RTL',15:'GUIDED',16:'INITIALISING',
  },
}

function vehicleKey(vt) {
  if (vt === 1) return 'plane'
  if (vt === 2) return 'copter'
  if (vt === 10) return 'rover'
  if (vt === 12) return 'sub'
  return 'plane'
}

export function extractEvents(parsed) {
  if (!parsed?.data) return []
  const t0 = parsed.t_start || 0
  const out = []
  const data = parsed.data, times = parsed.times
  const vehKey = vehicleKey(parsed.vehicleType)
  const modeMap = MODE_NAMES[vehKey] || {}

  // MODE changes
  const mode = data.MODE, mt = times.MODE
  if (mode && mt?.length) {
    const arr = mode.Mode || mode.ModeNum || mode.M
    if (arr) {
      let last = null
      for (let i = 0; i < arr.length; i++) {
        const m = arr[i]
        if (m !== last) {
          out.push({
            t: Math.max(0, mt[i] - t0),
            label: modeMap[m] || `MODE ${m}`,
            kind: 'mode',
            color: COLORS.mode,
          })
          last = m
        }
      }
    }
  }

  // Arm / disarm via EV (event) messages
  // EV.Id codes (ArduPilot): 10 = ARMED, 11 = DISARMED, 17 = LAND_COMPLETE
  const ev = data.EV, evT = times.EV
  if (ev?.Id && evT?.length) {
    for (let i = 0; i < ev.Id.length; i++) {
      const id = ev.Id[i]
      if (id === 10) out.push({ t: evT[i] - t0, label: 'ARMED',   kind: 'arm',    color: COLORS.arm })
      else if (id === 11) out.push({ t: evT[i] - t0, label: 'DISARMED', kind: 'disarm', color: COLORS.disarm })
      else if (id === 18 || id === 17) out.push({ t: evT[i] - t0, label: 'LANDED', kind: 'land', color: COLORS.land })
    }
  }

  // ERR / failsafe entries — Subsys 5 = failsafe radio, Subsys 6 = batt, Subsys 12 = GCS
  const err = data.ERR, errT = times.ERR
  if (err?.Subsys && errT?.length) {
    for (let i = 0; i < err.Subsys.length; i++) {
      const sub = err.Subsys[i], code = err.ECode ? err.ECode[i] : null
      if (code === 0) continue        // 0 == cleared
      let label = null
      if (sub === 5)  label = 'RADIO FS'
      else if (sub === 6)  label = 'BATTERY FS'
      else if (sub === 12) label = 'GCS FS'
      else if (sub === 11) label = 'EKF FS'
      else if (sub === 17) label = 'TERRAIN FS'
      if (label) out.push({ t: errT[i] - t0, label, kind: 'failsafe', color: COLORS.failsafe })
    }
  }

  // Notable MSG strings
  const msg = data.MSG, msgT = times.MSG
  if (msg?.Message && msgT?.length) {
    const RX = /(FAILSAFE|LAND COMPLETE|TAKEOFF|CRASH|GPS GLITCH|RTL|EKF)/i
    for (let i = 0; i < msg.Message.length; i++) {
      const s = msg.Message[i]
      if (typeof s !== 'string') continue
      const m = s.match(RX)
      if (!m) continue
      const upper = m[1].toUpperCase()
      const kind = upper.includes('FAILSAFE') || upper.includes('CRASH') ? 'failsafe' : 'warn'
      out.push({
        t: msgT[i] - t0,
        label: s.slice(0, 36),
        kind,
        color: kind === 'failsafe' ? COLORS.failsafe : COLORS.warn,
      })
    }
  }

  // Sort by time; clamp negatives
  out.sort((a, b) => a.t - b.t)
  return out
}

// Extract continuous mode segments — used by the timeline strip to paint
// colored bands behind the event dots. Returns:
//   [{ t0, t1, mode, label, color }]
const MODE_COLORS = {
  // ArduPilot-ish color buckets — easier on the eye than 30 unique hues
  manual:   '#3da9fc',
  stabilize:'#5fbcff',
  acro:     '#7dd3fc',
  auto:     '#34d399',
  loiter:   '#22d3ee',
  guided:   '#a78bfa',
  rtl:      '#facc15',
  land:     '#fb923c',
  takeoff:  '#f0b75d',
  failsafe: '#f87171',
  unknown:  '#525d72',
}
function modeBucket(name) {
  const n = (name || '').toUpperCase()
  if (/RTL/.test(n))               return 'rtl'
  if (/LAND/.test(n))              return 'land'
  if (/TAKEOFF/.test(n))           return 'takeoff'
  if (/AUTO/.test(n))              return 'auto'
  if (/LOITER|POSHOLD|HOLD|BRAKE/.test(n)) return 'loiter'
  if (/GUIDED/.test(n))            return 'guided'
  if (/ACRO|SPORT/.test(n))        return 'acro'
  if (/STAB|FBWA|FBWB|TRAINING|ALT_HOLD|CRUISE/.test(n)) return 'stabilize'
  if (/MANUAL/.test(n))            return 'manual'
  return 'unknown'
}
export function extractModeBands(parsed) {
  if (!parsed?.data) return []
  const t0 = parsed.t_start || 0
  const duration = parsed.duration || 0
  const vehKey = vehicleKey(parsed.vehicleType)
  const modeMap = MODE_NAMES[vehKey] || {}
  const mode = parsed.data.MODE, mt = parsed.times.MODE
  if (!mode?.Mode && !mode?.ModeNum && !mode?.M) return []
  const arr = mode.Mode || mode.ModeNum || mode.M
  if (!arr?.length || !mt?.length) return []
  const bands = []
  let last = null, lastT = 0
  for (let i = 0; i < arr.length; i++) {
    const m = arr[i]
    if (m === last) continue
    const t = Math.max(0, mt[i] - t0)
    if (last != null) bands.push({
      t0: lastT, t1: t,
      mode: last,
      label: modeMap[last] || `MODE ${last}`,
      color: MODE_COLORS[modeBucket(modeMap[last] || '')],
    })
    last = m; lastT = t
  }
  // Final segment runs to end-of-log
  if (last != null) bands.push({
    t0: lastT, t1: duration,
    mode: last,
    label: modeMap[last] || `MODE ${last}`,
    color: MODE_COLORS[modeBucket(modeMap[last] || '')],
  })
  return bands
}
