// Port of detect_frame_kind() from app.py. Returns one of:
//   'copter' | 'plane' | 'heli' | 'rover' | 'sub' | 'other'
export function detectFrameKind(parsed) {
  const mt = parsed.vehicle_type
  const copter = new Set([2, 3, 13, 14, 15, 19, 20, 21, 22, 23])
  if (copter.has(mt)) return 'copter'
  if (mt === 1) return 'plane'
  if (mt === 4) return 'heli'
  if (mt === 10 || mt === 11) return 'rover'
  if (mt === 12) return 'sub'
  const params = parsed.params || {}
  if (params.Q_ENABLE) return 'copter'
  if (params.FRAME_CLASS) return 'copter'
  return 'other'
}
