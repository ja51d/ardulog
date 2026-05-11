

# About Me
Hey there, thank you for checking out my UAV Log Viewer!
My name is Javid I'm 21, I'm an astronautics engineer and I'm highly interested in UAV engineering, I built my first UAV a year ago and then I decided to create this program. 

# UAV Log Viewer

A native desktop log viewer and **automatic health analyzer** for ArduPilot DataFlash (`.bin`) flight logs. Inspired by [plot.ardupilot.org](https://plot.ardupilot.org/), but as a real desktop application with a built-in plain-language flight review.
<img width="1680" height="1050" alt="Screenshot 2026-05-11 at 1 28 53 PM" src="https://github.com/user-attachments/assets/85a24b4c-9a15-45f2-b5e5-5145b356e639" />


> **Created by Javid**

---

## Features

- **One-click `.bin` parsing** — drop in any ArduPilot DataFlash log, parsed in a background thread via [pymavlink](https://github.com/ArduPilot/pymavlink). Tested on logs with 100k+ messages.
- **Searchable message tree** — every message type and field exposed in a filterable sidebar. Click a checkbox to plot the field.
- **Interactive multi-series plots** — fast `pyqtgraph` charts with a vertical crosshair that reads out the time-of-day under the cursor.
- **2D satellite map** — flight track drawn on Esri World Imagery with a layer toggle for Dark / Satellite / Place labels. Zoom up to z22.
- **3D trajectory view** — Plotly-powered orbit-able 3D path with altitude colorscale, hover tooltips (x/y/altitude in meters), and a built-in toolbar for screenshot export.
- **Auto Flight Review** — analyzes the log and produces a plain-English health verdict across **14+ factors**:
  - Vibration & IMU clipping
  - GPS quality (HDop, satellite count, fix percentage)
  - Battery sag and per-cell voltage
  - Compass interference
  - EKF (state estimator) innovations
  - Error events
  - Altitude profile
  - Attitude (peak roll / pitch)
  - Motor output balance
  - Power consumption (mAh)
  - RC link stability
  - Autopilot CPU loop overruns
  - IMU temperature drift
  - Flight mode timeline
- **Modern dark UI** — built with PyQt6, polished QSS theming, gradient accent lines, hover states, and an at-a-glance overall health score with green/amber/red verdicts.

---

## Screenshots

<img width="1680" height="1050" alt="Screenshot 2026-05-11 at 12 56 42 PM" src="https://github.com/user-attachments/assets/052ea027-5656-42b6-a913-b79d3880b2a9" />
<img width="1680" height="1050" alt="Screenshot 2026-05-11 at 12 54 58 PM" src="https://github.com/user-attachments/assets/24ae1638-e31e-4714-b489-e3c1e648b451" />
<img width="1680" height="1050" alt="Screenshot 2026-05-11 at 1 29 10 PM" src="https://github.com/user-attachments/assets/8e0e1ae2-c1ed-4e32-8a22-d9d365c5cac8" />

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
|  **Plot** | Time-series plots of any tickbox-selected fields. Crosshair shows wall-clock time. Click ✕ Clear all to reset. |
|  **Map** | 2D satellite view of the GPS / EKF-smoothed flight path. Layer switcher in the top-right. |
| ◧ **3D** | Orbit-able 3D trajectory in local meters (East / North / Altitude). |
| ✓ **Auto Review** | Plain-language health summary with an overall verdict and per-factor cards. |
| ⓘ **Info** | Raw log metadata: duration, vehicle type, mode timeline, error events, message counts. |

---

## Why this exists

The web-based ArduPilot log viewer is great for quick checks, but:
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
