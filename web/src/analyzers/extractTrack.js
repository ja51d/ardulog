// Port of _extract_track() from app.py. Pulls a clean lat/lng/alt+time
// track from POS / GPS / GPS2 messages with the same sanity filters.

export function extractTrack(parsed) {
  if (!parsed) return { coords: [], alts: [], trel: [] }
  const data = parsed.data || {}
  const times = parsed.times || {}
  const t0 = parsed.t_start || 0

  for (const mt of ['POS', 'GPS', 'GPS2']) {
    const block = data[mt]
    if (!block) continue
    const latKey = ['Lat', 'lat'].find(k => k in block)
    const lngKey = ['Lng', 'Lon', 'lng', 'lon'].find(k => k in block)
    if (!latKey || !lngKey) continue

    let lats = (block[latKey] || []).map(Number)
    let lngs = (block[lngKey] || []).map(Number)
    let alts = (block.Alt || lats.map(() => 0)).map(Number)
    let ts   = (times[mt] || []).map(Number)
    if (ts.length !== lats.length) ts = lats.map(() => 0)
    if (!lats.length) continue

    // Some firmware stores lat/lng as 1e7-scaled integers
    let maxAbs = 0
    for (const v of lats) if (Math.abs(v) > maxAbs) maxAbs = Math.abs(v)
    if (maxAbs > 200) {
      lats = lats.map(v => v / 1e7)
      lngs = lngs.map(v => v / 1e7)
    }

    // Build a mask: nonzero coords + GPS fix sanity
    const mask = []
    const status = block.Status, nsats = block.NSats
    for (let i = 0; i < lats.length; i++) {
      let ok = Math.abs(lats[i]) > 0.0001 && Math.abs(lngs[i]) > 0.0001
      if (ok && mt.startsWith('GPS')) {
        if (status && status[i] != null && status[i] < 3) ok = false
        if (nsats && nsats[i] != null && nsats[i] < 4) ok = false
      }
      mask.push(ok)
    }
    let kLats = [], kLngs = [], kAlts = [], kTs = []
    for (let i = 0; i < lats.length; i++) {
      if (mask[i]) { kLats.push(lats[i]); kLngs.push(lngs[i]); kAlts.push(alts[i]); kTs.push(ts[i]) }
    }
    if (kLats.length < 2) continue

    // Drop wild jumps relative to the median (cold start, RTCM glitches)
    const medLat = median(kLats), medLng = median(kLngs)
    const lat2 = [], lng2 = [], alt2 = [], ts2 = []
    for (let i = 0; i < kLats.length; i++) {
      if (Math.abs(kLats[i] - medLat) < 0.01 && Math.abs(kLngs[i] - medLng) < 0.01) {
        lat2.push(kLats[i]); lng2.push(kLngs[i]); alt2.push(kAlts[i]); ts2.push(kTs[i])
      }
    }
    if (lat2.length < 2) continue

    // Downsample to ~3000 points
    let step = 1
    if (lat2.length > 3000) step = Math.floor(lat2.length / 3000)
    const coords = [], alts3 = [], trel = []
    for (let i = 0; i < lat2.length; i += step) {
      coords.push([lat2[i], lng2[i]])
      alts3.push(alt2[i])
      trel.push(ts2[i] > 0 ? ts2[i] - t0 : 0)
    }
    return { coords, alts: alts3, trel }
  }
  return { coords: [], alts: [], trel: [] }
}

function median(arr) {
  const a = [...arr].sort((x, y) => x - y)
  if (!a.length) return 0
  const m = a.length >> 1
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2
}
