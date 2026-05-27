// Procedural low-poly meshes for the 3D playback view. Building these
// in code (instead of decimating a high-poly OBJ) gives a clean, crisp
// look at very low triangle counts — perfect for 60fps playback.
//
// Output format matches the OBJ loader: { xs, ys, zs, i, j, k }.
// Canonical orientation: +X forward (nose), +Z up.

// ---- low-level mesh builders ---------------------------------------

class MeshBuilder {
  constructor() {
    this.xs = []; this.ys = []; this.zs = []
    this.i = []; this.j = []; this.k = []
  }
  addVertex(x, y, z) {
    this.xs.push(x); this.ys.push(y); this.zs.push(z)
    return this.xs.length - 1
  }
  addTri(a, b, c) { this.i.push(a); this.j.push(b); this.k.push(c) }
  addQuad(a, b, c, d) { this.addTri(a, b, c); this.addTri(a, c, d) }
  build() {
    return { xs: this.xs, ys: this.ys, zs: this.zs, i: this.i, j: this.j, k: this.k }
  }
}

// Axis-aligned box, centered at (cx,cy,cz), with full sizes (sx,sy,sz).
function addBox(mb, cx, cy, cz, sx, sy, sz) {
  const x0 = cx - sx/2, x1 = cx + sx/2
  const y0 = cy - sy/2, y1 = cy + sy/2
  const z0 = cz - sz/2, z1 = cz + sz/2
  const v = [
    mb.addVertex(x0, y0, z0), mb.addVertex(x1, y0, z0),
    mb.addVertex(x1, y1, z0), mb.addVertex(x0, y1, z0),
    mb.addVertex(x0, y0, z1), mb.addVertex(x1, y0, z1),
    mb.addVertex(x1, y1, z1), mb.addVertex(x0, y1, z1),
  ]
  // -Z, +Z, -Y, +Y, -X, +X
  mb.addQuad(v[0], v[3], v[2], v[1])
  mb.addQuad(v[4], v[5], v[6], v[7])
  mb.addQuad(v[0], v[1], v[5], v[4])
  mb.addQuad(v[3], v[7], v[6], v[2])
  mb.addQuad(v[0], v[4], v[7], v[3])
  mb.addQuad(v[1], v[2], v[6], v[5])
}

// Capped cylinder along an arbitrary axis (start → end), radius r,
// segments s. Used for arms, motors, propeller blade booms.
function addCylinder(mb, start, end, r, s) {
  const [sx, sy, sz] = start
  const [ex, ey, ez] = end
  const ax = ex - sx, ay = ey - sy, az = ez - sz
  const len = Math.hypot(ax, ay, az) || 1
  const dx = ax / len, dy = ay / len, dz = az / len
  // Pick any perpendicular vector
  let upx = 0, upy = 0, upz = 1
  if (Math.abs(dz) > 0.95) { upx = 1; upy = 0; upz = 0 }
  // u = perpendicular to axis
  let ux = upy * dz - upz * dy
  let uy = upz * dx - upx * dz
  let uz = upx * dy - upy * dx
  const ul = Math.hypot(ux, uy, uz) || 1
  ux /= ul; uy /= ul; uz /= ul
  // v = axis × u
  const vx = dy * uz - dz * uy
  const vy = dz * ux - dx * uz
  const vz = dx * uy - dy * ux

  const ringStart = [], ringEnd = []
  for (let n = 0; n < s; n++) {
    const a = (n / s) * Math.PI * 2
    const cu = Math.cos(a) * r, cv = Math.sin(a) * r
    ringStart.push(mb.addVertex(sx + cu * ux + cv * vx, sy + cu * uy + cv * vy, sz + cu * uz + cv * vz))
    ringEnd.push(mb.addVertex(ex + cu * ux + cv * vx, ey + cu * uy + cv * vy, ez + cu * uz + cv * vz))
  }
  // Side walls
  for (let n = 0; n < s; n++) {
    const n2 = (n + 1) % s
    mb.addQuad(ringStart[n], ringEnd[n], ringEnd[n2], ringStart[n2])
  }
  // Caps (fan triangulation)
  const capStart = mb.addVertex(sx, sy, sz)
  const capEnd   = mb.addVertex(ex, ey, ez)
  for (let n = 0; n < s; n++) {
    const n2 = (n + 1) % s
    mb.addTri(capStart, ringStart[n2], ringStart[n])
    mb.addTri(capEnd,   ringEnd[n],    ringEnd[n2])
  }
}

