// Recent-logs cache backed by IndexedDB. We keep the raw ArrayBuffer for
// each log file so a re-parse is byte-identical to the original drop —
// nothing leaves the browser. Capped to the 5 most-recent (by mtime).

const DB_NAME = 'ardulog-cache'
const STORE = 'logs'
const VERSION = 1
const MAX = 5

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id' })
        store.createIndex('savedAt', 'savedAt', { unique: false })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function saveRecent(file, buffer) {
  try {
    const db = await open()
    const tx = db.transaction(STORE, 'readwrite')
    const store = tx.objectStore(STORE)
    const rec = {
      id: `${file.name}-${file.size}-${file.lastModified || 0}`,
      name: file.name,
      size: file.size,
      lastModified: file.lastModified || 0,
      savedAt: Date.now(),
      buffer,
    }
    store.put(rec)
    // Prune oldest if we exceed MAX
    const all = await listRecent(db)
    if (all.length > MAX) {
      const sorted = all.sort((a, b) => b.savedAt - a.savedAt)
      for (const r of sorted.slice(MAX)) store.delete(r.id)
    }
    await tx2Promise(tx)
    db.close()
  } catch (e) { /* swallow — caching is best-effort */ }
}

export async function listRecent(existing) {
  try {
    const db = existing || await open()
    const tx = db.transaction(STORE, 'readonly')
    const store = tx.objectStore(STORE)
    const req = store.getAll()
    const recs = await new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error) })
    if (!existing) db.close()
    return recs.sort((a, b) => b.savedAt - a.savedAt)
  } catch (e) {
    return []
  }
}

export async function loadRecent(id) {
  const db = await open()
  const tx = db.transaction(STORE, 'readonly')
  const req = tx.objectStore(STORE).get(id)
  const rec = await new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error) })
  db.close()
  return rec
}

export async function deleteRecent(id) {
  try {
    const db = await open()
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).delete(id)
    await tx2Promise(tx)
    db.close()
  } catch (e) {}
}

function tx2Promise(tx) {
  return new Promise((res, rej) => {
    tx.oncomplete = () => res()
    tx.onerror    = () => rej(tx.error)
    tx.onabort    = () => rej(tx.error)
  })
}

export function formatRelativeTime(ts) {
  const d = (Date.now() - ts) / 1000
  if (d < 60)        return 'just now'
  if (d < 3600)      return Math.floor(d / 60) + 'm ago'
  if (d < 86400)     return Math.floor(d / 3600) + 'h ago'
  if (d < 86400 * 7) return Math.floor(d / 86400) + 'd ago'
  return new Date(ts).toLocaleDateString()
}
