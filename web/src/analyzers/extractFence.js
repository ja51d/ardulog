// Pull geofence polygons from FNCE / POLY messages in ArduPilot logs.
// Modern AP uses FNCE for inclusion / exclusion polygons + circles.
// Returns:
//   { polygons: [{kind, points: [[lat,lng], ...]}], circles: [{kind, lat,lng, radius}] }
// Each polygon is closed (last point != first → we don't auto-close).

export function extractFence(parsed) {
  if (!parsed?.data) return { polygons: [], circles: [] }
  const data = parsed.data

  const polygons = []
  const circles = []

  // FNCE: Type=0 (inclusion polygon), 1 (exclusion polygon),
  // 2 (inclusion circle), 3 (exclusion circle), 4 (return point).
  // Fields: Tot (total), Seq (point index), Type, Lat, Lng, Radius
  const f = data.FNCE
  if (f?.Lat && f.Lng && f.Type != null && f.Seq != null) {
    const n = f.Lat.length
    let currentPoly = null
    for (let i = 0; i < n; i++) {
      let lat = Number(f.Lat[i]), lng = Number(f.Lng[i])
      if (Math.abs(lat) > 200) { lat /= 1e7; lng /= 1e7 }
      if (Math.abs(lat) < 1e-6 && Math.abs(lng) < 1e-6) continue
      const type = Number(f.Type[i])
      const seq = Number(f.Seq[i])
      const radius = f.Radius ? Number(f.Radius[i]) : 0

      if (type === 2 || type === 3) {
        // Circle
        circles.push({
          kind: type === 2 ? 'inclusion' : 'exclusion',
          lat, lng, radius,
        })
        continue
      }
      if (type === 4) continue  // return point — skip

      // Polygon point (type 0 = inclusion, 1 = exclusion)
      if (seq === 0 || !currentPoly || currentPoly.kind !== (type === 0 ? 'inclusion' : 'exclusion')) {
        currentPoly = { kind: type === 0 ? 'inclusion' : 'exclusion', points: [] }
        polygons.push(currentPoly)
      }
      currentPoly.points.push([lat, lng])
    }
  }

  // Older logs: POLY message (basic polygon)
  const p = data.POLY
  if (p?.Lat && p.Lng) {
    const n = p.Lat.length
    const pts = []
    for (let i = 0; i < n; i++) {
      let lat = Number(p.Lat[i]), lng = Number(p.Lng[i])
      if (Math.abs(lat) > 200) { lat /= 1e7; lng /= 1e7 }
      if (Math.abs(lat) < 1e-6 && Math.abs(lng) < 1e-6) continue
      pts.push([lat, lng])
    }
    if (pts.length >= 3) polygons.push({ kind: 'inclusion', points: pts })
  }

  return { polygons, circles }
}
