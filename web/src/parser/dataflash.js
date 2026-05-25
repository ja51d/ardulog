// Minimal ArduPilot DataFlash log parser (.bin).
//
// Format: a stream of messages, each prefixed with header bytes
//   0xA3 0x95 <type> <payload...>
// Two special types define the format of every other message:
//   FMT  (type 0x80) — declares a msg type: type / length / name / format / labels
//   FMTU            — unit/multiplier metadata (we ignore for now)
//
// The "format" field is a series of single-char codes that describe each
// payload field. See:
//   https://ardupilot.org/copter/docs/logmessages.html
//
// This is intentionally lean — we extract enough to support frame
// detection, parameter readout, message counts, and per-message
// timestamps. Field-level analysis can build on top.

const HEAD1 = 0xa3
const HEAD2 = 0x95
const FMT_TYPE = 0x80

// Type code → (size in bytes, decode function returning value + new offset)
function makeDecoders() {
  const td = new TextDecoder('utf-8')
  return {
    b: { size: 1, decode: (v, o) => [v.getInt8(o),                    o + 1] },
    B: { size: 1, decode: (v, o) => [v.getUint8(o),                   o + 1] },
    h: { size: 2, decode: (v, o) => [v.getInt16(o, true),             o + 2] },
    H: { size: 2, decode: (v, o) => [v.getUint16(o, true),            o + 2] },
    i: { size: 4, decode: (v, o) => [v.getInt32(o, true),             o + 4] },
    I: { size: 4, decode: (v, o) => [v.getUint32(o, true),            o + 4] },
    f: { size: 4, decode: (v, o) => [v.getFloat32(o, true),           o + 4] },
    d: { size: 8, decode: (v, o) => [v.getFloat64(o, true),           o + 8] },
    q: { size: 8, decode: (v, o) => [Number(v.getBigInt64(o, true)),  o + 8] },
    Q: { size: 8, decode: (v, o) => [Number(v.getBigUint64(o, true)), o + 8] },
    n: { size: 4, decode: (v, o) => [readZStr(v, o, 4), o + 4] },
    N: { size: 16, decode: (v, o) => [readZStr(v, o, 16), o + 16] },
    Z: { size: 64, decode: (v, o) => [readZStr(v, o, 64), o + 64] },
    c: { size: 2, decode: (v, o) => [v.getInt16(o, true) * 0.01,      o + 2] },
    C: { size: 2, decode: (v, o) => [v.getUint16(o, true) * 0.01,     o + 2] },
    e: { size: 4, decode: (v, o) => [v.getInt32(o, true) * 0.01,      o + 4] },
    E: { size: 4, decode: (v, o) => [v.getUint32(o, true) * 0.01,     o + 4] },
    L: { size: 4, decode: (v, o) => [v.getInt32(o, true) * 1e-7,      o + 4] },
    M: { size: 1, decode: (v, o) => [v.getUint8(o),                   o + 1] },
    a: { size: 64, decode: (v, o) => {
      const arr = []
      for (let i = 0; i < 32; i++) arr.push(v.getInt16(o + i * 2, true))
      return [arr, o + 64]
    }},
  }

  function readZStr(view, off, len) {
    const bytes = new Uint8Array(view.buffer, view.byteOffset + off, len)
    let end = bytes.indexOf(0); if (end < 0) end = len
    return td.decode(bytes.subarray(0, end))
  }
}

const DECODERS = makeDecoders()

function totalSize(fmtStr) {
  let s = 0
  for (const ch of fmtStr) {
    const d = DECODERS[ch]
    if (!d) return -1
    s += d.size
  }
  return s
}

/**
 * Parse a .bin DataFlash log.
 *
 * @param {ArrayBuffer} buffer
 * @param {(progress: {bytesRead: number, total: number, lastType: string}) => void} [onProgress]
 * @returns {Promise<{
 *   data: Record<string, Record<string, number[]>>,
 *   times: Record<string, number[]>,
 *   count: number,
 *   duration: number,
 *   t_start: number,
 *   t_end: number,
 *   vehicle_type: number | null,
 *   params: Record<string, number>,
 *   messages_meta: Record<string, {labels: string[], format: string}>
 * }>}
 */
