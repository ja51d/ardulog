# 🛩️ Ardulog

**Browser-based ArduPilot flight log analyzer.** Drop a `.bin` / `.tlog` / `.log`,
get a full diagnostic suite — 3D playback on real satellite terrain, AI-powered
insights, FFT, PID tuning, battery analysis, PDF reports. 100% local — your log
never leaves your browser.

🌐 **Live at [ardulog.app](https://ardulog.app)**

---

## Features

### 🗺️ Visualize
- **SUMMARY** — log overview with frame type, duration, message counts
- **PLOT** — searchable message tree, multi-series overlay, CSV export
- **MAP** — 2D satellite view with altitude-colored track, mission waypoints, and geofence overlay
- **TERRAIN** — 3D satellite map with real elevation, vehicle icon flying along the trajectory
- **3D** — orbit-able trajectory with airplane / quadcopter models, spinning propellers, vibration-heatmap toggle
- **COCKPIT** — attitude indicator, HSI, altitude / airspeed tapes, RC sticks, wind compass

### 🔬 Analyze
- **COPILOT** — AI flight Q&A (Google Gemini 2.5 Flash). Ask "Why was my battery sagging?" and get pilot-grade answers grounded in your log
- **FFT** — vibration spectrum per IMU axis with peak frequency detection
- **PID TUNING** — commanded vs actual roll / pitch / yaw overlay
- **MOTORS** — per-motor output balance and saturation analysis
- **BATTERY** — voltage / current / mAh consumption with sag detection
- **REVIEW** — automated 14+ factor health assessment (incidents, EKF, GPS, vibration, etc.)

### 💾 Data
- **REPORT** — comprehensive multi-section flight report with PNG / PDF export
- **PARAMS** — searchable parameter dump
- **INFO** — raw log metadata

### 🎮 Playback
- Synced play/pause/scrub across 3D, Terrain, Cockpit
- Speed control 0.5× → 8×
- Color-banded **flight timeline** showing mode segments + events (failsafes, arms, landings)
- Click any event to jump to that timestamp

---

## Privacy

Every byte of your log is parsed **in your browser via WebAssembly**. No upload, no server-side storage.
- Logs you've opened can be cached locally in IndexedDB (so they reappear on the home screen next visit) — purely local, never transmitted.
- The AI Copilot sends a *condensed text summary* (key metrics, events, review findings) to Google's Gemini API — not the raw log bytes.

---

## Tech stack

- **Vue 3** + **Vite** (Rolldown)
- **uPlot** — fast 2D charts
- **Plotly** — 3D scatter rendering
- **MapLibre GL** — vector + raster maps with 3D terrain
- **Leaflet** — 2D map view
- **fft.js** — vibration spectrum analysis
- **html-to-image** + **jsPDF** — report exports
- **Vercel** serverless function → **Google Gemini 2.5 Flash** for AI Copilot

---

## Local development

```bash
git clone https://github.com/ja51d/ardulog.git
cd ardulog/web
npm install
npm run dev
```

To enable the AI Copilot locally, set a `GEMINI_API_KEY` environment variable
(free key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)).

Built and deployed with [Vercel](https://vercel.com) → `vercel --prod`.

---

## Credits

Built by **Javid** ([@ja51d](https://github.com/ja51d)) — astronautics engineer and UAV builder.
Inspired by [plot.ardupilot.org](https://plot.ardupilot.org/) and the brilliant ArduPilot community.

## License

See [LICENSE](LICENSE).