// Flat disc (propeller). Two-sided so it's visible from above and below.
function addDisc(mb, cx, cy, cz, r, s) {
  const center = mb.addVertex(cx, cy, cz)
  const ring = []
  for (let n = 0; n < s; n++) {
    const a = (n / s) * Math.PI * 2
    ring.push(mb.addVertex(cx + Math.cos(a) * r, cy + Math.sin(a) * r, cz))
  }
  for (let n = 0; n < s; n++) {
    const n2 = (n + 1) % s
    mb.addTri(center, ring[n], ring[n2])
    mb.addTri(center, ring[n2], ring[n])  // back-face
  }
}

// Two-bladed propeller (skinny rectangle) on top of motor. Vertices are
// emitted in a contiguous block so the model layer can spin them in-place
// each frame by rotating just those verts.
function addPropeller(mb, cx, cy, cz, length, width) {
  const hl = length / 2, hw = width / 2
  const start = mb.xs.length
  const v0 = mb.addVertex(-hl + cx, -hw + cy, cz)
  const v1 = mb.addVertex( hl + cx, -hw + cy, cz)
  const v2 = mb.addVertex( hl + cx,  hw + cy, cz)
  const v3 = mb.addVertex(-hl + cx,  hw + cy, cz)
  mb.addQuad(v0, v1, v2, v3)
  mb.addQuad(v0, v3, v2, v1)  // back-face
  return { start, count: 4, center: [cx, cy, cz] }
}

// ---- quadcopter ----------------------------------------------------
// X-frame quadcopter. Arms run along ±X and ±Y diagonals (in body frame).
// Sized to fit roughly in a 2-unit cube. +X is the "front-right" arm by
// convention — we rotate the whole thing 45° so a clear arm points +X
// (forward, matching plane.obj convention).
//
// Returns the mesh plus `propellers` — a list of vertex slices the View3D
// layer can spin in-place each frame for a live "props spinning" effect.
export function buildQuadcopter() {
  const mb = new MeshBuilder()

  // Central body — slim hexagonal-ish box (use a stretched box)
  addBox(mb, 0, 0, 0, 0.55, 0.55, 0.18)

  // Top camera/sensor bump
  addBox(mb, 0.10, 0, 0.12, 0.20, 0.18, 0.10)

  // Four arms, rotated 45° so one points +X (forward)
  const armLen = 0.95
  const armR   = 0.05
  const arms = [
    [ Math.cos( Math.PI/4) * armLen,  Math.sin( Math.PI/4) * armLen],
    [ Math.cos(-Math.PI/4) * armLen,  Math.sin(-Math.PI/4) * armLen],
    [-Math.cos( Math.PI/4) * armLen, -Math.sin( Math.PI/4) * armLen],
    [-Math.cos(-Math.PI/4) * armLen, -Math.sin(-Math.PI/4) * armLen],
  ]
  for (const [ax, ay] of arms) {
    addCylinder(mb, [0, 0, 0], [ax, ay, 0], armR, 6)
    // Motor housing at the end
    addCylinder(mb, [ax, ay, -0.06], [ax, ay, 0.10], 0.08, 8)
  }

  // Landing legs — two small under-body cylinders
  addCylinder(mb, [-0.15, -0.20, -0.10], [-0.20, -0.30, -0.30], 0.025, 6)
  addCylinder(mb, [-0.15,  0.20, -0.10], [-0.20,  0.30, -0.30], 0.025, 6)
  addCylinder(mb, [ 0.15, -0.20, -0.10], [ 0.20, -0.30, -0.30], 0.025, 6)
  addCylinder(mb, [ 0.15,  0.20, -0.10], [ 0.20,  0.30, -0.30], 0.025, 6)

  // Propellers — added LAST so their vertex ranges are at the end of the
  // verts array. The view layer rotates just these verts around their
  // motor center each frame.
  const propellers = []
  for (let i = 0; i < arms.length; i++) {
    const [ax, ay] = arms[i]
    propellers.push(addPropeller(mb, ax, ay, 0.13, 0.55, 0.06))
  }

  const mesh = mb.build()
  mesh.propellers = propellers   // [{ start, count, center: [cx, cy, cz] }, ...]
  return mesh
}