export async function parseDataFlash(buffer, onProgress) {
  const view = new DataView(buffer)
  const total = buffer.byteLength
  // type → { name, fmt, labels }
  const formats = new Map()
  // mapped message data: type name -> field name -> array
  const data = {}
  const times = {}        // type -> [unix seconds]; uses TimeUS field if present
  const params = {}
  let count = 0
  let t_start = null
  let t_end = null
  let vehicleType = null
  // Boot time anchor for converting TimeUS (us since boot) → unix epoch.
  // The .bin doesn't include real-world clock; we use parse-time clock as
  // a placeholder. The desktop app does the same when GPS time isn't fused.
  const tBootEpoch = Date.now() / 1000

  let off = 0
  let lastReport = 0

  while (off + 3 < total) {
    if (view.getUint8(off) !== HEAD1 || view.getUint8(off + 1) !== HEAD2) {
      // Re-sync: scan forward for the next header pair.
      off += 1; continue
    }
    const type = view.getUint8(off + 2)
    const payloadStart = off + 3

    if (type === FMT_TYPE) {
      // FMT has a fixed layout
      if (payloadStart + 86 > total) break
      const t = view.getUint8(payloadStart)
      const len = view.getUint8(payloadStart + 1)
      const name = DECODERS.n.decode(view, payloadStart + 2)[0]
      const fmt = DECODERS.N.decode(view, payloadStart + 6)[0]
      const labels = DECODERS.Z.decode(view, payloadStart + 22)[0]
      formats.set(t, {
        name,
        fmt,
        labels: labels.split(',').filter(Boolean),
        size: len - 3, // payload size (len includes 3 header bytes)
      })
      off = payloadStart + 86
      count++
      continue
    }

    const f = formats.get(type)
    if (!f) {
      // Unknown type before its FMT — skip a byte and resync
      off += 1; continue
    }
    if (payloadStart + f.size > total) break

    // Decode the payload
    const row = {}
    let p = payloadStart
    for (let i = 0; i < f.fmt.length; i++) {
      const code = f.fmt[i]
      const dec = DECODERS[code]
      if (!dec) { p += 1; continue }
      const [val, next] = dec.decode(view, p)
      row[f.labels[i] || `f${i}`] = val
      p = next
    }

    // Store every numeric field by type
    let bucket = data[f.name]
    if (!bucket) bucket = data[f.name] = {}
    for (const k of Object.keys(row)) {
      const v = row[k]
      if (typeof v === 'number') {
        if (!bucket[k]) bucket[k] = []
        bucket[k].push(v)
      }
    }

    // Per-row timestamp via TimeUS if present
    if (row.TimeUS != null) {
      const t = tBootEpoch + row.TimeUS / 1e6
      if (t_start == null) t_start = t
      t_end = t
      let tarr = times[f.name]
      if (!tarr) tarr = times[f.name] = []
      tarr.push(t)
    }

    // Specials
    if (f.name === 'PARM' && row.Name) {
      params[row.Name] = row.Value
    }
    if (f.name === 'MSG' && typeof row.Message === 'string') {
      // ArduPilot logs vehicle type in startup banner: e.g. "ArduPlane V4.5.0"
      const m = row.Message.match(/Ardu(Plane|Copter|Rover|Sub)/i)
      if (m && vehicleType == null) {
        vehicleType = ({ plane: 1, copter: 2, rover: 10, sub: 12 })[m[1].toLowerCase()]
      }
    }

    off = p
    count++

    if (onProgress && (count - lastReport) > 5000) {
      lastReport = count
      onProgress({ bytesRead: off, total, lastType: f.name })
      // Yield to UI thread so progress updates can render
      await new Promise(r => setTimeout(r, 0))
    }
  }

  // Build messages_meta for downstream UI
  const messages_meta = {}
  for (const f of formats.values()) {
    messages_meta[f.name] = { labels: f.labels, format: f.fmt }
  }

  if (t_start == null) { t_start = tBootEpoch; t_end = tBootEpoch }

  return {
    data, times, count,
    duration: t_end - t_start,
    t_start, t_end,
    vehicle_type: vehicleType,
    params,
    messages_meta,
  }
}
