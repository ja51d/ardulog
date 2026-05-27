// Minimal OBJ loader — handles `v` (vertex) and `f` (face) lines only.
// Faces can be triangles or polygons; polygons are fan-triangulated.
// Ignores normals / UVs / materials. Returns flat arrays suitable for
// Plotly mesh3d (xs, ys, zs, i, j, k).

export async function loadObj(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`)
  const text = await res.text()
  return parseObj(text)
}

export function parseObj(text) {
  const xs = [], ys = [], zs = []
  const i = [], j = [], k = []
  const lines = text.split('\n')
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li]
    if (!line || line[0] === '#') continue
    if (line[0] === 'v' && line[1] === ' ') {
      const p = line.split(/\s+/)
      xs.push(parseFloat(p[1]))
      ys.push(parseFloat(p[2]))
      zs.push(parseFloat(p[3]))
    } else if (line[0] === 'f' && line[1] === ' ') {
      const p = line.split(/\s+/)
      // OBJ face indices are 1-based; "v/vt/vn" — we only want v
      const idx = []
      for (let n = 1; n < p.length; n++) {
        if (!p[n]) continue
        const v = parseInt(p[n].split('/')[0], 10)
        if (!isNaN(v)) idx.push(v - 1)
      }
      // Fan-triangulate any polygon
      for (let n = 1; n < idx.length - 1; n++) {
        i.push(idx[0]); j.push(idx[n]); k.push(idx[n + 1])
      }
    }
  }
  return { xs, ys, zs, i, j, k }
}

// Apply a one-shot rotation (yaw around Z, pitch around Y, roll around X)
// to a base mesh — used to re-orient an OBJ whose canonical axes don't
// match our convention (+X forward, +Y left, +Z up).
export function prerotate(base, { yaw = 0, pitch = 0, roll = 0 } = {}) {
  const cy = Math.cos(yaw),   sy = Math.sin(yaw)
  const cp = Math.cos(pitch), sp = Math.sin(pitch)
  const cr = Math.cos(roll),  sr = Math.sin(roll)
  const m00 = cy * cp,  m01 = cy * sp * sr - sy * cr,  m02 = cy * sp * cr + sy * sr
  const m10 = sy * cp,  m11 = sy * sp * sr + cy * cr,  m12 = sy * sp * cr - cy * sr
  const m20 = -sp,      m21 = cp * sr,                 m22 = cp * cr
  const n = base.xs.length
  const xs = new Array(n), ys = new Array(n), zs = new Array(n)
  for (let v = 0; v < n; v++) {
    const bx = base.xs[v], by = base.ys[v], bz = base.zs[v]
    xs[v] = m00 * bx + m01 * by + m02 * bz
    ys[v] = m10 * bx + m11 * by + m12 * bz
    zs[v] = m20 * bx + m21 * by + m22 * bz
  }
  // Carry through optional propeller spin metadata if the base has it
  // (and rotate the centers too, so they stay aligned with the spun verts).
  let propellers = null
  if (base.propellers) {
    propellers = base.propellers.map(p => {
      const [cx, cy, cz] = p.center
      return {
        start: p.start, count: p.count,
        center: [
          m00 * cx + m01 * cy + m02 * cz,
          m10 * cx + m11 * cy + m12 * cz,
          m20 * cx + m21 * cy + m22 * cz,
        ],
      }
    })
  }
  return { xs, ys, zs, i: base.i, j: base.j, k: base.k, propellers }
}

// Transform a base mesh (vertex arrays) by yaw / pitch / roll (radians)
// around its origin, then translate to (tx, ty, tz), and scale uniformly.
// Returns new flat arrays without mutating the input.
export function transformMesh(base, opts = {}) {
  const { yaw = 0, pitch = 0, roll = 0, scale = 1, tx = 0, ty = 0, tz = 0 } = opts
  const cy = Math.cos(yaw),   sy = Math.sin(yaw)
  const cp = Math.cos(pitch), sp = Math.sin(pitch)
  const cr = Math.cos(roll),  sr = Math.sin(roll)
  // Combined ZYX rotation matrix (yaw·pitch·roll, applied to body-frame +X forward)
  const m00 = cy * cp
  const m01 = cy * sp * sr - sy * cr
  const m02 = cy * sp * cr + sy * sr
  const m10 = sy * cp
  const m11 = sy * sp * sr + cy * cr
  const m12 = sy * sp * cr - cy * sr
  const m20 = -sp
  const m21 = cp * sr
  const m22 = cp * cr

  const n = base.xs.length
  const x = new Float32Array(n)
  const y = new Float32Array(n)
  const z = new Float32Array(n)

  // Optional spin: pre-rotate the propeller vertex ranges around their
  // motor centers (in body frame) before the global transform.
  // base.propellers = [{ start, count, center: [cx, cy, cz] }, ...]
  const spin = (typeof opts.propSpin === 'number') ? opts.propSpin : 0
  const propRanges = (spin && base.propellers) ? base.propellers : null
  const cs = Math.cos(spin), sn = Math.sin(spin)

  for (let v = 0; v < n; v++) {
    let bx = base.xs[v], by = base.ys[v], bz = base.zs[v]

    // Pre-spin if this vertex belongs to a propeller block
    if (propRanges) {
      for (const p of propRanges) {
        if (v >= p.start && v < p.start + p.count) {
          const dx = bx - p.center[0], dy = by - p.center[1]
          bx = p.center[0] + dx * cs - dy * sn
          by = p.center[1] + dx * sn + dy * cs
          break
        }
      }
    }

    bx *= scale; by *= scale; bz *= scale
    x[v] = m00 * bx + m01 * by + m02 * bz + tx
    y[v] = m10 * bx + m11 * by + m12 * bz + ty
    z[v] = m20 * bx + m21 * by + m22 * bz + tz
  }
  return { x, y, z }
}
