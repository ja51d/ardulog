"""UAV Log Viewer — desktop app for ArduPilot DataFlash (.bin) logs."""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuration — edit these to adapt the app to your locale.
# ----------------------------------------------------------------------------
# Default display timezone for log timestamps. Turkey/Istanbul is UTC+3.
# To use a different timezone, change the offset:
#   timezone(timedelta(hours=0))   # UTC
#   timezone(timedelta(hours=-5))  # New York (EST, no DST handling)
#   timezone(timedelta(hours=2))   # Berlin (CET, no DST handling)
# For DST-aware zones, use ZoneInfo:
#   from zoneinfo import ZoneInfo
#   ISTANBUL_TZ = ZoneInfo("America/New_York")
ISTANBUL_TZ = timezone(timedelta(hours=3), name="Istanbul")
# ----------------------------------------------------------------------------

def fmt_istanbul(unix_ts: float, with_date: bool = False) -> str:
    if unix_ts is None or unix_ts != unix_ts:  # None or NaN
        return "—"
    dt = datetime.fromtimestamp(float(unix_ts), tz=ISTANBUL_TZ)
    if with_date:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"

# Force PyQt6 to use its bundled Qt plugins (Anaconda's own Qt can hijack the
# QT_QPA_PLATFORM_PLUGIN_PATH and break the cocoa platform plugin on macOS).
def _fix_qt_plugin_path() -> None:
    try:
        import PyQt6  # noqa: F401
    except ImportError:
        return
    plugins = Path(PyQt6.__file__).parent / "Qt6" / "plugins"
    if plugins.is_dir():
        os.environ["QT_PLUGIN_PATH"] = str(plugins)
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins / "platforms")
_fix_qt_plugin_path()

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView
from pymavlink import DFReader

# ---------- Theme ----------
BG_0 = "#0b1220"   # window background
BG_1 = "#111a2e"   # panels
BG_2 = "#16223c"   # raised
BG_3 = "#1d2c4d"   # hover
BORDER = "#243154"
TEXT = "#e6edf7"
TEXT_DIM = "#8b97b3"
ACCENT = "#22d3ee"   # cyan
ACCENT_2 = "#a78bfa" # violet
DANGER = "#f87171"
SUCCESS = "#34d399"

pg.setConfigOption("background", BG_1)
pg.setConfigOption("foreground", TEXT)
pg.setConfigOptions(antialias=True)

PLOT_COLORS = [
    "#22d3ee",  # cyan
    "#a78bfa",  # violet
    "#34d399",  # green
    "#fbbf24",  # amber
    "#f87171",  # red
    "#60a5fa",  # blue
    "#f472b6",  # pink
    "#facc15",  # yellow
    "#4ade80",  # lime
    "#fb923c",  # orange
]

APP_QSS = f"""
* {{
    color: {TEXT};
    font-family: "Segoe UI", "Helvetica Neue", "Inter", Arial, sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget {{
    background-color: {BG_0};
}}
QMenuBar {{
    background: {BG_0};
    border-bottom: 1px solid {BORDER};
    padding: 3px 8px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 12px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{ background: {BG_2}; color: {ACCENT}; }}
QMenu {{
    background: {BG_1};
    border: 1px solid {BORDER};
    padding: 6px;
    border-radius: 8px;
}}
QMenu::item {{ padding: 7px 22px; border-radius: 5px; }}
QMenu::item:selected {{ background: {BG_3}; color: {ACCENT}; }}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 6px;
}}

QStatusBar {{
    background: {BG_0};
    border-top: 1px solid {BORDER};
    color: {TEXT_DIM};
    font-family: "SF Mono", Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
    letter-spacing: 0.5px;
    min-height: 26px;
}}
QStatusBar::item {{ border: none; }}

QSplitter::handle {{
    background: {BORDER};
    width: 1px;
}}
QSplitter::handle:hover {{ background: {ACCENT}; }}

QLineEdit {{
    background: {BG_2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 12px;
    selection-background-color: {ACCENT};
    selection-color: {BG_0};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
    background: {BG_3};
}}

QTreeWidget {{
    background: {BG_1};
    border: 1px solid {BORDER};
    border-radius: 8px;
    outline: 0;
    padding: 6px;
}}
QTreeWidget::item {{
    padding: 5px 6px;
    border-radius: 4px;
    border: 1px solid transparent;
}}
QTreeWidget::item:hover {{ background: {BG_2}; }}
QTreeWidget::item:selected {{
    background: {BG_3};
    color: {ACCENT};
    border: 1px solid {ACCENT};
}}
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {{
    image: none;
    border-image: none;
}}
QHeaderView::section {{
    background: {BG_1};
    color: {TEXT_DIM};
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 700;
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 1.5px;
}}
QTreeView::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {BG_2};
}}
QTreeView::indicator:hover {{ border: 1px solid {ACCENT}; }}
QTreeView::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    image: none;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    top: -1px;
    background: {BG_1};
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 10px 22px;
    margin-right: 3px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 500;
    font-size: 12px;
    letter-spacing: 0.5px;
}}
QTabBar::tab:hover {{
    color: {TEXT};
    background: {BG_2};
}}
QTabBar::tab:selected {{
    background: {BG_1};
    color: {ACCENT};
    border: 1px solid {BORDER};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}

QPlainTextEdit, QTextEdit {{
    background: {BG_1};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 12px;
    font-family: "SF Mono", Menlo, Monaco, Consolas, monospace;
    font-size: 12px;
    selection-background-color: {ACCENT};
    selection-color: {BG_0};
}}

QScrollArea {{ border: none; }}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BG_3}; min-height: 40px; border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BG_3}; min-width: 40px; border-radius: 5px; }}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

QToolTip {{
    background: {BG_2};
    color: {TEXT};
    border: 1px solid {ACCENT};
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 11px;
}}

QPushButton {{
    background: {BG_2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 16px;
    color: {TEXT};
    font-weight: 500;
}}
QPushButton:hover {{
    background: {BG_3};
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton:pressed {{ background: {BG_1}; }}
QPushButton#primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {ACCENT}, stop:1 #0ea5b8);
    color: {BG_0};
    border: 1px solid {ACCENT};
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #67e8f9, stop:1 {ACCENT});
    border-color: #67e8f9;
    color: {BG_0};
}}

QFrame#statTile {{
    background: {BG_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
"""

