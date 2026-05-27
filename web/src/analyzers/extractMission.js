// Pull mission waypoints from CMD messages in ArduPilot logs.
// CMD message fields: TimeUS, CTot, CNum, CId, Prm1..Prm4, Lat, Lng, Alt, Frame.
// CId is the MAV_CMD code — we keep position-bearing commands only.
//
// Returns { waypoints: [{ idx, lat, lng, alt, cmd, label }], home: {lat,lng,alt} }
// or { waypoints: [], home: null } if no mission is present.

// Subset of MAV_CMD codes (we only care about the position-bearing ones)
const CMD_LABELS = {
  16:  'WP',          // NAV_WAYPOINT
  17:  'LOITER',      // NAV_LOITER_UNLIM
  18:  'LOITER N',    // NAV_LOITER_TURNS
  19:  'LOITER T',    // NAV_LOITER_TIME
  20:  'RTL',         // NAV_RETURN_TO_LAUNCH
  21:  'LAND',        // NAV_LAND
  22:  'TAKEOFF',     // NAV_TAKEOFF
  31:  'SPLINE',      // NAV_SPLINE_WAYPOINT
  82:  'PAYLOAD',     // NAV_PAYLOAD_PLACE
  189: 'DELAY',       // CONDITION_DELAY (no position)
}

export function extractMission(parsed) {
  if (!parsed?.data?.CMD) return { waypoints: [], home: null }
  const cmd = parsed.data.CMD
  if (!cmd.Lat || !cmd.Lng) return { waypoints: [], home: null }

  let home = null
  const waypoints = []

  const n = cmd.Lat.length
  for (let i = 0; i < n; i++) {
    let lat = Number(cmd.Lat[i])
    let lng = Number(cmd.Lng[i])
    const alt = Number(cmd.Alt?.[i] ?? 0)
    const cid = Number(cmd.CId?.[i] ?? 0)
    const cnum = Number(cmd.CNum?.[i] ?? i)

    // ArduPilot stores degrees ×1e7 in CMD just like in POS/GPS
    if (Math.abs(lat) > 200) { lat /= 1e7; lng /= 1e7 }

    // Skip zero / clearly-invalid coordinates EXCEPT the home (index 0)
    if (Math.abs(lat) < 1e-6 && Math.abs(lng) < 1e-6) continue

    // CNum == 0 is typically HOME
    if (cnum === 0 && !home) {
      home = { lat, lng, alt }
      continue
    }
    waypoints.push({
      idx: cnum,
      lat, lng, alt,
      cmd: cid,
      label: CMD_LABELS[cid] || `CMD ${cid}`,
    })
  }

  return { waypoints, home }
}
