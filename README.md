

# About Me
Hey there, thank you for checking out my ArduPilot UAV Log Viewer!
My name is Javid I'm 21, I'm an astronautics engineer and I'm highly interested in UAV, I built my first UAV a year ago and then I decided to create this program. 

# ArduPilot UAV Log Viewer

Native desktop log viewer and **automatic health analyzer** for ArduPilot DataFlash (`.bin`) flight logs. Inspired by [plot.ardupilot.org](https://plot.ardupilot.org/), but offline and as a real desktop application with a built-in plain-language flight review.
<img width="1680" height="1050" alt="Screenshot 2026-05-25 at 9 11 16 PM" src="https://github.com/user-attachments/assets/e93a2085-13a9-4ee1-a44d-e23e5a0b9cd8" />



> **Created by Javid**

---

## Features

### Loading logs
- **One-click parsing** of any ArduPilot DataFlash `.bin`, MAVLink ground-station `.tlog`, or generic `.log` file. Parsed in a background thread via [pymavlink](https://github.com/ArduPilot/pymavlink). Tested on logs with 100k+ messages.
- **Drag-and-drop** a file from Finder/Explorer anywhere onto the window to open it.
- **Open Recent** submenu — keeps the last 10 logs you used; remembers the last folder you opened from.
- **Window state persistence** — geometry, splitter, last tab, and timezone are restored next launch.

### Analysis tabs
- **PLOT** — searchable message tree, click a field to add it as a curve. Wall-clock crosshair readout. **Right-click anywhere on the plot** to drop a labeled annotation (vertical dashed line + text); annotations persist per log automatically.
- **MAP** — 2D satellite view with the GPS / EKF-smoothed flight path **colored by altitude** (gradient cyan→violet→amber + legend). Now also overlays the **planned mission waypoints** (numbered violet markers + dashed mission line) and the **geofence polygon** if your log has them. Layer toggle for Satellite / Dark / Place labels. Zoom to z22.
- **3D** — orbit-able 3D trajectory with an animated airplane mesh that banks into turns. Distance markers along the route auto-adapt to the flight scale (`50 m`, `100 m`, `1 km`…). Play / pause / reset + 0.5×–8× speed buttons + scrubbable timeline. Real-time 1× playback by default.
- **COCKPIT** — flight instrument panel: artificial horizon (roll/pitch), heading indicator, altitude & airspeed tapes, plus radio-transmitter gimbals showing the live throttle/yaw/pitch/roll stick positions. Synced playback with speed controls.
- **FFT** — per-axis vibration spectrum (AccX/Y/Z) with the top-3 resonance peaks annotated. **Multi-IMU overlay**: IMU, IMU2 and IMU3 are drawn together (solid / dashed / dotted) so you can spot which sensor is failing. Below the spectra: a **spectrogram** (FFT-over-time heatmap) showing how vibration content evolves during the flight.
- **PID TUNING** — overlays the commanded vs actual roll / pitch / yaw so you can immediately see loose tuning (gap between desired and actual) or over-tuning (oscillation around the command).
- **AUTO REVIEW** — analyzes the log and produces a plain-English health verdict across **14+ factors**:
  - Vibration & IMU clipping · GPS quality · Battery sag · Compass interference
  - EKF state estimator · Error events · Altitude profile · Attitude peaks
  - Motor output balance · Power consumption · RC link · CPU loop overruns
  - IMU temperature drift · Flight mode timeline
  - **Incident detector** — flags extreme tilt (>60°), free-fall descent (>12 m/s), per-cell battery < 3.3 V, EKF stress, RC failsafe, and explicit ERR events. Each detected event is a **clickable row** — click jumps to the PLOT tab, zooms to a 20-second window around the moment, drops a red marker, and snaps the Map / 3D / Cockpit tabs to the same instant.
  - **Tooltips** on every category card explaining what the metric measures and what good / bad values mean.
- **INFO** — raw log metadata: duration, vehicle type, mode timeline, error events, message counts.

### Preferences (`View → Preferences…` or ⌘+,)
- **Timezone picker** — 17 IANA zones (with DST support). The plot axis, cockpit HUD, 3D HUD, status bar and Info tab all switch zones immediately.

### Reports & export
- **File → Export flight report (PDF)** — one-click branded PDF with the Auto Review, mode timeline, and incident list. Also available as a prominent **EXPORT PDF** button in the header.
- **File → Save plot as image (PNG)** — exports the current PLOT view at 1,800 px wide.
- **File → Export plotted series to CSV** — dumps the curves you've plotted with ISO timestamp, Unix timestamp, relative seconds, and value columns.

### Compare two flights
- **File → Load comparison log** — overlays a second flight on the plot as dashed, color-matched curves. Toggle any field on the tree and it mirrors automatically. Perfect for tuning before/after.

### Built for hobbyists
- **Modern dark UI** — built with PyQt6, Inter + JetBrains Mono typography, tactical accent line, hover states, and an at-a-glance overall health score with green/amber/red verdicts.

---

## Screenshots
<img width="1680" height="1050" alt="Screenshot 2026-05-25 at 9 12 51 PM" src="https://github.com/user-attachments/assets/79794d70-86f9-4e99-99b5-8f58b919797d" />


<img width="1680" height="1050" alt="Screenshot 2026-05-25 at 9 13 24 PM" src="https://github.com/user-attachments/assets/2b6e34ea-1c80-4df8-b797-7a9f02db189c" />
![Screenshot 2026-05-25 at 9 13 06 PM](https://github.com/user-attachments/assets/3b6d0e02-a5e1-4052-bfea-001c0f4ceba6)



---

## Installation

Requires **Python 3.10+** and a working pip toolchain.

```bash
pip install -r requirements.txt
```

Dependencies:
- `PyQt6` and `PyQt6-WebEngine` — UI + embedded browser for map/3D
- `pyqtgraph` — fast plotting
- `pymavlink` — ArduPilot log parser
- `numpy`, `bottleneck`

The map and 3D views need an internet connection (they pull tile imagery from OpenStreetMap/Esri and the Plotly/Leaflet libraries from CDN).

---


### Tabs

| Tab | What it shows |
| --- | --- |
| **PLOT** | Time-series plots of any tick-box-selected fields. Crosshair shows wall-clock time. Right-click to drop labeled annotations (persisted per log). ✕ Clear all to reset. |
| **MAP** | 2D satellite view of the EKF-smoothed flight path, segments colored by altitude. Mission waypoints and geofence overlaid if present. |
| **3D** | Orbit-able 3D trajectory with an animated airplane that banks into turns, plus auto-spaced distance markers. Play / pause / reset + speed controls + scrubbable timeline. |
| **COCKPIT** | Artificial horizon, heading indicator, altitude / airspeed tapes, and live radio-transmitter gimbals. Real-time playback with speed controls. |
| **FFT** | Multi-IMU vibration frequency spectrum per accel axis + a spectrogram (FFT-over-time heatmap) below. |
| **PID TUNING** | Commanded vs actual roll / pitch / yaw. Diagnose loose or over-tuned gains visually. |
| **AUTO REVIEW** | Plain-language health summary with an overall verdict, hover tooltips per metric, and a clickable incident list that jumps the whole app to the moment of interest. |
| **INFO** | Raw log metadata: duration, vehicle type, mode timeline, error events, message counts. |

---


## Tech stack

- **PyQt6** for the desktop shell
- **pyqtgraph** for time-series plots (Qt-native, GPU-accelerated)
- **QtWebEngineView** + **Leaflet** for the 2D map (Esri World Imagery tiles)
- **QtWebEngineView** + **Plotly** for the 3D trajectory
- **pymavlink** (`DFReader_binary`) for parsing ArduPilot DataFlash logs

---

## License

MIT — see [LICENSE](LICENSE).

ArduPilot logs and pymavlink are copyright their respective owners. Map tiles © OpenStreetMap, © CARTO, and Esri / Maxar / Earthstar Geographics for satellite imagery.