PLOT3D_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8" />
<title>3D Track</title>
<style>
  html,body{height:100%;margin:0;padding:0;background:#0b1220;
            font-family:"Segoe UI","Helvetica Neue",sans-serif;color:#e6edf7;overflow:hidden}
  #plot{width:100%;height:100vh}
  .empty{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
         padding:18px 24px;background:#111a2e;border:1px solid #243154;
         color:#8b97b3;border-radius:8px;text-align:center}
  .hud{position:absolute;top:14px;left:14px;z-index:10;
       padding:8px 14px;background:rgba(17,26,46,0.85);
       border:1px solid #22d3ee;border-radius:8px;
       backdrop-filter:blur(6px);font-size:11px;letter-spacing:1px;
       color:#22d3ee;font-weight:600}
  .hud .v{color:#e6edf7;font-weight:400;letter-spacing:0;margin-left:8px}
</style>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head><body>
<div id="hud" class="hud" style="display:none">
  <span>◈ TELEMETRY</span>
  <span class="v" id="hud-alt">alt — m</span>
  <span class="v" id="hud-d">dist — m</span>
  <span class="v" id="hud-i">frame —/—</span>
</div>
<div id="plot"></div>
<script>
const PTS = __PTS__;
if (!PTS || PTS.x.length < 2) {
  document.body.innerHTML = '<div class="empty">'
    + '<div style="font-size:14px;color:#e6edf7;margin-bottom:4px">No 3D track</div>'
    + '<div style="font-size:12px">Need at least 2 GPS/POS points with a 3D fix.</div></div>';
} else {
  const X = PTS.x, Y = PTS.y, Z = PTS.z;
  const N = X.length;
  // Subsample for animation frames (cap ~150 to stay smooth)
  const FRAMES = Math.min(150, N);
  const STEP = Math.max(1, Math.floor(N / FRAMES));
  const idxs = [];
  for (let i = 0; i < N; i += STEP) idxs.push(i);
  if (idxs[idxs.length-1] !== N - 1) idxs.push(N - 1);

  // Cumulative distance for HUD
  const cumD = new Array(N).fill(0);
  for (let i = 1; i < N; i++) {
    const dx=X[i]-X[i-1], dy=Y[i]-Y[i-1], dz=Z[i]-Z[i-1];
    cumD[i] = cumD[i-1] + Math.sqrt(dx*dx+dy*dy+dz*dz);
  }

  // Direction vector at index i (forward difference, normalized)
  function dir(i) {
    const j = Math.min(i + 1, N - 1);
    const k = Math.max(i - 1, 0);
    let u = X[j]-X[k], v = Y[j]-Y[k], w = Z[j]-Z[k];
    const m = Math.sqrt(u*u+v*v+w*w) || 1;
    return [u/m, v/m, w/m];
  }

  const xExtent = Math.max(...X) - Math.min(...X);
  const yExtent = Math.max(...Y) - Math.min(...Y);
  const zExtent = Math.max(...Z) - Math.min(...Z);
  const sizeRef = Math.max(0.6, Math.max(xExtent, yExtent, zExtent) * 0.06);

  // ---- Initial traces ----
  // 0: full route (dimmed)
  const fullRoute = {
    type:'scatter3d', mode:'lines',
    x:X, y:Y, z:Z,
    line:{ width:2, color:'rgba(167,139,250,0.30)' },
    name:'route',
    hoverinfo:'skip',
    showlegend:true
  };
  // 1: flown trail (bright cyan, grows during animation)
  const flownTrail = {
    type:'scatter3d', mode:'lines',
    x:[X[0]], y:[Y[0]], z:[Z[0]],
    line:{ width:6, color:'#22d3ee' },
    name:'flown',
    hoverinfo:'skip'
  };
  // 2: aircraft (cone, points along velocity)
  const [u0,v0,w0] = dir(0);
  const aircraft = {
    type:'cone',
    x:[X[0]], y:[Y[0]], z:[Z[0]],
    u:[u0], v:[v0], w:[w0],
    sizemode:'absolute', sizeref:sizeRef,
    showscale:false,
    colorscale:[[0,'#fbbf24'],[1,'#f87171']],
    anchor:'tail',
    name:'aircraft',
    hovertemplate:'AIRCRAFT<br>x: %{x:.1f} m<br>y: %{y:.1f} m<br>alt: %{z:.1f} m<extra></extra>'
  };
  // 3: start marker
  const startMarker = {
    type:'scatter3d', mode:'markers',
    x:[X[0]], y:[Y[0]], z:[Z[0]],
    marker:{ size:7, color:'#34d399', line:{color:'#0b1220',width:2} },
    name:'start',
    hovertemplate:'START<extra></extra>'
  };
  // 4: end marker
  const endMarker = {
    type:'scatter3d', mode:'markers',
    x:[X[N-1]], y:[Y[N-1]], z:[Z[N-1]],
    marker:{ size:7, color:'#f87171', line:{color:'#0b1220',width:2} },
    name:'end',
    hovertemplate:'END<extra></extra>'
  };

  // ---- Animation frames ----
  const frames = idxs.map(i => {
    const [u,v,w] = dir(i);
    return {
      name: String(i),
      data: [
        {},  // route unchanged
        { x:X.slice(0,i+1), y:Y.slice(0,i+1), z:Z.slice(0,i+1) },  // flown
        { x:[X[i]], y:[Y[i]], z:[Z[i]], u:[u], v:[v], w:[w] }       // aircraft
      ],
      traces:[0,1,2]
    };
  });

  const sliderSteps = idxs.map(i => ({
    label:'',
    method:'animate',
    args:[[String(i)], { mode:'immediate',
                         frame:{duration:0,redraw:true},
                         transition:{duration:0} }]
  }));

  const layout = {
    paper_bgcolor:'#0b1220',
    plot_bgcolor:'#0b1220',
    font:{ color:'#e6edf7', family:'"Segoe UI","Helvetica Neue",sans-serif' },
    margin:{ l:0, r:0, t:0, b:90 },
    showlegend:true,
    scene:{
      bgcolor:'#0b1220',
      xaxis:{ title:{text:'EAST (m)',font:{size:10,color:'#8b97b3'}},
              gridcolor:'#243154', zerolinecolor:'#22d3ee', color:'#8b97b3',
              showbackground:true, backgroundcolor:'rgba(17,26,46,0.4)' },
      yaxis:{ title:{text:'NORTH (m)',font:{size:10,color:'#8b97b3'}},
              gridcolor:'#243154', zerolinecolor:'#22d3ee', color:'#8b97b3',
              showbackground:true, backgroundcolor:'rgba(17,26,46,0.4)' },
      zaxis:{ title:{text:'ALTITUDE (m)',font:{size:10,color:'#8b97b3'}},
              gridcolor:'#243154', zerolinecolor:'#a78bfa', color:'#8b97b3',
              showbackground:true, backgroundcolor:'rgba(17,26,46,0.6)' },
      aspectmode:'data',
      camera:{ eye:{x:1.5, y:1.5, z:0.95} }
    },
    legend:{ font:{color:'#e6edf7',size:10},
             bgcolor:'rgba(17,26,46,0.85)',
             bordercolor:'#22d3ee', borderwidth:1,
             x:0.85, y:0.97 },
    updatemenus:[{
      type:'buttons',
      direction:'left',
      x:0.02, y:0, xanchor:'left', yanchor:'bottom',
      pad:{t:10, b:20, l:0, r:0},
      bgcolor:'rgba(17,26,46,0.0)', bordercolor:'rgba(0,0,0,0)',
      font:{color:'#e6edf7', family:'"Segoe UI",sans-serif', size:11},
      buttons:[
        { label:'▶  PLAY', method:'animate',
          args:[null, { mode:'immediate', fromcurrent:true,
                        frame:{duration:60, redraw:true},
                        transition:{duration:0} }] },
        { label:'❚❚  PAUSE', method:'animate',
          args:[[null], { mode:'immediate',
                          frame:{duration:0, redraw:false},
                          transition:{duration:0} }] },
        { label:'⏮  RESET', method:'animate',
          args:[[String(idxs[0])], { mode:'immediate',
                                      frame:{duration:0, redraw:true},
                                      transition:{duration:0} }] }
      ]
    }],
    sliders:[{
      pad:{t:10, b:0, l:280, r:30},
      x:0, y:0,
      len:1,
      bgcolor:'#243154',
      bordercolor:'rgba(0,0,0,0)',
      activebgcolor:'#22d3ee',
      tickcolor:'#8b97b3',
      font:{color:'#8b97b3', size:10},
      currentvalue:{ visible:false },
      steps:sliderSteps
    }]
  };
  const config = { displayModeBar:true, displaylogo:false, responsive:true,
                   modeBarButtonsToRemove:['toImage'] };

  document.getElementById('hud').style.display = 'block';
  function updateHud(i) {
    document.getElementById('hud-alt').textContent = 'ALT ' + Z[i].toFixed(1) + ' m';
    document.getElementById('hud-d').textContent   = 'DIST ' + cumD[i].toFixed(1) + ' m';
    document.getElementById('hud-i').textContent   = 'FRAME ' + (idxs.indexOf(i)+1) + '/' + idxs.length;
  }
  updateHud(0);

  Plotly.newPlot('plot', [fullRoute, flownTrail, aircraft, startMarker, endMarker], layout, config)
    .then(gd => {
      Plotly.addFrames('plot', frames);
      gd.on('plotly_animatingframe', e => {
        const i = parseInt(e.frame.name, 10);
        if (!isNaN(i)) updateHud(i);
      });
    });
}
</script>
</body></html>
"""

MAP_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8" />
<title>Track</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  html,body,#map{height:100%;margin:0;padding:0;background:#0b1220}
  .leaflet-container{background:#0b1220 !important;font-family:-apple-system,sans-serif}
  .leaflet-control-attribution{background:rgba(17,26,46,.85) !important;color:#8b97b3 !important;border:none !important}
  .leaflet-control-attribution a{color:#22d3ee !important}
  .leaflet-bar{border:1px solid #243154 !important;background:#16223c !important}
  .leaflet-bar a{background:#16223c !important;color:#e6edf7 !important;border-bottom:1px solid #243154 !important}
  .leaflet-bar a:hover{background:#1d2c4d !important;color:#22d3ee !important}
  .leaflet-tooltip{background:#16223c;border:1px solid #22d3ee;color:#e6edf7;box-shadow:0 2px 8px rgba(0,0,0,.4)}
  .leaflet-tooltip-top:before{border-top-color:#22d3ee}
  .leaflet-control-layers{background:#111a2e !important;border:1px solid #243154 !important;color:#e6edf7 !important;border-radius:6px !important;padding:4px 6px !important}
  .leaflet-control-layers-expanded{padding:8px 12px !important;min-width:140px}
  .leaflet-control-layers label{color:#e6edf7;font-size:12px;padding:2px 0;cursor:pointer}
  .leaflet-control-layers-separator{border-top:1px solid #243154 !important;margin:6px 0 !important}
  .leaflet-control-layers-toggle{background-color:#16223c !important}
  .empty-banner{
    position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
    padding:18px 24px;background:#111a2e;border:1px solid #243154;
    color:#8b97b3;border-radius:8px;font-family:-apple-system,sans-serif;
    z-index:1000;text-align:center
  }
</style>
</head><body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const COORDS = __COORDS__;
const map = L.map('map', {
  zoomControl: true,
  attributionControl: true,
  maxZoom: 22,
});

// --- Layers ---
const satellite = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {
    maxZoom: 22,
    maxNativeZoom: 19,
    attribution: 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, GIS User Community'
  }
);
// Reference overlay (place labels) for the Hybrid view
const refLabels = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
  { maxZoom: 22, maxNativeZoom: 19, attribution: '' }
);
const dark = L.tileLayer(
  'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
  { maxZoom: 20, attribution: '© OpenStreetMap · © CARTO' }
);

// Default: satellite + labels (hybrid feel)
satellite.addTo(map);
refLabels.addTo(map);

const baseLayers = {
  'Satellite': satellite,
  'Dark': dark,
};
const overlays = {
  'Place labels': refLabels,
};
L.control.layers(baseLayers, overlays, {position:'topright', collapsed:false}).addTo(map);

// --- Track ---
if (COORDS.length > 1) {
  const glow = L.polyline(COORDS, {color:'#22d3ee', weight:9, opacity:0.25}).addTo(map);
  const line = L.polyline(COORDS, {color:'#22d3ee', weight:3, opacity:1.0}).addTo(map);
  L.circleMarker(COORDS[0], {
    radius:8, color:'#0b1220', fillColor:'#34d399', fillOpacity:1, weight:2
  }).addTo(map).bindTooltip('start', {direction:'top', permanent:false});
  L.circleMarker(COORDS[COORDS.length-1], {
    radius:8, color:'#0b1220', fillColor:'#f87171', fillOpacity:1, weight:2
  }).addTo(map).bindTooltip('end', {direction:'top', permanent:false});

  // Pad the bounds slightly and pick a tighter starting zoom so the user
  // sees the location, then they can zoom further in (max 22).
  const bounds = line.getBounds().pad(0.3);
  map.fitBounds(bounds, {padding:[30,30], maxZoom: 19});
} else {
  map.setView([20,0], 2);
  const div = L.DomUtil.create('div', 'empty-banner');
  div.innerHTML = '<div style="font-size:14px;color:#e6edf7;margin-bottom:4px">No GPS data</div>'
                + '<div style="font-size:12px">Load a log with GPS messages to see the flight track.</div>';
  document.body.appendChild(div);
}
</script>
</body></html>
"""


def auto_review(parsed: dict) -> list[dict]:
    """Run a plain-English health check across the parsed log.
    Returns a list of {category, verdict, color, headline, detail} dicts."""
    data = parsed["data"]
    items: list[dict] = []

    def add(category, verdict, color, headline, detail):
        items.append({
            "category": category, "verdict": verdict, "color": color,
            "headline": headline, "detail": detail,
        })

    # ---------- Vibration ----------
    vibe = data.get("VIBE")
    if vibe and "VibeX" in vibe and "VibeY" in vibe and "VibeZ" in vibe:
        vx = np.asarray(vibe["VibeX"], dtype=float)
        vy = np.asarray(vibe["VibeY"], dtype=float)
        vz = np.asarray(vibe["VibeZ"], dtype=float)
        peak = float(max(np.nanmax(vx), np.nanmax(vy), np.nanmax(vz)))
        mean = float(np.nanmean(np.sqrt(vx*vx + vy*vy + vz*vz)))
        if peak < 30 and mean < 15:
            add("Vibration", "Good", SUCCESS,
                f"Vibration levels are healthy.",
                f"Peak axis vibration was {peak:.1f} m/s²; average magnitude {mean:.1f} m/s². "
                f"ArduPilot considers <30 m/s² fine and >60 m/s² problematic.")
        elif peak < 60 and mean < 30:
            add("Vibration", "Marginal", "#fbbf24",
                f"Vibration is acceptable but on the higher side.",
                f"Peak {peak:.1f} m/s² (advisory: <30). Consider tightening props, balancing motors, "
                f"or improving flight-controller foam/dampening.")
        else:
            add("Vibration", "Bad", DANGER,
                f"Vibration is high and may degrade EKF / position hold.",
                f"Peak {peak:.1f} m/s², average {mean:.1f} m/s². ArduPilot warns above 60 m/s². "
                f"Check propeller balance, motor mounts, FC isolation foam.")
    # CLIPPING (IMU saturation)
    if vibe and any(k in vibe for k in ("Clip0", "Clip1", "Clip2")):
        total_clip = 0
        for k in ("Clip0", "Clip1", "Clip2"):
            if k in vibe:
                arr = np.asarray(vibe[k], dtype=float)
                if len(arr):
                    total_clip += int(arr[-1] - arr[0])
        if total_clip == 0:
            add("IMU clipping", "Good", SUCCESS,
                "No accelerometer clipping events.",
                "Clip counters did not increase during the flight — the IMU never saturated.")
        elif total_clip < 100:
            add("IMU clipping", "Marginal", "#fbbf24",
                f"{total_clip} clipping events.",
                "A few events are usually fine but indicate occasional vibration spikes.")
        else:
            add("IMU clipping", "Bad", DANGER,
                f"{total_clip} clipping events — IMU saturated repeatedly.",
                "This usually points to severe vibration. Reduce vibration before flying again.")

    # ---------- GPS ----------
    gps = data.get("GPS")
    if gps:
        status = np.asarray(gps.get("Status", []), dtype=float) if "Status" in gps else None
        nsats = np.asarray(gps.get("NSats", []), dtype=float) if "NSats" in gps else None
        hdop = np.asarray(gps.get("HDop", []), dtype=float) if "HDop" in gps else None
        if status is not None and len(status):
            fix3d_pct = float((status >= 3).sum()) / len(status) * 100
            if nsats is not None and len(nsats):
                avg_sats = float(np.nanmean(nsats[status >= 3])) if (status >= 3).any() else 0
            else:
                avg_sats = 0
            if hdop is not None and len(hdop):
                hdop_valid = hdop[(status >= 3) & (hdop > 0) & (hdop < 50)]
                avg_hdop = float(np.nanmean(hdop_valid)) if len(hdop_valid) else 99
            else:
                avg_hdop = 99
            if fix3d_pct > 70 and avg_sats >= 8 and avg_hdop < 1.5:
                add("GPS", "Good", SUCCESS,
                    "GPS reception was strong throughout the flight.",
                    f"3D fix held {fix3d_pct:.0f}% of the time, average {avg_sats:.0f} satellites, "
                    f"average HDop {avg_hdop:.2f} (under 1.5 is excellent).")
            elif fix3d_pct > 50 and avg_sats >= 6 and avg_hdop < 2.5:
                add("GPS", "Marginal", "#fbbf24",
                    "GPS reception was acceptable but not great.",
                    f"3D fix {fix3d_pct:.0f}% of time, ~{avg_sats:.0f} sats, HDop {avg_hdop:.2f}. "
                    f"For modes that depend on GPS (Loiter/Auto/RTL) you want HDop <1.5 and ≥8 sats.")
            else:
                add("GPS", "Bad", DANGER,
                    "GPS reception was poor.",
                    f"3D fix only {fix3d_pct:.0f}% of time, ~{avg_sats:.0f} sats, HDop {avg_hdop:.2f}. "
                    f"Avoid GPS-dependent flight modes until reception improves (open sky, antenna placement).")

    # ---------- Battery ----------
    bat = None
    for k in ("BAT", "BAT1", "BATT"):
        if k in data and "Volt" in data[k]:
            bat = data[k]; break
    if bat:
        v = np.asarray(bat["Volt"], dtype=float)
        v = v[v > 1]  # filter zero readings
        if len(v):
            v_start = float(np.median(v[: max(1, len(v)//20)]))
            v_end = float(np.median(v[-max(1, len(v)//20):]))
            v_min = float(np.min(v))
            cells_guess = round(v_start / 3.85) if v_start > 5 else 0
            per_cell_min = v_min / cells_guess if cells_guess else 0
            if cells_guess and per_cell_min >= 3.6:
                add("Battery", "Good", SUCCESS,
                    f"Battery healthy ({v_start:.1f}V → {v_end:.1f}V, ~{cells_guess}S pack).",
                    f"Minimum voltage {v_min:.2f}V ({per_cell_min:.2f}V/cell). Above 3.6V/cell is comfortable.")
            elif cells_guess and per_cell_min >= 3.3:
                add("Battery", "Marginal", "#fbbf24",
                    f"Battery dipped low: {v_min:.2f}V minimum (~{per_cell_min:.2f}V/cell).",
                    f"Started at {v_start:.1f}V, ended at {v_end:.1f}V. Below 3.5V/cell under load is "
                    f"approaching the safe limit — land sooner or use a bigger pack.")
            else:
                add("Battery", "Bad", DANGER,
                    f"Battery sagged badly: {v_min:.2f}V minimum"
                    + (f" (~{per_cell_min:.2f}V/cell)" if cells_guess else "") + ".",
                    f"Below 3.3V/cell under load damages LiPo cells. Inspect the pack and reduce loading "
                    f"(prop size, weight) or replace it.")

    # ---------- Compass / magnetic field ----------
    mag = data.get("MAG")
    if mag and all(k in mag for k in ("MagX", "MagY", "MagZ")):
        mx = np.asarray(mag["MagX"], dtype=float)
        my = np.asarray(mag["MagY"], dtype=float)
        mz = np.asarray(mag["MagZ"], dtype=float)
        magn = np.sqrt(mx*mx + my*my + mz*mz)
        if len(magn):
            mean_m = float(np.nanmean(magn))
            std_m = float(np.nanstd(magn))
            ratio = std_m / mean_m if mean_m > 0 else 1
            if ratio < 0.05:
                add("Compass", "Good", SUCCESS,
                    "Magnetic field looks stable — no obvious interference.",
                    f"Mean field {mean_m:.0f} mGauss, variation ±{std_m:.0f} ({ratio*100:.1f}%).")
            elif ratio < 0.15:
                add("Compass", "Marginal", "#fbbf24",
                    "Magnetic field shows some variation.",
                    f"Mean {mean_m:.0f} mGauss, ±{std_m:.0f} ({ratio*100:.1f}%). Could be normal flight "
                    f"or mild interference — recheck after a Compass/Motor calibration.")
            else:
                add("Compass", "Bad", DANGER,
                    "Magnetic field is unstable — likely interference.",
                    f"Variation {ratio*100:.0f}% of the mean field. Check for power cables / ESCs near "
                    f"the compass, or run Compass-Motor calibration.")

    # ---------- EKF innovations ----------
    xkf = data.get("XKF4") or data.get("NKF4")
    if xkf and "SV" in xkf and "SP" in xkf:
        sv = np.asarray(xkf["SV"], dtype=float)
        sp = np.asarray(xkf["SP"], dtype=float)
        sv_max = float(np.nanmax(sv)) if len(sv) else 0
        sp_max = float(np.nanmax(sp)) if len(sp) else 0
        if sv_max < 0.5 and sp_max < 0.5:
            add("EKF (state estimator)", "Good", SUCCESS,
                "EKF was confident throughout the flight.",
                f"Velocity / position innovation peaks {sv_max:.2f} / {sp_max:.2f} (under 0.5 is healthy).")
        elif sv_max < 1.0 and sp_max < 1.0:
            add("EKF (state estimator)", "Marginal", "#fbbf24",
                "EKF saw moderate uncertainty at times.",
                f"Innovation peaks vel {sv_max:.2f}, pos {sp_max:.2f}. Above 1.0 the EKF can refuse to arm.")
        else:
            add("EKF (state estimator)", "Bad", DANGER,
                "EKF flagged high uncertainty.",
                f"Innovation peaks vel {sv_max:.2f}, pos {sp_max:.2f}. This often correlates with bad GPS, "
                f"compass interference, or vibration.")

    # ---------- Errors ----------
    err = data.get("ERR")
    if err:
        n_err = len(parsed["times"].get("ERR", []))
        if n_err == 0:
            add("Errors", "Good", SUCCESS, "No errors logged.", "")
        else:
            subs = err.get("Subsys", [])
            ecodes = err.get("ECode", [])
            samples = []
            for i in range(min(5, n_err)):
                samples.append(f"Subsys={subs[i] if i < len(subs) else '?'} "
                               f"ECode={ecodes[i] if i < len(ecodes) else '?'}")
            add("Errors", "Bad" if n_err > 3 else "Marginal",
                DANGER if n_err > 3 else "#fbbf24",
                f"{n_err} error event(s) logged.",
                "First few: " + " ; ".join(samples))

    # ---------- Altitude profile ----------
    pos = data.get("POS")
    if pos and "Alt" in pos:
        alt = np.asarray(pos["Alt"], dtype=float)
        alt = alt[~np.isnan(alt)]
        if len(alt) > 10:
            alt0 = float(np.median(alt[:10]))
            agl = alt - alt0
            max_h = float(np.max(agl))
            min_h = float(np.min(agl))
            t = parsed["times"].get("POS")
            climb_rate = 0.0
            if t is not None and len(t) == len(alt) and len(t) > 1:
                dt = np.diff(np.asarray(t, dtype=float))
                dz = np.diff(alt)
                rates = dz[dt > 0] / dt[dt > 0]
                climb_rate = float(np.nanmax(np.abs(rates))) if len(rates) else 0.0
            add("Altitude", "Info", ACCENT,
                f"Max height {max_h:+.1f} m AGL, lowest {min_h:+.1f} m, peak vertical speed {climb_rate:.1f} m/s.",
                f"Heights are relative to the takeoff altitude. Vertical speed peaks above 8 m/s "
                f"can indicate aggressive throttle response.")

    # ---------- Attitude (roll/pitch peaks) ----------
    att = data.get("ATT")
    if att and "Roll" in att and "Pitch" in att:
        roll = np.asarray(att["Roll"], dtype=float)
        pitch = np.asarray(att["Pitch"], dtype=float)
        peak_roll = float(np.nanmax(np.abs(roll)))
        peak_pitch = float(np.nanmax(np.abs(pitch)))
        peak = max(peak_roll, peak_pitch)
        if peak < 25:
            add("Attitude", "Good", SUCCESS,
                f"Gentle flight envelope (peak tilt {peak:.0f}°).",
                f"Maximum roll {peak_roll:.0f}°, pitch {peak_pitch:.0f}°. Under 25° = calm flying.")
        elif peak < 45:
            add("Attitude", "Info", ACCENT,
                f"Moderate manoeuvres (peak tilt {peak:.0f}°).",
                f"Roll {peak_roll:.0f}°, pitch {peak_pitch:.0f}°. Normal sport flying.")
        else:
            add("Attitude", "Marginal", "#fbbf24",
                f"Aggressive tilt angles (peak {peak:.0f}°).",
                f"Roll {peak_roll:.0f}°, pitch {peak_pitch:.0f}°. Above 45° the drone needs more "
                f"throttle just to stay level — fine for acro, watch altitude loss otherwise.")

    # ---------- Throttle / motor output balance ----------
    rcou = data.get("RCOU")
    if rcou:
        ch_keys = [k for k in rcou.keys() if k.startswith("C") and k[1:].isdigit()]
        ch_keys = sorted(ch_keys, key=lambda s: int(s[1:]))[:8]  # first 8 motors
        if len(ch_keys) >= 4:
            means = []
            for k in ch_keys:
                arr = np.asarray(rcou[k], dtype=float)
                arr = arr[(arr > 1050) & (arr < 2000)]  # only flying samples
                if len(arr): means.append(float(np.mean(arr)))
            if len(means) >= 4:
                spread = max(means) - min(means)
                avg = sum(means) / len(means)
                if spread < 60:
                    add("Motor balance", "Good", SUCCESS,
                        f"Motors well balanced (spread {spread:.0f} µs across {len(means)} motors).",
                        f"Average PWM {avg:.0f} µs. Less than 60 µs spread is healthy.")
                elif spread < 150:
                    add("Motor balance", "Marginal", "#fbbf24",
                        f"Motors slightly uneven (spread {spread:.0f} µs).",
                        f"Could be CG offset, prop wear, or one motor working harder. "
                        f"Check propellers and CG.")
                else:
                    add("Motor balance", "Bad", DANGER,
                        f"Motor output spread is large ({spread:.0f} µs).",
                        f"One motor is doing much more work than the others — usually a "
                        f"CG / weight imbalance, bent arm, or weak motor.")

    # ---------- Power consumption ----------
    bat_block = None
    for k in ("BAT", "BAT1", "BATT"):
        if k in data: bat_block = data[k]; break
    if bat_block and "CurrTot" in bat_block:
        ct = np.asarray(bat_block["CurrTot"], dtype=float)
        ct = ct[ct >= 0]
        if len(ct):
            mah = float(np.max(ct))
            add("Power used", "Info", ACCENT,
                f"Consumed {mah:.0f} mAh during the flight.",
                f"Compare to your pack capacity: try to land before using ~80%.")

    # ---------- RC signal ----------
    rcin = data.get("RCIN")
    if rcin:
        c1 = rcin.get("C1")
        if c1 is None:
            c1 = rcin.get("Chan1")
        if c1 is not None:
            arr = np.asarray(c1, dtype=float)
            failsafe_lo = (arr < 900).sum()
            valid = (arr >= 900).sum()
            if valid:
                pct_lost = failsafe_lo / (failsafe_lo + valid) * 100
                if pct_lost == 0:
                    add("RC link", "Good", SUCCESS, "RC signal stable for the entire flight.", "")
                elif pct_lost < 1:
                    add("RC link", "Marginal", "#fbbf24",
                        f"{failsafe_lo} brief RC dropouts ({pct_lost:.1f}% of samples).",
                        "A few short losses are common at long range. Check antenna orientation.")
                else:
                    add("RC link", "Bad", DANGER,
                        f"RC signal lost {pct_lost:.1f}% of the time.",
                        "Significant link issues — check transmitter antenna, receiver placement, "
                        "and avoid flying near 2.4 GHz interference.")

    # ---------- Loop performance ----------
    pm = data.get("PM")
    if pm and "MaxT" in pm:
        max_t = np.asarray(pm["MaxT"], dtype=float)
        max_t = max_t[max_t > 0]
        if len(max_t):
            peak_us = float(np.max(max_t))
            avg_us = float(np.mean(max_t))
            # Most coptr setups run at 400 Hz = 2500 us budget
            if peak_us < 2500:
                add("Autopilot CPU", "Good", SUCCESS,
                    f"Main loop ran on time (peak {peak_us:.0f} µs).",
                    "Flight controller had headroom throughout the flight.")
            elif peak_us < 4000:
                add("Autopilot CPU", "Marginal", "#fbbf24",
                    f"Occasional loop overruns (peak {peak_us:.0f} µs, avg {avg_us:.0f}).",
                    "A few late loops are normal. If this gets worse, consider reducing logging "
                    "rate or disabling unused features.")
            else:
                add("Autopilot CPU", "Bad", DANGER,
                    f"Loop overruns are significant (peak {peak_us:.0f} µs).",
                    "The autopilot is missing its real-time deadline. Reduce logging, disable "
                    "unused sensors, or check for a CPU-intensive parameter setting.")

    # ---------- IMU temperature stability ----------
    imu = data.get("IMU")
    if imu and "T" in imu:
        T = np.asarray(imu["T"], dtype=float)
        T = T[(T > -40) & (T < 120)]
        if len(T):
            t_min, t_max = float(np.min(T)), float(np.max(T))
            spread = t_max - t_min
            if spread < 5:
                add("IMU temperature", "Good", SUCCESS,
                    f"IMU stayed thermally stable ({t_min:.0f}–{t_max:.0f} °C).",
                    "Steady temperature means consistent gyro/accelerometer bias.")
            elif spread < 15:
                add("IMU temperature", "Info", ACCENT,
                    f"IMU temperature swung {spread:.0f} °C ({t_min:.0f}–{t_max:.0f} °C).",
                    "Mild drift is normal during a flight, especially in cold weather takeoffs.")
            else:
                add("IMU temperature", "Marginal", "#fbbf24",
                    f"Large IMU temperature swing ({spread:.0f} °C).",
                    "Big temperature shifts can shift gyro bias. Consider IMU heating or letting "
                    "the FC warm up before arming.")

    # ---------- Flight modes summary ----------
    mode = data.get("MODE")
    if mode and "Mode" in mode:
        modes = mode["Mode"]
        unique = []
        for m in modes:
            if not unique or unique[-1] != m:
                unique.append(m)
        add("Flight modes", "Info", ACCENT,
            f"{len(unique)} mode change(s): " + " → ".join(str(m) for m in unique),
            "")

    if not items:
        add("No data", "Info", TEXT_DIM,
            "Couldn't run the auto-review.",
            "Standard message types (VIBE, GPS, BAT, MAG, ERR) were not found in this log.")
    return items


class LogParseWorker(QThread):
    progress = pyqtSignal(int, str)
    done = pyqtSignal(object)  # dict
    error = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        # Open WITHOUT zero_time_base so pymavlink fills in real wall-clock
        # timestamps from GPS week/ms — _timestamp becomes Unix epoch seconds.
        try:
            mlog = DFReader.DFReader_binary(self.path)
        except Exception as exc:
            self.error.emit(f"Could not open log: {exc}")
            return

        data: dict[str, dict[str, list]] = {}
        times: dict[str, list] = {}      # Unix epoch seconds
        fieldnames_cache: dict[str, list[str]] = {}
        count = 0
        t_start: float | None = None
        t_end: float | None = None
        try:
            while True:
                msg = mlog.recv_match()
                if msg is None:
                    break
                mtype = msg.get_type()
                if mtype in ("FMT", "FMTU", "UNIT", "MULT", "FILE"):
                    continue
                ts = getattr(msg, "_timestamp", None)
                if ts is None:
                    continue
                if t_start is None or ts < t_start:
                    t_start = ts
                if t_end is None or ts > t_end:
                    t_end = ts
                if mtype not in fieldnames_cache:
                    fmt = getattr(msg, "fmt", None)
                    cols = list(getattr(fmt, "columns", []) or [])
                    if not cols:
                        cols = [k for k in msg.to_dict().keys() if k != "mavpackettype"]
                    fieldnames_cache[mtype] = cols
                    data[mtype] = {f: [] for f in cols}
                    times[mtype] = []
                for f in fieldnames_cache[mtype]:
                    data[mtype][f].append(getattr(msg, f, None))
                times[mtype].append(ts)
                count += 1
                if count % 50000 == 0:
                    self.progress.emit(count, mtype)
        except Exception as exc:
            self.error.emit(f"Parse error after {count} messages: {exc}\n{traceback.format_exc()}")
            return

        for mt, fields in data.items():
            for f, vals in fields.items():
                try:
                    fields[f] = np.array(vals)
                except Exception:
                    pass
            times[mt] = np.array(times[mt], dtype=float)

        duration = (t_end - t_start) if (t_start and t_end) else 0.0

        result = {
            "data": data,
            "times": times,            # Unix epoch seconds
            "count": count,
            "duration": duration,
            "t_start": t_start,
            "t_end": t_end,
            "path": self.path,
            "vehicle_type": getattr(mlog, "mav_type", None),
            "params": dict(getattr(mlog, "params", {})),
            "messages_meta": getattr(mlog, "messages", {}),
        }
        self.done.emit(result)


class IstanbulTimeAxis(pg.AxisItem):
    """X axis that displays Unix-epoch seconds as Istanbul wall-clock time."""
    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            try:
                dt = datetime.fromtimestamp(float(v), tz=ISTANBUL_TZ)
            except (OSError, OverflowError, ValueError):
                out.append("")
                continue
            if spacing >= 3600:
                out.append(dt.strftime("%H:%M"))
            elif spacing >= 1:
                out.append(dt.strftime("%H:%M:%S"))
            else:
                out.append(dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}")
        return out


class CrosshairPlot(pg.PlotWidget):
    """PlotWidget with a vertical crosshair that reports time-of-day + y."""
    def __init__(self, status_label: QtWidgets.QLabel, parent=None):
        axis = IstanbulTimeAxis(orientation="bottom")
        super().__init__(parent, axisItems={"bottom": axis})
        self.status_label = status_label
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(ACCENT, width=1, style=Qt.PenStyle.DashLine))
        self.addItem(self.vline, ignoreBounds=True)
        self.vline.hide()
        self.scene().sigMouseMoved.connect(self._on_mouse)

    def _on_mouse(self, pos):
        if not self.sceneBoundingRect().contains(pos):
            return
        view = self.plotItem.vb.mapSceneToView(pos)
        x, y = view.x(), view.y()
        self.vline.setPos(x)
        self.vline.show()
        self.status_label.setText(
            f"◇   {fmt_istanbul(x, with_date=False)}  TR     y = {y:0.4f}"
        )


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UAV Log Viewer")
        self.resize(1500, 950)

        self.parsed: dict | None = None
        self.curves: dict[tuple[str, str], pg.PlotDataItem] = {}
        self.color_idx = 0
        self.worker: LogParseWorker | None = None

        self._build_menu()
        self._build_ui()

    # ----- UI -----
    def _build_menu(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        open_act = QtGui.QAction("&Open .bin…", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self.open_file)
        file_menu.addAction(open_act)
        file_menu.addSeparator()
        quit_act = QtGui.QAction("&Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        view_menu = bar.addMenu("&View")
        clear_act = QtGui.QAction("Clear plot", self)
        clear_act.triggered.connect(self.clear_plot)
        view_menu.addAction(clear_act)

    def _build_ui(self):
        # Root container with header on top, splitter below
        root = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Header bar ---
        header = QtWidgets.QFrame()
        header.setObjectName("header")
        header.setStyleSheet(
            f"QFrame#header {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {BG_1}, stop:0.6 {BG_0}, stop:1 {BG_1});"
            f"border-bottom: 1px solid {BORDER}; }}"
        )
        header.setFixedHeight(72)
        h = QtWidgets.QHBoxLayout(header)
        h.setContentsMargins(22, 10, 22, 10)
        h.setSpacing(14)

        # Logo + status indicator
        logo_block = QtWidgets.QHBoxLayout()
        logo_block.setSpacing(10)
        logo = QtWidgets.QLabel("◆")
        logo.setStyleSheet(
            f"color:{ACCENT}; font-size:26px; font-weight:600;"
            f"padding:0 4px;"
        )
        logo_block.addWidget(logo)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(0)
        title = QtWidgets.QLabel("UAV LOG VIEWER")
        title.setStyleSheet(
            f"color:{TEXT}; font-size:16px; font-weight:800; letter-spacing:3px;"
        )
        subtitle = QtWidgets.QLabel("◢  ARDUPILOT TELEMETRY ANALYZER")
        subtitle.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; letter-spacing:2px; font-weight:600;"
        )
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        logo_block.addLayout(title_box)
        h.addLayout(logo_block)

        # Status indicator (pulses when loaded)
        self.status_dot = QtWidgets.QLabel("●")
        self.status_dot.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px;"
        )
        self.status_dot.setToolTip("No log loaded")
        h.addWidget(self.status_dot)
        self.status_dot_text = QtWidgets.QLabel("STANDBY")
        self.status_dot_text.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; letter-spacing:2px; font-weight:600;"
        )
        h.addWidget(self.status_dot_text)

        h.addStretch(1)

        # Telemetry summary chip
        self.header_summary = QtWidgets.QLabel("no log loaded")
        self.header_summary.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; padding:8px 14px;"
            f"background:{BG_2}; border:1px solid {BORDER}; border-radius:8px;"
            f"font-family:'SF Mono', Menlo, monospace;"
        )
        h.addWidget(self.header_summary)

        # Prominent credit badge in the header
        credit_badge = QtWidgets.QLabel(
            f"<span style='color:{TEXT_DIM};font-size:10px;letter-spacing:2px;font-weight:600;'>CREATED BY</span>"
            f"&nbsp;&nbsp;<span style='color:{ACCENT};font-size:16px;font-weight:800;letter-spacing:1.5px;'>JAVID</span>"
        )
        credit_badge.setTextFormat(Qt.TextFormat.RichText)
        credit_badge.setStyleSheet(
            f"padding:10px 18px;"
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {BG_2}, stop:1 {BG_1});"
            f"border:1px solid {ACCENT}; border-radius:8px;"
        )
        h.addWidget(credit_badge)

        open_btn = QtWidgets.QPushButton("◉  OPEN LOG")
        open_btn.setObjectName("primary")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setMinimumHeight(38)
        open_btn.clicked.connect(self.open_file)
        h.addWidget(open_btn)
        root_layout.addWidget(header)

        # Thin gradient accent line under the header (cyan → violet)
        accent_line = QtWidgets.QFrame()
        accent_line.setFixedHeight(2)
        accent_line.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {ACCENT}, stop:0.5 {ACCENT_2}, stop:1 {ACCENT});"
        )
        root_layout.addWidget(accent_line)

        # --- Body splitter ---
        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Left: searchable message tree
        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(12, 12, 6, 12)
        lv.setSpacing(8)

        sidebar_label = QtWidgets.QLabel("MESSAGES")
        sidebar_label.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-weight:600;"
            f"letter-spacing:1.5px; padding:0 4px;"
        )
        lv.addWidget(sidebar_label)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("🔍  Filter messages or fields…")
        self.search.textChanged.connect(self._apply_filter)
        lv.addWidget(self.search)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Message · Field"])
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(14)
        self.tree.itemChanged.connect(self.on_tree_changed)
        lv.addWidget(self.tree, 1)
        splitter.addWidget(left)

        # Right: tabs
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.setContentsMargins(6, 12, 12, 12)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)

        # Plot tab
        plot_container = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(plot_container)
        pv.setContentsMargins(8, 8, 8, 8)
        pv.setSpacing(6)

        # Plot toolbar
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(8)
        self.plot_count_label = QtWidgets.QLabel("0 series")
        self.plot_count_label.setStyleSheet(
            f"color:{TEXT_DIM}; padding:4px 10px; background:{BG_2};"
            f"border:1px solid {BORDER}; border-radius:6px; font-size:11px;"
        )
        toolbar.addWidget(self.plot_count_label)
        toolbar.addStretch(1)
        clear_btn = QtWidgets.QPushButton("✕  Clear all")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self.clear_plot)
        toolbar.addWidget(clear_btn)
        pv.addLayout(toolbar)

        self.cursor_label = QtWidgets.QLabel("◇  hover the plot for cursor readout")
        self.cursor_label.setStyleSheet(
            f"color:{TEXT_DIM}; padding:6px 10px; background:{BG_2};"
            f"border:1px solid {BORDER}; border-radius:6px;"
            f"font-family: Menlo, Monaco, Consolas, monospace; font-size:11px;"
        )
        self.plot = CrosshairPlot(self.cursor_label)
        self.plot.addLegend(
            offset=(10, 10),
            brush=pg.mkBrush(BG_2),
            pen=pg.mkPen(BORDER),
            labelTextColor=TEXT,
        )
        self.plot.showGrid(x=True, y=True, alpha=0.15)
        for axis_name in ("left", "bottom"):
            ax = self.plot.getAxis(axis_name)
            ax.setPen(pg.mkPen(BORDER))
            ax.setTextPen(pg.mkPen(TEXT_DIM))
        self.plot.setLabel("bottom", "Time (Istanbul, UTC+3)", color=TEXT_DIM)
        pv.addWidget(self.plot, 1)
        pv.addWidget(self.cursor_label)
        self.tabs.addTab(plot_container, "  📈  Plot  ")

        # Map tab
        self.map_view = QWebEngineView()
        self.map_view.loadFinished.connect(self._on_map_loaded)
        self._set_map_coords([])
        self.tabs.addTab(self.map_view, "  🗺  Map  ")

        # 3D tab (Plotly via WebEngine — same tech as the map, no GL conflict)
        self.view3d = QWebEngineView()
        self.view3d.loadFinished.connect(self._on_3d_loaded)
        self._set_3d_points(None)
        self.tabs.addTab(self.view3d, "  ◧  3D  ")

        # Auto Review tab
        review_container = QtWidgets.QScrollArea()
        review_container.setWidgetResizable(True)
        review_container.setStyleSheet(f"background:{BG_1};border:1px solid {BORDER};border-radius:8px;")
        self.review_inner = QtWidgets.QWidget()
        self.review_inner.setStyleSheet(f"background:{BG_1};")
        self.review_layout = QtWidgets.QVBoxLayout(self.review_inner)
        self.review_layout.setContentsMargins(18, 18, 18, 18)
        self.review_layout.setSpacing(12)
        self._review_placeholder()
        review_container.setWidget(self.review_inner)
        self.tabs.addTab(review_container, "  ✓  Auto Review  ")

        # Info tab
        self.info_text = QtWidgets.QPlainTextEdit()
        self.info_text.setReadOnly(True)
        self.tabs.addTab(self.info_text, "  ⓘ  Info  ")

        rv.addWidget(self.tabs)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 1160])
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(root)

        self.statusBar().showMessage("Open a .bin log (⌘O / Ctrl+O) to begin")

    # ----- File loading -----
    def open_file(self):
        start_dir = str(Path(__file__).parent)
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open ArduPilot DataFlash log", start_dir, "Binary logs (*.bin);;All files (*)"
        )
        if not path:
            return
        self.load_file(path)

    def load_file(self, path: str):
        if self.worker and self.worker.isRunning():
            return
        self.statusBar().showMessage(f"Parsing {Path(path).name}…")
        self.tree.clear()
        self.clear_plot()
        self.info_text.clear()
        self.worker = LogParseWorker(path)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_parsed)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, count: int, mtype: str):
        self.statusBar().showMessage(f"Parsed {count:,} messages… (last: {mtype})")

    def _on_error(self, msg: str):
        self.statusBar().showMessage("Parse failed.")
        QtWidgets.QMessageBox.critical(self, "Parse error", msg)

    def _on_parsed(self, result: dict):
        self.parsed = result
        name = Path(result["path"]).name
        start_txt = fmt_istanbul(result["t_start"], with_date=True) if result.get("t_start") else "—"
        msg = f"◉  LOG ACTIVE   ·   {name}   ·   {result['count']:,} MSGS   ·   {result['duration']:0.1f}s   ·   START {start_txt} TR"
        self.statusBar().showMessage(msg)
        self.header_summary.setText(
            f"<span style='color:{TEXT}'>{name}</span>"
            f"   ·   <span style='color:{ACCENT}'>{result['count']:,}</span> msgs"
            f"   ·   <span style='color:{ACCENT}'>{result['duration']:0.1f}s</span>"
            f"   ·   <span style='color:{TEXT_DIM}'>{start_txt} TR</span>"
        )
        self.header_summary.setTextFormat(Qt.TextFormat.RichText)
        # Status dot → live cyan
        self.status_dot.setStyleSheet(f"color:{SUCCESS}; font-size:11px;")
        self.status_dot.setToolTip("Log active")
        self.status_dot_text.setStyleSheet(
            f"color:{SUCCESS}; font-size:10px; letter-spacing:2px; font-weight:700;"
        )
        self.status_dot_text.setText("LIVE")
        self._populate_tree()
        self._populate_info()
        self._populate_map()
        self._populate_3d()
        self._populate_review()

    # ----- Tree -----
    def _populate_tree(self):
        assert self.parsed is not None
        self.tree.blockSignals(True)
        self.tree.clear()
        for mtype in sorted(self.parsed["data"].keys()):
            fields = self.parsed["data"][mtype]
            n = len(self.parsed["times"][mtype])
            top = QtWidgets.QTreeWidgetItem([f"{mtype}  ({n})"])
            top.setFlags(top.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            for fname, arr in fields.items():
                if fname in ("TimeUS", "TimeMS"):
                    continue  # internal timestamp — not plottable as a series
                if not self._is_plottable(arr):
                    continue
                child = QtWidgets.QTreeWidgetItem([fname])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Unchecked)
                child.setData(0, Qt.ItemDataRole.UserRole, (mtype, fname))
                top.addChild(child)
            if top.childCount() > 0:
                self.tree.addTopLevelItem(top)
        self.tree.blockSignals(False)

    @staticmethod
    def _is_plottable(arr) -> bool:
        if isinstance(arr, np.ndarray):
            return arr.dtype.kind in ("i", "u", "f", "b")
        return False

    def _apply_filter(self, text: str):
        text = text.lower().strip()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            top_text = top.text(0).lower()
            any_visible = False
            for j in range(top.childCount()):
                child = top.child(j)
                visible = (not text) or (text in top_text) or (text in child.text(0).lower())
                child.setHidden(not visible)
                any_visible = any_visible or visible
            top.setHidden(not any_visible)

    def on_tree_changed(self, item: QtWidgets.QTreeWidgetItem, column: int):
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if not payload:
            return
        key = tuple(payload)
        if item.checkState(0) == Qt.CheckState.Checked:
            self._add_curve(key[0], key[1])
        else:
            self._remove_curve(key)

    # ----- Plot -----
    def _update_plot_count(self):
        n = len(self.curves)
        self.plot_count_label.setText(f"{n} series" if n != 1 else "1 series")

    def _add_curve(self, mtype: str, field: str):
        key = (mtype, field)
        if key in self.curves or self.parsed is None:
            return
        x = self.parsed["times"][mtype]
        y = self.parsed["data"][mtype][field]
        if len(x) == 0:
            return
        color = PLOT_COLORS[self.color_idx % len(PLOT_COLORS)]
        self.color_idx += 1
        pen = pg.mkPen(color=color, width=1.8)
        curve = self.plot.plot(x, y, pen=pen, name=f"{mtype}.{field}")
        self.curves[key] = curve
        self._update_plot_count()

    def _remove_curve(self, key: tuple[str, str]):
        curve = self.curves.pop(key, None)
        if curve is not None:
            self.plot.removeItem(curve)
            self.plot.plotItem.legend.removeItem(curve)
        self._update_plot_count()

    def clear_plot(self):
        for key in list(self.curves.keys()):
            self._remove_curve(key)
        # Uncheck all tree items
        if self.tree.topLevelItemCount() == 0:
            return
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                top.child(j).setCheckState(0, Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)

    # ----- Info tab -----
    def _populate_info(self):
        assert self.parsed is not None
        d = self.parsed
        lines = []
        lines.append(f"File:         {d['path']}")
        lines.append(f"Messages:     {d['count']:,}")
        lines.append(f"Duration:     {d['duration']:0.2f} s ({d['duration']/60:0.2f} min)")
        if d.get("t_start"):
            lines.append(f"Start (TR):   {fmt_istanbul(d['t_start'], with_date=True)}")
            lines.append(f"End   (TR):   {fmt_istanbul(d['t_end'],   with_date=True)}")
        lines.append(f"Vehicle type: {d.get('vehicle_type')}")
        lines.append("")

        # Mode changes
        mode_msgs = d["data"].get("MODE")
        mode_times = d["times"].get("MODE")
        if mode_msgs is not None and mode_times is not None and len(mode_times):
            lines.append("Flight modes (Istanbul time):")
            mode_field = "Mode" if "Mode" in mode_msgs else next(iter(mode_msgs.keys()))
            seen = []
            for t, m in zip(mode_times, mode_msgs[mode_field]):
                if not seen or seen[-1][1] != m:
                    seen.append((float(t), m))
            for t, m in seen:
                lines.append(f"  {fmt_istanbul(t)}   {m}")
            lines.append("")

        # Errors / events
        for evt_type in ("ERR", "EV", "MSG"):
            if evt_type in d["data"]:
                lines.append(f"{evt_type} events: {len(d['times'][evt_type])}")
                fields = d["data"][evt_type]
                show = min(20, len(d["times"][evt_type]))
                for i in range(show):
                    t = float(d["times"][evt_type][i])
                    parts = [f"{k}={fields[k][i]!r}" for k in fields]
                    lines.append(f"  {fmt_istanbul(t)}   " + "  ".join(parts))
                if show < len(d["times"][evt_type]):
                    lines.append(f"  … ({len(d['times'][evt_type]) - show} more)")
                lines.append("")

        # Battery summary
        for bt in ("BAT", "BAT1", "BATT"):
            if bt in d["data"] and "Volt" in d["data"][bt]:
                v = d["data"][bt]["Volt"]
                lines.append(f"{bt}: V min={float(np.min(v)):.2f} max={float(np.max(v)):.2f} mean={float(np.mean(v)):.2f}")
                if "Curr" in d["data"][bt]:
                    c = d["data"][bt]["Curr"]
                    lines.append(f"      A min={float(np.min(c)):.2f} max={float(np.max(c)):.2f} mean={float(np.mean(c)):.2f}")
                break
        lines.append("")

        lines.append(f"Message types ({len(d['data'])}):")
        for mt in sorted(d["data"].keys()):
            lines.append(f"  {mt:<8}  n={len(d['times'][mt])}")

        self.info_text.setPlainText("\n".join(lines))

    # ----- Auto Review tab -----
    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _review_placeholder(self):
        lbl = QtWidgets.QLabel("Open a log to see an automatic flight health review.")
        lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:13px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.review_layout.addWidget(lbl)
        self.review_layout.addStretch(1)

    def _populate_review(self):
        self._clear_layout(self.review_layout)
        items = auto_review(self.parsed)

        # Tally for the overall score
        n_good = sum(1 for it in items if it["verdict"] == "Good")
        n_marg = sum(1 for it in items if it["verdict"] == "Marginal")
        n_bad = sum(1 for it in items if it["verdict"] == "Bad")
        n_info = sum(1 for it in items if it["verdict"] == "Info")

        if n_bad > 0:
            overall_color, overall_text = DANGER, "Needs attention"
            overall_blurb = "Some flight data points to issues that should be looked at before the next flight."
        elif n_marg > 0:
            overall_color, overall_text = "#fbbf24", "Acceptable"
            overall_blurb = "The flight was usable, but a few things are on the marginal side."
        elif n_good > 0:
            overall_color, overall_text = SUCCESS, "Healthy flight"
            overall_blurb = "All measured systems behaved well throughout the flight."
        else:
            overall_color, overall_text = TEXT_DIM, "Limited data"
            overall_blurb = "Not enough standard data to grade the flight."

        # ---- Overall score card ----
        score_card = QtWidgets.QFrame()
        score_card.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {BG_2}, stop:1 {BG_1});"
            f" border:1px solid {BORDER};"
            f" border-left: 5px solid {overall_color};"
            f" border-radius:12px; }}"
        )
        score_shadow = QtWidgets.QGraphicsDropShadowEffect()
        score_shadow.setBlurRadius(24)
        score_shadow.setOffset(0, 4)
        score_shadow.setColor(QtGui.QColor(0, 0, 0, 120))
        score_card.setGraphicsEffect(score_shadow)
        sl = QtWidgets.QHBoxLayout(score_card)
        sl.setContentsMargins(20, 18, 20, 18)
        sl.setSpacing(20)

        # Big icon block
        icon = QtWidgets.QLabel("◈")
        icon.setStyleSheet(
            f"color:{overall_color}; font-size:36px; font-weight:700;"
            f"min-width:44px; max-width:44px;"
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(icon)

        # Verdict text
        text_block = QtWidgets.QVBoxLayout()
        text_block.setSpacing(2)
        kicker = QtWidgets.QLabel("OVERALL FLIGHT HEALTH")
        kicker.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; font-weight:600; letter-spacing:2px;"
        )
        verdict = QtWidgets.QLabel(overall_text)
        verdict.setStyleSheet(
            f"color:{overall_color}; font-size:22px; font-weight:700; letter-spacing:0.5px;"
        )
        blurb = QtWidgets.QLabel(overall_blurb)
        blurb.setStyleSheet(f"color:{TEXT_DIM}; font-size:12px;")
        blurb.setWordWrap(True)
        text_block.addWidget(kicker)
        text_block.addWidget(verdict)
        text_block.addWidget(blurb)
        sl.addLayout(text_block, 1)

        # Tally chips
        for label, count, col in (
            ("good", n_good, SUCCESS),
            ("marginal", n_marg, "#fbbf24"),
            ("bad", n_bad, DANGER),
            ("info", n_info, ACCENT),
        ):
            chip = QtWidgets.QFrame()
            chip.setStyleSheet(
                f"QFrame {{ background:{BG_0}; border:1px solid {BORDER};"
                f" border-radius:8px; min-width:64px; max-width:80px; }}"
            )
            cl = QtWidgets.QVBoxLayout(chip)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(0)
            num = QtWidgets.QLabel(str(count))
            num.setStyleSheet(f"color:{col}; font-size:20px; font-weight:700;")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab = QtWidgets.QLabel(label)
            lab.setStyleSheet(f"color:{TEXT_DIM}; font-size:10px; letter-spacing:1px;")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(num)
            cl.addWidget(lab)
            sl.addWidget(chip)

        self.review_layout.addWidget(score_card)

        # ---- Findings header ----
        findings_lbl = QtWidgets.QLabel("DETAILED FINDINGS")
        findings_lbl.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-weight:600; letter-spacing:2px;"
            f"padding:8px 4px 0 4px;"
        )
        self.review_layout.addWidget(findings_lbl)

        # ---- Per-finding cards ----
        for it in items:
            card = QtWidgets.QFrame()
            card.setStyleSheet(
                f"QFrame {{ background:{BG_2}; border:1px solid {BORDER};"
                f" border-left: 4px solid {it['color']}; border-radius:8px; }}"
                f"QFrame:hover {{ background:{BG_3}; border-color:{it['color']}; }}"
            )
            v = QtWidgets.QVBoxLayout(card)
            v.setContentsMargins(16, 12, 16, 12)
            v.setSpacing(4)

            top = QtWidgets.QHBoxLayout()
            cat = QtWidgets.QLabel(it["category"])
            cat.setStyleSheet(
                f"color:{TEXT}; font-size:13px; font-weight:600; letter-spacing:0.3px;"
            )
            top.addWidget(cat)
            top.addStretch(1)
            badge = QtWidgets.QLabel(it["verdict"].upper())
            badge.setStyleSheet(
                f"background:{it['color']}; color:{BG_0};"
                f"padding:3px 12px; border-radius:10px;"
                f"font-size:10px; font-weight:700; letter-spacing:1.2px;"
            )
            top.addWidget(badge)
            v.addLayout(top)

            head = QtWidgets.QLabel(it["headline"])
            head.setWordWrap(True)
            head.setStyleSheet(f"color:{TEXT}; font-size:13px;")
            v.addWidget(head)

            if it["detail"]:
                det = QtWidgets.QLabel(it["detail"])
                det.setWordWrap(True)
                det.setStyleSheet(f"color:{TEXT_DIM}; font-size:12px; padding-top:2px;")
                v.addWidget(det)

            self.review_layout.addWidget(card)

        self.review_layout.addStretch(1)

    # ----- 3D tab -----
    def _populate_3d(self):
        if self.parsed is None:
            self._set_3d_points(None)
            return
        # Pull lat/lng/alt from POS first, else GPS with valid fix
        coords = None
        for mt in ("POS", "GPS"):
            block = self.parsed["data"].get(mt)
            if not block: continue
            if "Lat" not in block or "Lng" not in block: continue
            lats = np.asarray(block["Lat"], dtype=float)
            lngs = np.asarray(block["Lng"], dtype=float)
            alts = np.asarray(block.get("Alt", np.zeros_like(lats)), dtype=float)
            if np.nanmax(np.abs(lats)) > 200:
                lats = lats / 1e7; lngs = lngs / 1e7
            mask = (np.abs(lats) > 0.0001) & (np.abs(lngs) > 0.0001)
            if mt.startswith("GPS"):
                if "Status" in block:
                    mask &= np.asarray(block["Status"], dtype=float) >= 3
                if "NSats" in block:
                    mask &= np.asarray(block["NSats"], dtype=float) >= 4
            lats = lats[mask]; lngs = lngs[mask]; alts = alts[mask]
            if len(lats) >= 2:
                coords = (lats, lngs, alts)
                break

        if coords is None:
            self._set_3d_points(None)
            return

        lats, lngs, alts = coords
        lat0, lng0 = float(lats[0]), float(lngs[0])
        alt0 = float(alts[0])
        # Flat-earth conversion to local meters (fine for short flights)
        m_per_deg_lat = 111320.0
        m_per_deg_lng = 111320.0 * np.cos(np.radians(lat0))
        x = (lngs - lng0) * m_per_deg_lng     # East
        y = (lats - lat0) * m_per_deg_lat     # North
        z = alts - alt0                        # Altitude AGL

        # Downsample to keep Plotly snappy
        if len(x) > 4000:
            step = len(x) // 4000
            x = x[::step]; y = y[::step]; z = z[::step]

        self._set_3d_points({
            "x": [float(v) for v in x],
            "y": [float(v) for v in y],
            "z": [float(v) for v in z],
        })

    def _set_3d_points(self, pts):
        html = PLOT3D_HTML_TEMPLATE.replace("__PTS__", json.dumps(pts) if pts else "null")
        self.view3d.setHtml(html, QtCore.QUrl("https://localhost/"))

    def _on_3d_loaded(self, ok: bool):
        if not ok:
            self.statusBar().showMessage("3D view failed to load.")

    # ----- Map tab -----
    def _populate_map(self):
        coords = self._extract_track()
        self._set_map_coords(coords)

    def _extract_track(self) -> list[list[float]]:
        """Return a clean lat/lng track. Prefer POS (EKF-smoothed) over raw GPS."""
        if self.parsed is None:
            return []
        # POS first — fewer outliers, no noisy pre-fix points
        for mt in ("POS", "GPS", "GPS2"):
            block = self.parsed["data"].get(mt)
            if not block:
                continue
            lat_key = next((k for k in ("Lat", "lat") if k in block), None)
            lng_key = next((k for k in ("Lng", "Lon", "lng", "lon") if k in block), None)
            if not lat_key or not lng_key:
                continue

            lats = np.asarray(block[lat_key], dtype=float)
            lngs = np.asarray(block[lng_key], dtype=float)
            if len(lats) == 0:
                continue

            # Older logs store lat/lng as int * 1e7 — pymavlink usually scales
            # already, but guard for edge cases.
            if np.nanmax(np.abs(lats)) > 200:
                lats = lats / 1e7
                lngs = lngs / 1e7

            # Drop zero/null fixes
            mask = (np.abs(lats) > 0.0001) & (np.abs(lngs) > 0.0001)
            # If GPS, also require a 3D fix and decent satellite count
            if mt.startswith("GPS"):
                status = block.get("Status")
                nsats = block.get("NSats")
                if status is not None:
                    mask &= np.asarray(status, dtype=float) >= 3
                if nsats is not None:
                    mask &= np.asarray(nsats, dtype=float) >= 4

            lats = lats[mask]
            lngs = lngs[mask]
            if len(lats) < 2:
                continue

            # Tighten — drop single-point outliers > 1 km from the median
            med_la, med_lo = float(np.median(lats)), float(np.median(lngs))
            jump_mask = (np.abs(lats - med_la) < 0.01) & (np.abs(lngs - med_lo) < 0.01)
            lats = lats[jump_mask]
            lngs = lngs[jump_mask]
            if len(lats) < 2:
                continue

            # Downsample for Leaflet
            if len(lats) > 5000:
                step = len(lats) // 5000
                lats = lats[::step]
                lngs = lngs[::step]
            return [[float(la), float(lo)] for la, lo in zip(lats, lngs)]
        return []

    def _set_map_coords(self, coords: list[list[float]]):
        html = MAP_HTML_TEMPLATE.replace("__COORDS__", json.dumps(coords))
        # setHtml with a real https base URL — lets QtWebEngine load https
        # scripts (Leaflet from unpkg) and tiles (Esri/CARTO) without the
        # file:// "null origin" mixed-content restrictions.
        self.map_view.setHtml(html, QtCore.QUrl("https://localhost/"))

    def _on_map_loaded(self, ok: bool):
        if not ok:
            self.statusBar().showMessage("Map failed to load (check internet connection for satellite tiles).")


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("UAV Log Viewer")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
    # Fusion dark palette so native chrome (titlebar dropdowns, etc.) matches
    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(BG_0))
    pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(BG_1))
    pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(BG_2))
    pal.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(BG_2))
    pal.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(ACCENT))
    pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(BG_0))
    pal.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(BG_2))
    pal.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor(TEXT))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        QtCore.QTimer.singleShot(50, lambda: win.load_file(sys.argv[1]))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
