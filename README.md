

# About Me
Hey there, thank you for checking out my UAV Log Viewer!
My name is Javid I'm 21, I'm an astronautics engineer and I'm highly interested in UAV engineering, I built my first UAV a year ago and then I decided to create this program. 

# UAV Log Viewer

A native desktop log viewer and **automatic health analyzer** for ArduPilot DataFlash (`.bin`) flight logs. Inspired by [plot.ardupilot.org](https://plot.ardupilot.org/), but offline and as a real desktop application with a built-in plain-language flight review.
<img width="1680" height="1050" alt="Screenshot 2026-05-11 at 7 51 35 PM" src="https://github.com/user-attachments/assets/22410de2-367c-409d-ac32-daa3e1cc11ea" />



> **Created by Javid**

---

## Features

### Loading logs
- **One-click parsing** of any ArduPilot DataFlash `.bin`, MAVLink ground-station `.tlog`, or generic `.log` file. Parsed in a background thread via [pymavlink](https://github.com/ArduPilot/pymavlink). Tested on logs with 100k+ messages.
- **Drag-and-drop** a file from Finder/Explorer anywhere onto the window to open it.
- **Open Recent** submenu — keeps the last 10 logs you used.

### Analysis tabs
- **PLOT** — searchable message tree, click a field to add it as a curve. Wall-clock crosshair readout, ✕ Clear all toolbar.
- **MAP** — 2D satellite view with the GPS / EKF-smoothed flight path **colored by altitude** (gradient cyan→violet→amber + legend). Layer toggle for Satellite / Dark / Place labels. Zoom to z22.
- **3D** — orbit-able 3D trajectory with an animated airplane mesh that banks into turns. Play/pause/reset + 0.5×–8× speed buttons + scrubbable timeline. Real-time 1× playback by default.
- **COCKPIT** — flight instrument panel: artificial horizon (roll/pitch), heading indicator, altitude & airspeed tapes, plus radio transmitter gimbals showing the live throttle/yaw/pitch/roll stick positions. Synced playback with speed controls.
- **FFT** — per-axis vibration spectrum (AccX/Y/Z) with the top-3 resonance peaks annotated. Spot motor / airframe resonances at a glance.
- **PID TUNING** — overlays the commanded vs actual roll / pitch / yaw so you can immediately see loose tuning (gap between desired and actual) or over-tuning (oscillation around the command).
- **AUTO REVIEW** — analyzes the log and produces a plain-English health verdict across **14+ factors**:
  - Vibration & IMU clipping · GPS quality · Battery sag · Compass interference
  - EKF state estimator · Error events · Altitude profile · Attitude peaks
  - Motor output balance · Power consumption · RC link · CPU loop overruns
  - IMU temperature drift · Flight mode timeline
  - **Incident detector** — flags extreme tilt (>60°), free-fall descent (>12 m/s), per-cell battery < 3.3 V, EKF stress, RC failsafe, and explicit ERR events with timestamps.
- **INFO** — raw log metadata: duration, vehicle type, mode timeline, error events, message counts.

### Master timeline
- **PLAY ALL bar** at the top of the window drives the Map, 3D, and Cockpit tabs in **synchronized real-time playback** with a single timeline. A moving cyan marker on the map shows the aircraft's live position.

### Reports & export
- **File → Export flight report (PDF)** — one-click branded PDF with the Auto Review, mode timeline, and incident list.
- **File → Export plotted series to CSV** — dumps the curves you've plotted with ISO timestamp, Unix timestamp, relative seconds, and value columns.

### Compare two flights
- **File → Load comparison log** — overlays a second flight on the plot as dashed, color-matched curves. Toggle any field on the tree and it mirrors automatically. Perfect for tuning before/after.

### Built for hobbyists
- **Modern dark UI** — built with PyQt6, Inter + JetBrains Mono typography, tactical accent line, hover states, and an at-a-glance overall health score with green/amber/red verdicts.

---

## Screenshots

<img width="1680" height="1050" alt="Screenshot 2026-05-11 at 7 48 55 PM" src="https://github.com/user-attachments/assets/141f71e9-37e3-4bc2-b881-35f4f0695e3c" />

<img width="1680" height="1050" alt="Screenshot 2026-05-11 at 7 49 15 PM" src="https://github.com/user-attachments/assets/cb66780c-4381-450d-9019-85733814b05b" />
<img width="1680" height="1050" alt="Screenshot 2026-05-11 at 7 49 07 PM" src="https://github.com/user-attachments/assets/fc81a5f9-a3b4-4bd0-b38f-f28e2e240e76" />


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
| **PLOT** | Time-series plots of any tick-box-selected fields. Crosshair shows wall-clock time. ✕ Clear all to reset. |
| **MAP** | 2D satellite view of the EKF-smoothed flight path, segments colored by altitude. Moving cyan marker tracks the master timeline. |
| **3D** | Orbit-able 3D trajectory with an animated airplane that banks into turns. Play / pause / reset + speed controls + scrubbable timeline. |
| **COCKPIT** | Artificial horizon, heading indicator, altitude / airspeed tapes, and live radio transmitter gimbals. Real-time synced playback. |
| **FFT** | Vibration frequency spectrum per accel axis with annotated resonance peaks. |
| **PID TUNING** | Commanded vs actual roll / pitch / yaw. Diagnose loose or over-tuned gains visually. |
| **AUTO REVIEW** | Plain-language health summary with an overall verdict, per-factor cards, and an incident detector. |
| **INFO** | Raw log metadata: duration, vehicle type, mode timeline, error events, message counts. |

---

## Why this exists

Most web-based ArduPilot log viewers are great for quick checks, but:
- It runs in the browser — no native window, no offline use.
- It shows you *the data*, not *what the data means*.
- New pilots staring at vibration plots don't know if `25 m/s²` is good or bad.

This tool fixes both: it's a real desktop app, and the **Auto Review** tab translates raw telemetry into sentences any pilot can act on


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
