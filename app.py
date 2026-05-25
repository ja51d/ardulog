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
# Configuration — runtime-configurable via Preferences dialog.
# ----------------------------------------------------------------------------
try:
    from zoneinfo import ZoneInfo
    _HAVE_ZONEINFO = True
except ImportError:
    _HAVE_ZONEINFO = False

# Default zone: Istanbul (UTC+3, no DST)
ISTANBUL_TZ = (ZoneInfo("Europe/Istanbul") if _HAVE_ZONEINFO
               else timezone(timedelta(hours=3), name="Istanbul"))
TZ_NAME = "Europe/Istanbul"
TZ_LABEL = "TR"

# Pretty list of common timezones for the Settings dialog
COMMON_TIMEZONES = [
    ("Europe/Istanbul",      "TR",  "Türkiye (Istanbul)"),
    ("UTC",                  "UTC", "Coordinated Universal Time"),
    ("Europe/London",        "GB",  "United Kingdom (London)"),
    ("Europe/Berlin",        "CE",  "Central Europe (Berlin, Paris)"),
    ("Europe/Moscow",        "MSK", "Russia (Moscow)"),
    ("America/New_York",     "ET",  "US Eastern (New York)"),
    ("America/Chicago",      "CT",  "US Central (Chicago)"),
    ("America/Denver",       "MT",  "US Mountain (Denver)"),
    ("America/Los_Angeles",  "PT",  "US Pacific (Los Angeles)"),
    ("Asia/Dubai",           "GST", "UAE (Dubai)"),
    ("Asia/Kolkata",         "IST", "India (Delhi, Mumbai)"),
    ("Asia/Bangkok",         "ICT", "Indochina (Bangkok)"),
    ("Asia/Singapore",       "SGT", "Singapore, Malaysia"),
    ("Asia/Tokyo",           "JST", "Japan (Tokyo)"),
    ("Asia/Shanghai",        "CST", "China (Beijing, Shanghai)"),
    ("Australia/Sydney",     "AEST","Sydney"),
    ("Pacific/Auckland",     "NZ",  "New Zealand (Auckland)"),
]

def _apply_timezone(zone_name: str) -> None:
    """Switch the global display timezone. Called at startup and from settings."""
    global ISTANBUL_TZ, TZ_NAME, TZ_LABEL
    label = next((lab for z, lab, _ in COMMON_TIMEZONES if z == zone_name), zone_name)
    try:
        if _HAVE_ZONEINFO:
            ISTANBUL_TZ = ZoneInfo(zone_name)
        else:
            ISTANBUL_TZ = timezone(timedelta(hours=0), name=zone_name)
        TZ_NAME = zone_name
        TZ_LABEL = label
    except Exception:
        # Bad zone name — fall back to Istanbul
        ISTANBUL_TZ = (ZoneInfo("Europe/Istanbul") if _HAVE_ZONEINFO
                       else timezone(timedelta(hours=3), name="Istanbul"))
        TZ_NAME = "Europe/Istanbul"
        TZ_LABEL = "TR"

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
from PyQt6 import QtCore, QtGui, QtPrintSupport, QtWidgets
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView
from pymavlink import DFReader

# ---------- Theme ----------
BG_0 = "#1a1f29"   # window background — cool steel dark
BG_1 = "#20262f"   # panels
BG_2 = "#262d38"   # raised
BG_3 = "#2f3742"   # hover
BORDER = "#323a47"
TEXT = "#cdd6e0"
TEXT_DIM = "#7a8699"
ACCENT = "#4a90e2"   # steel blue
ACCENT_2 = "#6aa9e8" # lighter steel blue
DANGER = "#d96666"
SUCCESS = "#5dba7c"
WARN = "#d9a14a"     # muted amber for marginal verdicts

pg.setConfigOption("background", BG_1)
pg.setConfigOption("foreground", TEXT)
# Antialias OFF — on macOS, anti-aliased software paths take ~1s for 3,500
# points which makes plotting feel like the UI is frozen. Lines still look
# fine with Qt's default rendering at typical screen sizes.
pg.setConfigOptions(antialias=False)

PLOT_COLORS = [
    "#22d3ee",  # cyan
    "#a78bfa",  # violet
    "#34d399",  # green
    WARN,  # amber
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
    font-family: "Inter", "Helvetica Neue", "Segoe UI", -apple-system, Arial, sans-serif;
    font-size: 13px;
    font-weight: 400;
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
    border-radius: 2px;
}}
QMenuBar::item:selected {{ background: {BG_2}; color: {ACCENT}; }}
QMenu {{
    background: {BG_1};
    border: 1px solid {BORDER};
    padding: 4px;
    border-radius: 2px;
}}
QMenu::item {{ padding: 6px 22px; border-radius: 2px; }}
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
    font-family: "JetBrains Mono", "SF Mono", Menlo, "Cascadia Code", Consolas, monospace;
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
    border-radius: 2px;
    padding: 6px 10px;
    selection-background-color: {ACCENT};
    selection-color: {BG_0};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
    background: {BG_2};
}}

QTreeWidget {{
    background: {BG_1};
    border: 1px solid {BORDER};
    border-radius: 2px;
    outline: 0;
    padding: 4px;
}}
QTreeWidget::item {{
    padding: 4px 6px;
    border-radius: 0;
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
    width: 12px; height: 12px;
    border: 1px solid {BORDER};
    border-radius: 1px;
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
    border-radius: 0;
    top: -1px;
    background: {BG_1};
}}
QTabBar::tab {{
    background: {BG_0};
    color: {TEXT_DIM};
    padding: 8px 18px;
    margin-right: 1px;
    border: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    border-top-left-radius: 0;
    border-top-right-radius: 0;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QTabBar::tab:hover {{
    color: {TEXT};
    background: {BG_2};
}}
QTabBar::tab:selected {{
    background: {BG_1};
    color: {ACCENT};
    border-top: 2px solid {ACCENT};
    border-left: 1px solid {BORDER};
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BG_1};
    font-weight: 700;
}}

QPlainTextEdit, QTextEdit {{
    background: {BG_1};
    border: 1px solid {BORDER};
    border-radius: 2px;
    padding: 10px;
    font-family: "JetBrains Mono", "SF Mono", Menlo, "Cascadia Code", Consolas, monospace;
    font-size: 12px;
    selection-background-color: {ACCENT};
    selection-color: {BG_0};
}}

QScrollArea {{ border: none; }}

QScrollBar:vertical {{
    background: {BG_0}; width: 10px; margin: 0;
    border-left: 1px solid {BORDER};
}}
QScrollBar::handle:vertical {{
    background: {BG_3}; min-height: 30px; border-radius: 0;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{
    background: {BG_0}; height: 10px; margin: 0;
    border-top: 1px solid {BORDER};
}}
QScrollBar::handle:horizontal {{ background: {BG_3}; min-width: 30px; border-radius: 0; }}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

QToolTip {{
    background: {BG_2};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px 10px;
    border-radius: 2px;
    font-size: 11px;
}}

QPushButton {{
    background: {BG_2};
    border: 1px solid {BORDER};
    border-radius: 2px;
    padding: 6px 14px;
    color: {TEXT};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 11px;
}}
QPushButton:hover {{
    background: {BG_3};
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton:pressed {{ background: {BG_1}; }}
QPushButton#primary {{
    background: {ACCENT};
    color: {BG_0};
    border: 1px solid {ACCENT};
    font-weight: 700;
}}
QPushButton#primary:hover {{
    background: {ACCENT_2};
    border-color: {ACCENT_2};
    color: {BG_0};
}}
QPushButton#violet {{
    background: {BG_2};
    color: {ACCENT_2};
    border: 1px solid {ACCENT_2};
    font-weight: 700;
    padding: 6px 16px;
}}
QPushButton#icon {{
    background: {BG_2};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 2px;
    padding: 6px 10px;
    font-size: 16px;
    font-weight: 400;
}}
QPushButton#icon:hover {{
    background: {BG_3};
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton#violet:hover {{
    background: {ACCENT_2};
    color: {BG_0};
}}

QFrame#statTile {{
    background: {BG_2};
    border: 1px solid {BORDER};
    border-radius: 2px;
}}
"""

INSTRUMENTS_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8" />
<title>Instruments</title>
<style>
  html,body{height:100%;margin:0;padding:0;background:#0b1220;
            font-family:"Inter","Helvetica Neue","Segoe UI",sans-serif;
            color:#e6edf7;overflow:hidden;user-select:none}
  .empty{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
         padding:18px 24px;background:#111a2e;border:1px solid #243154;
         color:#8b97b3;border-radius:8px;text-align:center}
  #wrap{height:100vh;display:flex;flex-direction:column;padding:14px;gap:12px;box-sizing:border-box}
  .row{display:grid;gap:14px;min-height:0}
  #row-instruments{grid-template-columns:repeat(4,1fr);flex:1 1 280px}
  #row-sticks{flex:0 0 220px}
  #ctrl{flex:0 0 auto}
  .panel{background:
           radial-gradient(circle at 50% 0%, rgba(34,211,238,0.06) 0%, rgba(0,0,0,0) 60%),
           linear-gradient(180deg,#1a2740 0%,#0e172a 100%);
         border:1px solid #2a3a5a; border-radius:14px;
         padding:14px 14px 12px; display:flex; flex-direction:column;
         align-items:center; min-height:0;
         box-shadow: 0 8px 24px rgba(0,0,0,0.45),
                     inset 0 1px 0 rgba(255,255,255,0.05),
                     inset 0 0 0 1px rgba(34,211,238,0.05)}
  .panel h3{margin:0 0 10px; color:#8b97b3; font-size:10px; letter-spacing:3px;
            font-weight:800; text-align:center;
            padding-bottom:6px; width:100%;
            border-bottom: 1px solid rgba(34,211,238,0.18)}
  .panel svg{flex:1;min-height:0;width:100%}
  .readout{margin-top:10px; padding:6px 12px;
           background:rgba(11,18,32,0.7); border:1px solid rgba(34,211,238,0.2);
           border-radius:6px;
           font-family:"JetBrains Mono","SF Mono",Menlo,monospace;
           color:#22d3ee; font-size:13px; font-weight:700; letter-spacing:1.2px;
           text-align:center; white-space:nowrap;
           text-shadow:0 0 8px rgba(34,211,238,0.4)}
  .readout .dim{color:#5b7196; font-weight:600; letter-spacing:1.5px; font-size:10px;
                text-shadow:none}

  /* Radio transmitter — brushed-metal style housing with two gimbals */
  .rc-housing{
    background:
      radial-gradient(ellipse at 30% 0%, rgba(34,211,238,0.10) 0%, rgba(0,0,0,0) 60%),
      linear-gradient(180deg,#1f2a40 0%,#0e1626 100%);
    border:1px solid #2a3a5a; border-radius:18px;
    box-shadow:
      0 10px 30px rgba(0,0,0,0.55),
      inset 0 1px 0 rgba(255,255,255,0.08),
      inset 0 0 0 1px rgba(34,211,238,0.08);
    padding:14px 26px 18px;
    display:grid;grid-template-columns:1fr auto 1fr;gap:18px;align-items:center;
    position:relative;min-height:0
  }
  .rc-housing::before{
    content:'';position:absolute;top:0;left:24px;right:24px;height:1px;
    background:linear-gradient(90deg, transparent 0%, rgba(34,211,238,0.45) 50%, transparent 100%)
  }
  .gimbal-wrap{display:flex;flex-direction:column;align-items:center;gap:8px;min-height:0}
  .gimbal-wrap svg{flex:1;min-height:0;width:100%;max-width:220px}
  .gimbal-label{font-size:9px;letter-spacing:3px;font-weight:800;color:#5b7196;
                text-align:center;text-transform:uppercase;margin-top:2px}
  .gimbal-readout{font-family:"JetBrains Mono","SF Mono",Menlo,monospace;color:#22d3ee;
                  font-size:11px;font-weight:700;letter-spacing:0.5px;text-align:center;
                  white-space:nowrap;text-shadow:0 0 6px rgba(34,211,238,0.35)}
  .gimbal-readout .dim{color:#5b7196;text-shadow:none;font-weight:600}
  /* Center spine between the two gimbals — looks like a real transmitter */
  .rc-center{display:flex;flex-direction:column;align-items:center;gap:14px;
             padding:0 8px;color:#5b7196;font-size:9px;letter-spacing:2px;
             font-weight:800;text-align:center;font-family:"Inter",sans-serif}
  .rc-led{width:8px;height:8px;border-radius:50%;background:#22d3ee;
          box-shadow:0 0 10px #22d3ee, 0 0 20px rgba(34,211,238,0.5)}

  /* Control bar — always visible at bottom */
  #ctrl{display:flex;align-items:center;gap:14px;padding:12px 18px;
        background:#111a2e;border:1px solid #243154;border-radius:12px;
        flex-shrink:0;flex-wrap:wrap}
  .btn{background:#22d3ee;color:#0b1220;font-weight:800;letter-spacing:1.5px;
       font-size:11px;padding:9px 18px;border-radius:6px;cursor:pointer;
       border:1px solid #22d3ee;font-family:inherit;transition:all 0.15s;
       box-shadow:0 0 12px rgba(34,211,238,0.35)}
  .btn:hover{background:#67e8f9;border-color:#67e8f9;box-shadow:0 0 18px rgba(34,211,238,0.55)}
  .btn.alt{background:#16223c;color:#e6edf7;border-color:#243154;box-shadow:none}
  .btn.alt:hover{background:#1d2c4d;border-color:#22d3ee;color:#22d3ee;box-shadow:0 0 12px rgba(34,211,238,0.25)}
  .speed-group{display:flex;gap:4px;padding:3px;background:#0b1220;
               border:1px solid #243154;border-radius:6px}
  .speed-btn{background:transparent;color:#8b97b3;font-size:10px;font-weight:700;
             letter-spacing:1px;padding:6px 10px;border:none;border-radius:4px;
             cursor:pointer;font-family:"JetBrains Mono","SF Mono",Menlo,monospace;
             transition:all 0.15s}
  .speed-btn:hover{color:#22d3ee;background:#16223c}
  .speed-btn.active{background:#22d3ee;color:#0b1220}
  #scrub{flex:1;-webkit-appearance:none;height:6px;background:#243154;
         border-radius:3px;outline:none;cursor:pointer}
  #scrub::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;
         background:#22d3ee;border-radius:50%;border:2px solid #0b1220;cursor:pointer;
         box-shadow:0 0 10px rgba(34,211,238,0.7)}
  #time-readout{font-family:"JetBrains Mono","SF Mono",Menlo,monospace;
         color:#22d3ee;font-size:14px;font-weight:700;letter-spacing:1px;min-width:160px;text-align:right}
  .ai-bg{fill:#06101e}
  .ai-sky{fill:#1e3a8a}        /* deeper sky */
  .ai-ground{fill:#7c2d12}     /* richer brown */
  .ai-horizon{stroke:#ffffff;stroke-width:2}
  .ai-pitch-tick{stroke:#ffffff;stroke-width:1.1;stroke-linecap:round;opacity:0.95}
  .ai-pitch-label{fill:#ffffff;font-size:7px;font-family:"JetBrains Mono",monospace;font-weight:700}
  .ai-frame{fill:none;stroke:#2a3a5a;stroke-width:2.5}
  .ai-aircraft{fill:none;stroke:#d9a14a;stroke-width:3;stroke-linecap:round}
  .ai-roll-tick{stroke:#ffffff;stroke-width:1.2}
  .ai-roll-pointer{fill:#d9a14a}
  .hsi-card{fill:#06101e;stroke:#2a3a5a;stroke-width:2}
  .hsi-tick{stroke:#e6edf7;stroke-width:1.2;stroke-linecap:round}
  .hsi-cardinal{fill:#22d3ee;font-size:15px;font-weight:900;font-family:"Inter",sans-serif;text-anchor:middle}
  .hsi-deg{fill:#8b97b3;font-size:8px;font-family:"JetBrains Mono",monospace;text-anchor:middle}
  .hsi-aircraft{fill:#d9a14a;stroke:#06101e;stroke-width:1}
  .tape-bg{fill:#06101e;stroke:#2a3a5a;stroke-width:1.5}
  .tape-tick{stroke:#5b7196;stroke-width:1}
  .tape-tick-major{stroke:#e6edf7;stroke-width:1.5}
  .tape-label{fill:#8b97b3;font-size:9px;font-family:"JetBrains Mono",monospace;font-weight:600}
  .tape-marker{fill:#22d3ee}
  .tape-current{fill:#22d3ee;font-size:14px;font-weight:800;font-family:"JetBrains Mono",monospace;text-anchor:middle}
  .stick-frame{fill:#06101e;stroke:#2a3a5a;stroke-width:1.5}
  .stick-cross{stroke:#2a3a5a;stroke-width:1}
  .stick-dot{fill:#22d3ee;stroke:#06101e;stroke-width:2}
  .stick-axis{fill:#8b97b3;font-size:8px;font-family:"JetBrains Mono",monospace;font-weight:600;letter-spacing:1.5px}
</style>
</head><body>
<script>
const D = __DATA__;
if (!D) {
  document.body.innerHTML = '<div class="empty">'
    + '<div style="font-size:14px;color:#e6edf7;margin-bottom:4px">No instrument data</div>'
    + '<div style="font-size:12px">This log is missing ATT or RCIN messages.</div></div>';
} else {
  document.body.innerHTML = `
  <div id="wrap">
    <div class="row" id="row-instruments">
      <div class="panel">
        <h3>ATTITUDE</h3>
        <svg viewBox="-100 -100 200 200" preserveAspectRatio="xMidYMid meet">
          <defs><clipPath id="ai-clip"><circle cx="0" cy="0" r="80"/></clipPath></defs>
          <circle class="ai-bg" cx="0" cy="0" r="92"/>
          <g clip-path="url(#ai-clip)">
            <g id="ai-roll-group">
              <g id="ai-pitch-group">
                <rect class="ai-sky" x="-200" y="-200" width="400" height="200"/>
                <rect class="ai-ground" x="-200" y="0" width="400" height="200"/>
                <line class="ai-horizon" x1="-200" y1="0" x2="200" y2="0"/>
                <g id="ai-pitch-ladder"></g>
              </g>
            </g>
          </g>
          <circle class="ai-frame" cx="0" cy="0" r="80"/>
          <!-- aircraft symbol -->
          <g class="ai-aircraft">
            <line x1="-30" y1="0" x2="-10" y2="0"/>
            <line x1="30" y1="0" x2="10" y2="0"/>
            <circle cx="0" cy="0" r="2.5" fill=WARN/>
            <line x1="0" y1="-12" x2="0" y2="-4"/>
          </g>
          <!-- roll scale ticks -->
          <g id="ai-roll-scale"></g>
          <!-- roll pointer (fixed at top) -->
          <polygon class="ai-roll-pointer" points="0,-80 -5,-72 5,-72"/>
        </svg>
        <div class="readout">
          <span class="dim">ROLL</span> <span id="ai-roll-val">0°</span>
          &nbsp;·&nbsp;
          <span class="dim">PITCH</span> <span id="ai-pitch-val">0°</span>
        </div>
      </div>

      <div class="panel">
        <h3>HEADING</h3>
        <svg viewBox="-100 -100 200 200" preserveAspectRatio="xMidYMid meet">
          <circle class="hsi-card" cx="0" cy="0" r="88"/>
          <g id="hsi-rose"></g>
          <!-- aircraft symbol pointing up (fixed) -->
          <polygon class="hsi-aircraft" points="0,-58 -8,-44 -2,-44 -2,-30 -14,-30 -14,-24 -2,-24 -2,8 -10,14 -10,18 0,15 10,18 10,14 2,8 2,-24 14,-24 14,-30 2,-30 2,-44 8,-44"/>
          <!-- top pointer (fixed) -->
          <polygon fill=WARN points="0,-90 -5,-78 5,-78"/>
        </svg>
        <div class="readout">
          <span class="dim">HDG</span> <span id="hsi-hdg-val">000°</span>
        </div>
      </div>

      <div class="panel">
        <h3>ALTITUDE</h3>
        <svg viewBox="-30 -100 60 200" preserveAspectRatio="xMidYMid meet">
          <rect class="tape-bg" x="-25" y="-90" width="50" height="180" rx="4"/>
          <g id="alt-tape"></g>
          <!-- current value box -->
          <rect x="-26" y="-12" width="52" height="24" fill="#16223c" stroke="#22d3ee" stroke-width="1.5"/>
          <text id="alt-tape-current" class="tape-current" x="0" y="4">0</text>
          <!-- center reticle -->
          <polygon fill="#22d3ee" points="-26,-12 -26,12 -32,0"/>
        </svg>
        <div class="readout">
          <span class="dim">ALT</span> <span id="alt-val">0.0 m</span>
        </div>
      </div>

      <div class="panel">
        <h3>GROUND SPEED</h3>
        <svg viewBox="-30 -100 60 200" preserveAspectRatio="xMidYMid meet">
          <rect class="tape-bg" x="-25" y="-90" width="50" height="180" rx="4"/>
          <g id="spd-tape"></g>
          <rect x="-26" y="-12" width="52" height="24" fill="#16223c" stroke="#22d3ee" stroke-width="1.5"/>
          <text id="spd-tape-current" class="tape-current" x="0" y="4">0</text>
          <polygon fill="#22d3ee" points="-26,-12 -26,12 -32,0"/>
        </svg>
        <div class="readout">
          <span class="dim">SPD</span> <span id="spd-val">0.0 m/s</span>
        </div>
      </div>
    </div>

    <div class="row" id="row-sticks">
      <div class="rc-housing">
        <div class="gimbal-wrap">
          <svg viewBox="-110 -110 220 220" preserveAspectRatio="xMidYMid meet">
            <defs>
              <radialGradient id="gimbal-grad" cx="0.5" cy="0.4" r="0.7">
                <stop offset="0%" stop-color="#1a2b3f"/>
                <stop offset="100%" stop-color="#0a131f"/>
              </radialGradient>
            </defs>
            <circle cx="0" cy="0" r="100" fill="#0a131f" stroke="#0b1a26" stroke-width="3"/>
            <circle cx="0" cy="0" r="92" fill="url(#gimbal-grad)" stroke="#0d2030" stroke-width="1"/>
            <line x1="-78" y1="0" x2="78" y2="0" stroke="#3a4a60" stroke-width="1.5"/>
            <line x1="0" y1="-78" x2="0" y2="78" stroke="#3a4a60" stroke-width="1.5"/>
            <defs>
              <radialGradient id="ball-grad" cx="0.35" cy="0.30" r="0.7">
                <stop offset="0%" stop-color="#dfe6f0"/>
                <stop offset="55%" stop-color="#9aa9bc"/>
                <stop offset="100%" stop-color="#4c5a70"/>
              </radialGradient>
            </defs>
            <circle id="stick-l-dot" cx="0" cy="0" r="15"
                    fill="url(#ball-grad)" stroke="#1a2433" stroke-width="1.5"/>
          </svg>
          <div class="gimbal-label">THROTTLE · YAW</div>
          <div class="gimbal-readout">
            <span class="dim">THR</span> <span id="stick-l-thr">1500</span> &nbsp;·&nbsp; <span class="dim">YAW</span> <span id="stick-l-yaw">1500</span>
          </div>
        </div>
        <div class="rc-center">
          <div class="rc-led"></div>
          <div>RC<br>INPUT</div>
        </div>
        <div class="gimbal-wrap">
          <svg viewBox="-110 -110 220 220" preserveAspectRatio="xMidYMid meet">
            <circle cx="0" cy="0" r="100" fill="#0a131f" stroke="#0b1a26" stroke-width="3"/>
            <circle cx="0" cy="0" r="92" fill="url(#gimbal-grad)" stroke="#0d2030" stroke-width="1"/>
            <line x1="-78" y1="0" x2="78" y2="0" stroke="#3a4a60" stroke-width="1.5"/>
            <line x1="0" y1="-78" x2="0" y2="78" stroke="#3a4a60" stroke-width="1.5"/>
            <circle id="stick-r-dot" cx="0" cy="0" r="15"
                    fill="url(#ball-grad)" stroke="#1a2433" stroke-width="1.5"/>
          </svg>
          <div class="gimbal-label">PITCH · ROLL</div>
          <div class="gimbal-readout">
            <span class="dim">PIT</span> <span id="stick-r-pit">1500</span> &nbsp;·&nbsp; <span class="dim">ROLL</span> <span id="stick-r-rol">1500</span>
          </div>
        </div>
      </div>
    </div>

    <div id="ctrl">
      <button class="btn" id="btn-play">▶ PLAY</button>
      <button class="btn alt" id="btn-pause">❚❚ PAUSE</button>
      <button class="btn alt" id="btn-reset">⏮ RESET</button>
      <div class="speed-group">
        <button class="speed-btn" data-speed="0.5">0.5×</button>
        <button class="speed-btn active" data-speed="1">1×</button>
        <button class="speed-btn" data-speed="2">2×</button>
        <button class="speed-btn" data-speed="4">4×</button>
        <button class="speed-btn" data-speed="8">8×</button>
      </div>
      <input type="range" id="scrub" min="0" max="${D.n-1}" value="0">
      <div id="time-readout"><span id="t-time">--:--:--</span> <span style="color:#8b97b3">·</span> <span id="t-rel">T+0.0s</span></div>
    </div>
  </div>`;

  // Build pitch ladder
  const ladder = document.getElementById('ai-pitch-ladder');
  for (let p = -90; p <= 90; p += 10) {
    if (p === 0) continue;
    const y = p * 4;  // 4 px per degree (matches translate factor below)
    const w = (Math.abs(p) % 30 === 0) ? 30 : 16;
    ladder.innerHTML += `<line class="ai-pitch-tick" x1="-${w}" y1="${y}" x2="${w}" y2="${y}"/>`;
    if (Math.abs(p) % 30 === 0) {
      ladder.innerHTML += `<text class="ai-pitch-label" x="-${w+4}" y="${y+2}" text-anchor="end">${Math.abs(p)}</text>`;
      ladder.innerHTML += `<text class="ai-pitch-label" x="${w+4}" y="${y+2}" text-anchor="start">${Math.abs(p)}</text>`;
    }
  }
  // Roll scale ticks at top (every 30°)
  const rollScale = document.getElementById('ai-roll-scale');
  for (let r = -60; r <= 60; r += 10) {
    const rad = (r - 90) * Math.PI / 180;
    const r1 = 80, r2 = (r % 30 === 0) ? 70 : 75;
    const x1 = r1 * Math.cos(rad), y1 = r1 * Math.sin(rad);
    const x2 = r2 * Math.cos(rad), y2 = r2 * Math.sin(rad);
    rollScale.innerHTML += `<line class="ai-roll-tick" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
  }

  // Build compass rose (heading)
  const rose = document.getElementById('hsi-rose');
  const CARDINALS = {0:'N',90:'E',180:'S',270:'W'};
  for (let h = 0; h < 360; h += 10) {
    const rad = (h - 90) * Math.PI / 180;
    const r1 = 80, r2 = (h % 30 === 0) ? 68 : 74;
    const x1 = r1 * Math.cos(rad), y1 = r1 * Math.sin(rad);
    const x2 = r2 * Math.cos(rad), y2 = r2 * Math.sin(rad);
    rose.innerHTML += `<line class="hsi-tick" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
    if (h in CARDINALS) {
      const lx = 56 * Math.cos(rad), ly = 56 * Math.sin(rad);
      rose.innerHTML += `<text class="hsi-cardinal" x="${lx}" y="${ly+5}">${CARDINALS[h]}</text>`;
    } else if (h % 30 === 0) {
      const lx = 58 * Math.cos(rad), ly = 58 * Math.sin(rad);
      rose.innerHTML += `<text class="hsi-deg" x="${lx}" y="${ly+3}">${h/10}</text>`;
    }
  }

  // Build altitude tape (initial state — actual marks rendered each frame)
  function buildTape(g, span, step) {
    const out = [];
    for (let k = -span; k <= span; k += step) {
      const y = -k * (180 / (2 * span));  // map [-span, +span] → [+90, -90] (top = +span)
      const major = (k % (step*5) === 0);
      const w = major ? 12 : 6;
      out.push(`<line class="${major?'tape-tick-major':'tape-tick'}" x1="-25" y1="${y}" x2="${-25+w}" y2="${y}"/>`);
      if (major) out.push(`<text class="tape-label" x="${-25+w+3}" y="${y+3}">${k}</text>`);
    }
    g.innerHTML = out.join('');
  }
  buildTape(document.getElementById('alt-tape'), 50, 5);
  buildTape(document.getElementById('spd-tape'), 20, 2);

  // ---------- Animation ----------
  let framePos = 0;       // fractional frame position (e.g. 12.37)
  let playing = false;
  let speed = 1.0;
  let lastTime = 0;
  // Real-time: at 1×, 1 wall-clock second of playback advances
  // exactly the frames covered in the same real-time slice.
  const flightDurationSec = Math.max(0.001, (D.trel[D.n - 1] - D.trel[0]));
  const BASE_FPS = D.n / flightDurationSec;

  function lerp(a, b, t) { return a + (b - a) * t; }
  function lerpAngle(a, b, t) {
    let d = (b - a) % 360;
    if (d > 180) d -= 360;
    if (d < -180) d += 360;
    return ((a + d * t) % 360 + 360) % 360;
  }

  function update(fp) {
    framePos = Math.max(0, Math.min(D.n-1, fp));
    const lo = Math.floor(framePos);
    const hi = Math.min(D.n-1, lo + 1);
    const f = framePos - lo;
    const r = lerp(D.roll[lo],  D.roll[hi],  f);
    const p = lerp(D.pitch[lo], D.pitch[hi], f);
    const y = lerpAngle(D.yaw[lo], D.yaw[hi], f);
    const a = lerp(D.alt[lo],   D.alt[hi],   f);
    const s = lerp(D.spd[lo],   D.spd[hi],   f);
    const c1 = lerp(D.c1[lo], D.c1[hi], f);
    const c2 = lerp(D.c2[lo], D.c2[hi], f);
    const c3 = lerp(D.c3[lo], D.c3[hi], f);
    const c4 = lerp(D.c4[lo], D.c4[hi], f);
    const trel = lerp(D.trel[lo], D.trel[hi], f);
    const tstr = D.tstr[lo] || '--:--:--';
    const frame = lo;  // for raw value displays

    // Attitude indicator
    document.getElementById('ai-roll-group').setAttribute('transform', `rotate(${-r})`);
    document.getElementById('ai-pitch-group').setAttribute('transform', `translate(0, ${p*4})`);
    document.getElementById('ai-roll-val').textContent  = (r>=0?'+':'') + r.toFixed(1) + '°';
    document.getElementById('ai-pitch-val').textContent = (p>=0?'+':'') + p.toFixed(1) + '°';

    // Heading
    const hdg = ((y % 360) + 360) % 360;
    document.getElementById('hsi-rose').setAttribute('transform', `rotate(${-hdg})`);
    document.getElementById('hsi-hdg-val').textContent = String(Math.round(hdg)).padStart(3,'0') + '°';

    // Altitude tape — shift the tape so current altitude lines up with center
    const altSpan = 50;
    const altShift = a * (180 / (2 * altSpan));
    document.getElementById('alt-tape').setAttribute('transform', `translate(0, ${altShift})`);
    document.getElementById('alt-tape-current').textContent = a.toFixed(0);
    document.getElementById('alt-val').textContent = a.toFixed(1) + ' m';

    // Speed tape
    const spdSpan = 20;
    const spdShift = s * (180 / (2 * spdSpan));
    document.getElementById('spd-tape').setAttribute('transform', `translate(0, ${spdShift})`);
    document.getElementById('spd-tape-current').textContent = s.toFixed(0);
    document.getElementById('spd-val').textContent = s.toFixed(1) + ' m/s';

    // Sticks: PWM 1000-2000 → -1..+1, mapped inside gimbal (r=92, travel=75)
    function norm(c) { return (c - 1500) / 500; }
    const TRAVEL = 75;
    const lx = norm(c4) * TRAVEL;   // yaw → x
    const ly = -norm(c3) * TRAVEL;  // throttle → -y (up = high)
    const rx = norm(c1) * TRAVEL;   // roll → x
    const ry = -norm(c2) * TRAVEL;  // pitch → -y
    document.getElementById('stick-l-dot').setAttribute('cx', lx);
    document.getElementById('stick-l-dot').setAttribute('cy', ly);
    document.getElementById('stick-r-dot').setAttribute('cx', rx);
    document.getElementById('stick-r-dot').setAttribute('cy', ry);
    document.getElementById('stick-l-thr').textContent = Math.round(c3);
    document.getElementById('stick-l-yaw').textContent = Math.round(c4);
    document.getElementById('stick-r-pit').textContent = Math.round(c2);
    document.getElementById('stick-r-rol').textContent = Math.round(c1);

    // Time readout
    document.getElementById('t-time').textContent = tstr + ' __TZLABEL__';
    document.getElementById('t-rel').textContent  = 'T+' + trel.toFixed(1) + 's';

    // Sync scrub bar
    document.getElementById('scrub').value = Math.round(framePos);
  }

  function loop(t) {
    if (!playing) return;
    if (lastTime === 0) { lastTime = t; requestAnimationFrame(loop); return; }
    const dt = (t - lastTime) / 1000;
    lastTime = t;
    let next = framePos + dt * BASE_FPS * speed;
    if (next >= D.n - 1) {
      playing = false;
      update(D.n - 1);
      return;
    }
    update(next);
    requestAnimationFrame(loop);
  }

  document.getElementById('btn-play').addEventListener('click', () => {
    if (playing) return;
    if (framePos >= D.n - 1) framePos = 0;
    playing = true; lastTime = 0;
    requestAnimationFrame(loop);
  });
  document.getElementById('btn-pause').addEventListener('click', () => { playing = false; });
  document.getElementById('btn-reset').addEventListener('click', () => {
    playing = false; update(0);
  });
  document.getElementById('scrub').addEventListener('input', (e) => {
    playing = false;
    update(parseInt(e.target.value, 10));
  });
  document.querySelectorAll('.speed-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      speed = parseFloat(btn.dataset.speed);
      document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    });
  });

  // External bridge: master timeline can drive this view via window.setPos(t_sec)
  window.setPos = function(t_sec) {
    if (!D || !D.trel || D.n < 2) return;
    playing = false;
    if (t_sec <= D.trel[0]) { update(0); return; }
    if (t_sec >= D.trel[D.n-1]) { update(D.n-1); return; }
    let lo = 0;
    for (let i = 1; i < D.n; i++) {
      if (D.trel[i] >= t_sec) { lo = i - 1; break; }
    }
    const span = D.trel[lo+1] - D.trel[lo];
    const f = span > 0 ? (t_sec - D.trel[lo]) / span : 0;
    update(lo + f);
  };

  update(0);
}
</script>
</body></html>
"""

PLOT3D_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8" />
<title>3D Track</title>
<style>
  html,body{height:100%;margin:0;padding:0;background:#0b1220;
            font-family:"Inter","Helvetica Neue","Segoe UI",sans-serif;color:#e6edf7;overflow:hidden}
  #app{height:100vh;display:flex;flex-direction:column}
  #plot{flex:1;min-height:0;width:100%}
  #ctrl3d{display:flex;align-items:center;gap:14px;padding:10px 14px;
          background:#111a2e;border-top:1px solid #243154;flex-shrink:0}
  #ctrl3d .btn{background:#22d3ee;color:#0b1220;font-weight:800;letter-spacing:1.5px;
       font-size:11px;padding:8px 16px;border-radius:6px;cursor:pointer;
       border:1px solid #22d3ee;font-family:inherit;transition:all 0.15s;
       box-shadow:0 0 12px rgba(34,211,238,0.35)}
  #ctrl3d .btn:hover{background:#67e8f9;border-color:#67e8f9}
  #ctrl3d .btn.alt{background:#16223c;color:#e6edf7;border-color:#243154;box-shadow:none}
  #ctrl3d .btn.alt:hover{background:#1d2c4d;border-color:#22d3ee;color:#22d3ee}
  #ctrl3d .speed-group{display:flex;gap:4px;padding:3px;background:#0b1220;
               border:1px solid #243154;border-radius:6px}
  #ctrl3d .speed-btn{background:transparent;color:#8b97b3;font-size:10px;font-weight:700;
             letter-spacing:1px;padding:6px 10px;border:none;border-radius:4px;
             cursor:pointer;font-family:"JetBrains Mono","SF Mono",Menlo,monospace}
  #ctrl3d .speed-btn:hover{color:#22d3ee;background:#16223c}
  #ctrl3d .speed-btn.active{background:#22d3ee;color:#0b1220}
  #ctrl3d #scrub3d{flex:1;-webkit-appearance:none;height:6px;background:#243154;
         border-radius:3px;outline:none;cursor:pointer}
  #ctrl3d #scrub3d::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;
         background:#22d3ee;border-radius:50%;border:2px solid #0b1220;cursor:pointer;
         box-shadow:0 0 10px rgba(34,211,238,0.7)}
  #t3d{font-family:"JetBrains Mono","SF Mono",Menlo,monospace;
         color:#22d3ee;font-size:13px;font-weight:700;letter-spacing:1px;min-width:200px;text-align:right}
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
<div id="app">
  <div style="position:relative;flex:1;min-height:0">
    <div id="hud" class="hud" style="display:none">
      <span>◈ TELEMETRY</span>
      <span class="v" id="hud-time">time —</span>
      <span class="v" id="hud-elapsed">T+ —s</span>
      <span class="v" id="hud-alt">alt — m</span>
      <span class="v" id="hud-d">dist — m</span>
      <span class="v" id="hud-i">frame —/—</span>
    </div>
    <div id="plot" style="width:100%;height:100%"></div>
  </div>
  <div id="ctrl3d">
    <button class="btn" id="btn-play3d">▶ PLAY</button>
    <button class="btn alt" id="btn-pause3d">❚❚ PAUSE</button>
    <button class="btn alt" id="btn-reset3d">⏮ RESET</button>
    <div class="speed-group">
      <button class="speed-btn" data-speed="0.5">0.5×</button>
      <button class="speed-btn active" data-speed="1">1×</button>
      <button class="speed-btn" data-speed="2">2×</button>
      <button class="speed-btn" data-speed="4">4×</button>
      <button class="speed-btn" data-speed="8">8×</button>
    </div>
    <input type="range" id="scrub3d" min="0" max="0" value="0" step="0.01">
    <div id="t3d"><span id="t3d-time">--:--:--</span> <span style="color:#8b97b3">·</span> <span id="t3d-rel">T+0.0s</span></div>
  </div>
</div>
<script>
const PTS = __PTS__;
if (!PTS || PTS.x.length < 2) {
  document.body.innerHTML = '<div class="empty">'
    + '<div style="font-size:14px;color:#e6edf7;margin-bottom:4px">No 3D track</div>'
    + '<div style="font-size:12px">Need at least 2 GPS/POS points with a 3D fix.</div></div>';
} else {
  const X = PTS.x, Y = PTS.y, Z = PTS.z;
  const TSTR = PTS.tstr || [];
  const TREL = PTS.trel || [];
  const N = X.length;
  const FRAMES = Math.min(400, N);
  const STEP = Math.max(1, Math.floor(N / FRAMES));
  const idxs = [];
  for (let i = 0; i < N; i += STEP) idxs.push(i);
  if (idxs[idxs.length-1] !== N - 1) idxs.push(N - 1);

  const cumD = new Array(N).fill(0);
  for (let i = 1; i < N; i++) {
    const dx=X[i]-X[i-1], dy=Y[i]-Y[i-1], dz=Z[i]-Z[i-1];
    cumD[i] = cumD[i-1] + Math.sqrt(dx*dx+dy*dy+dz*dz);
  }

  function dir(i) {
    // Look ahead a few samples for a stable direction estimate
    const win = Math.max(1, Math.floor(N / 80));
    const j = Math.min(i + win, N - 1);
    const k = Math.max(i - win, 0);
    let u = X[j]-X[k], v = Y[j]-Y[k], w = Z[j]-Z[k];
    const m = Math.sqrt(u*u+v*v+w*w);
    if (m < 1e-6) return [0, 1, 0];  // default: nose forward (+y)
    return [u/m, v/m, w/m];
  }

  const xExtent = Math.max(...X) - Math.min(...X);
  const yExtent = Math.max(...Y) - Math.min(...Y);
  const zExtent = Math.max(...Z) - Math.min(...Z);
  const S = Math.max(0.8, Math.max(xExtent, yExtent, zExtent) * 0.04);

  // ---- Aircraft mesh — user-supplied (airplane_mesh.json) or procedural fallback ----
  const MESH = __MESH__;
  let BODY, FACE_I, FACE_J, FACE_K, VERT_COLORS;
  if (MESH && MESH.verts && MESH.verts.length > 0) {
    BODY = MESH.verts;          // body-frame coords, longest dim ~2.0
    FACE_I = MESH.faces.map(f => f[0]);
    FACE_J = MESH.faces.map(f => f[1]);
    FACE_K = MESH.faces.map(f => f[2]);
    VERT_COLORS = MESH.vcolors || [];
  } else {
    BODY = [
      [ 0.9,  0.9,  0.0 ], [-0.9,  0.9,  0.0 ],
      [ 0.9, -0.9,  0.0 ], [-0.9, -0.9,  0.0 ],
      [ 0.0,  0.0,  0.35], [ 0.0,  0.0, -0.35],
      [ 0.0,  1.1,  0.10],
    ];
    FACE_I = [4,4,4,4,4,5,5,5,5,5];
    FACE_J = [0,6,1,3,2,6,1,3,2,0];
    FACE_K = [6,1,3,2,0,0,6,1,3,2];
    VERT_COLORS = ['#22d3ee','#22d3ee','#a78bfa','#a78bfa','#22d3ee','#a78bfa','#d9a14a'];
  }

  function rotatedAircraftVerts(i) {
    const fwd = dir(i);
    const upx=0, upy=0, upz=1;
    // right = fwd × up
    let rx = fwd[1]*upz - fwd[2]*upy;
    let ry = fwd[2]*upx - fwd[0]*upz;
    let rz = fwd[0]*upy - fwd[1]*upx;
    let rm = Math.hypot(rx, ry, rz);
    if (rm < 1e-6) { rx=1; ry=0; rz=0; rm=1; }
    rx/=rm; ry/=rm; rz/=rm;
    // up' = right × fwd
    const u2x = ry*fwd[2] - rz*fwd[1];
    const u2y = rz*fwd[0] - rx*fwd[2];
    const u2z = rx*fwd[1] - ry*fwd[0];
    const cx = X[i], cy = Y[i], cz = Z[i];
    const N = BODY.length;
    const xs = new Array(N), ys = new Array(N), zs = new Array(N);
    for (let k = 0; k < N; k++) {
      const v = BODY[k];
      // Negate body-Y so the nose (was at -Y in the imported model) points forward.
      const sx = v[0]*S, sy = -v[1]*S, sz = v[2]*S;
      xs[k] = sx*rx + sy*fwd[0] + sz*u2x + cx;
      ys[k] = sx*ry + sy*fwd[1] + sz*u2y + cy;
      zs[k] = sx*rz + sy*fwd[2] + sz*u2z + cz;
    }
    return { x: xs, y: ys, z: zs };
  }

  // ---- Distance markers along the route ----
  // Adaptive spacing: ~6-10 markers depending on total distance flown
  const totalDist = cumD[N-1] || 0;
  let markerStep = 50;
  if (totalDist >  500) markerStep = 100;
  if (totalDist > 2000) markerStep = 250;
  if (totalDist > 5000) markerStep = 500;
  if (totalDist <  20) markerStep = 2;  // very short flight
  else if (totalDist < 50) markerStep = 5;
  else if (totalDist < 150) markerStep = 20;
  const markerX = [], markerY = [], markerZ = [], markerLabels = [];
  let nextMark = markerStep;
  for (let i = 1; i < N; i++) {
    if (cumD[i] >= nextMark) {
      markerX.push(X[i]); markerY.push(Y[i]); markerZ.push(Z[i]);
      markerLabels.push(nextMark + ' m');
      nextMark += markerStep;
    }
  }

  // ---- Traces ----
  const fullRoute = {
    type:'scatter3d', mode:'lines',
    x:X, y:Y, z:Z,
    line:{ width:2, color:'rgba(167,139,250,0.30)' },
    name:'route', hoverinfo:'skip', showlegend:true
  };
  const distMarkers = {
    type:'scatter3d', mode:'markers+text',
    x: markerX, y: markerY, z: markerZ,
    text: markerLabels,
    textposition: 'top center',
    textfont: { color:'#8b97b3', size:10,
                family:'"JetBrains Mono","SF Mono",Menlo,monospace' },
    marker: { size:4, color:'#a78bfa', symbol:'diamond',
              line:{color:'#0b1220', width:1} },
    name: 'distance',
    hoverinfo: 'text'
  };
  const flownTrail = {
    type:'scatter3d', mode:'lines',
    x:[X[0]], y:[Y[0]], z:[Z[0]],
    line:{ width:6, color:'#22d3ee' },
    name:'flown', hoverinfo:'skip'
  };
  const initVerts = rotatedAircraftVerts(0);
  const aircraft = {
    type:'mesh3d',
    x: initVerts.x, y: initVerts.y, z: initVerts.z,
    i: FACE_I, j: FACE_J, k: FACE_K,
    vertexcolor: VERT_COLORS,
    flatshading: false,
    lighting: { ambient:0.55, diffuse:0.7, specular:0.4, roughness:0.4 },
    lightposition: { x:1000, y:1000, z:2000 },
    name:'aircraft',
    hovertemplate:'AIRCRAFT<br>x: %{x:.1f} m<br>y: %{y:.1f} m<br>alt: %{z:.1f} m<extra></extra>'
  };
  const startMarker = {
    type:'scatter3d', mode:'markers',
    x:[X[0]], y:[Y[0]], z:[Z[0]],
    marker:{ size:7, color:'#34d399', line:{color:'#0b1220',width:2} },
    name:'start', hovertemplate:'START<extra></extra>'
  };
  const endMarker = {
    type:'scatter3d', mode:'markers',
    x:[X[N-1]], y:[Y[N-1]], z:[Z[N-1]],
    marker:{ size:7, color:'#f87171', line:{color:'#0b1220',width:2} },
    name:'end', hovertemplate:'END<extra></extra>'
  };

  // Real-time playback: at 1×, one wall-clock second advances the same
  // sample range covered by one real second of flight.
  const flightDurationSec = Math.max(0.001, TREL[N-1] - TREL[0]);
  const BASE_INDEX_PER_SEC = N / flightDurationSec;  // 1× = real time

  function lerp(a, b, t) { return a + (b - a) * t; }

  const layout = {
    paper_bgcolor:'#0b1220',
    plot_bgcolor:'#0b1220',
    font:{ color:'#e6edf7', family:'"Inter","Helvetica Neue","Segoe UI",sans-serif' },
    margin:{ l:0, r:0, t:0, b:0 },
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
  };
  const config = { displayModeBar:true, displaylogo:false, responsive:true,
                   modeBarButtonsToRemove:['toImage'] };

  document.getElementById('hud').style.display = 'block';
  function updateHud(fp) {
    const lo = Math.floor(fp);
    const hi = Math.min(N-1, lo + 1);
    const f = fp - lo;
    const t = TSTR[lo] || '—';
    const tr = lerp(TREL[lo] || 0, TREL[hi] || 0, f);
    const alt = lerp(Z[lo], Z[hi], f);
    const dist = lerp(cumD[lo], cumD[hi], f);
    document.getElementById('hud-time').textContent    = 'TIME ' + t + ' __TZLABEL__';
    document.getElementById('hud-elapsed').textContent = 'T+' + tr.toFixed(1) + 's';
    document.getElementById('hud-alt').textContent     = 'ALT ' + alt.toFixed(1) + ' m';
    document.getElementById('hud-d').textContent       = 'DIST ' + dist.toFixed(1) + ' m';
    document.getElementById('hud-i').textContent       = 'SAMPLE ' + (lo+1) + '/' + N;
    document.getElementById('t3d-time').textContent    = t + ' __TZLABEL__';
    document.getElementById('t3d-rel').textContent     = 'T+' + tr.toFixed(1) + 's';
  }

  // Smooth interpolated direction vector at fractional sample position
  function dirAt(fp) {
    const lo = Math.floor(fp);
    const hi = Math.min(N-1, lo + 1);
    const t = fp - lo;
    const dlo = dir(lo), dhi = dir(hi);
    let u = lerp(dlo[0], dhi[0], t);
    let v = lerp(dlo[1], dhi[1], t);
    let w = lerp(dlo[2], dhi[2], t);
    const m = Math.hypot(u, v, w);
    if (m < 1e-6) return [0, 1, 0];
    return [u/m, v/m, w/m];
  }

  // Interpolated rotated mesh at any fractional position
  function rotatedAircraftVertsAt(fp) {
    const lo = Math.floor(fp), hi = Math.min(N-1, lo + 1), t = fp - lo;
    const cx = lerp(X[lo], X[hi], t);
    const cy = lerp(Y[lo], Y[hi], t);
    const cz = lerp(Z[lo], Z[hi], t);
    const fwd = dirAt(fp);
    const upx=0, upy=0, upz=1;
    let rx = fwd[1]*upz - fwd[2]*upy;
    let ry = fwd[2]*upx - fwd[0]*upz;
    let rz = fwd[0]*upy - fwd[1]*upx;
    let rm = Math.hypot(rx, ry, rz);
    if (rm < 1e-6) { rx=1; ry=0; rz=0; rm=1; }
    rx/=rm; ry/=rm; rz/=rm;
    const u2x = ry*fwd[2] - rz*fwd[1];
    const u2y = rz*fwd[0] - rx*fwd[2];
    const u2z = rx*fwd[1] - ry*fwd[0];
    const nv = BODY.length;
    const xs = new Array(nv), ys = new Array(nv), zs = new Array(nv);
    for (let k = 0; k < nv; k++) {
      const v = BODY[k];
      const sx = v[0]*S, sy = -v[1]*S, sz = v[2]*S;
      xs[k] = sx*rx + sy*fwd[0] + sz*u2x + cx;
      ys[k] = sx*ry + sy*fwd[1] + sz*u2y + cy;
      zs[k] = sx*rz + sy*fwd[2] + sz*u2z + cz;
    }
    return { x: xs, y: ys, z: zs };
  }

  // Trail = all samples up to lo, plus interpolated tip
  function trailAt(fp) {
    const lo = Math.floor(fp), hi = Math.min(N-1, lo + 1), t = fp - lo;
    const tx = X.slice(0, lo + 1); tx.push(lerp(X[lo], X[hi], t));
    const ty = Y.slice(0, lo + 1); ty.push(lerp(Y[lo], Y[hi], t));
    const tz = Z.slice(0, lo + 1); tz.push(lerp(Z[lo], Z[hi], t));
    return { x: tx, y: ty, z: tz };
  }

  let pos = 0;             // fractional sample index [0..N-1]
  let playing = false;
  let speed = 1.0;
  let lastT = 0;
  let lastRender = 0;
  const TARGET_FPS = 30;   // throttle Plotly.restyle to 30fps (smooth + fast)

  function renderFrame(fp) {
    pos = Math.max(0, Math.min(N - 1, fp));
    const trail = trailAt(pos);
    const verts = rotatedAircraftVertsAt(pos);
    Plotly.restyle('plot', {
      x: [trail.x, verts.x],
      y: [trail.y, verts.y],
      z: [trail.z, verts.z]
    }, [1, 2]);
    updateHud(pos);
    document.getElementById('scrub3d').value = pos.toString();
  }

  function loop(t) {
    if (!playing) return;
    if (lastT === 0) { lastT = t; lastRender = t; requestAnimationFrame(loop); return; }
    const dt = (t - lastT) / 1000;
    lastT = t;
    pos += dt * BASE_INDEX_PER_SEC * speed;
    if (pos >= N - 1) {
      pos = N - 1;
      playing = false;
      renderFrame(pos);
      return;
    }
    if (t - lastRender >= 1000 / TARGET_FPS) {
      lastRender = t;
      renderFrame(pos);
    }
    requestAnimationFrame(loop);
  }

  Plotly.newPlot('plot', [fullRoute, flownTrail, aircraft, startMarker, endMarker, distMarkers], layout, config)
    .then(gd => {
      document.getElementById('scrub3d').max = (N - 1).toString();
      renderFrame(0);

      document.getElementById('btn-play3d').addEventListener('click', () => {
        if (playing) return;
        if (pos >= N - 1) pos = 0;
        playing = true; lastT = 0;
        requestAnimationFrame(loop);
      });
      document.getElementById('btn-pause3d').addEventListener('click', () => { playing = false; });
      document.getElementById('btn-reset3d').addEventListener('click', () => {
        playing = false; renderFrame(0);
      });
      document.getElementById('scrub3d').addEventListener('input', (e) => {
        playing = false;
        renderFrame(parseFloat(e.target.value));
      });
      document.querySelectorAll('#ctrl3d .speed-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          speed = parseFloat(btn.dataset.speed);
          document.querySelectorAll('#ctrl3d .speed-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
        });
      });

      // External bridge: master timeline can drive this view via window.setPos(t_sec)
      window.setPos = function(t_sec) {
        if (!TREL || TREL.length < 2) return;
        playing = false;
        if (t_sec <= TREL[0]) { renderFrame(0); return; }
        if (t_sec >= TREL[N-1]) { renderFrame(N-1); return; }
        let lo = 0;
        for (let i = 1; i < N; i++) {
          if (TREL[i] >= t_sec) { lo = i - 1; break; }
        }
        const span = TREL[lo+1] - TREL[lo];
        const f = span > 0 ? (t_sec - TREL[lo]) / span : 0;
        renderFrame(lo + f);
      };
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
  .leaflet-container{background:#0b1220 !important;font-family:"Inter","Helvetica Neue","Segoe UI",sans-serif}
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
    color:#8b97b3;border-radius:8px;font-family:"Inter","Helvetica Neue","Segoe UI",sans-serif;
    z-index:1000;text-align:center
  }
</style>
</head><body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const TRACK = __TRACK__;
const COORDS = TRACK.coords    || [];
const ALTS   = TRACK.alts      || [];
const TREL   = TRACK.trel      || [];
const WAYPOINTS = TRACK.waypoints || [];
const FENCE     = TRACK.fence     || [];
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

// Altitude → color (cyan low → violet mid → amber high)
function altColor(t) {
  // t in [0,1]
  const lerp = (a, b, k) => Math.round(a + (b - a) * k);
  let r, g, b;
  if (t < 0.5) { const k = t * 2;
    r = lerp(0x22, 0xa7, k); g = lerp(0xd3, 0x8b, k); b = lerp(0xee, 0xfa, k);
  } else { const k = (t - 0.5) * 2;
    r = lerp(0xa7, 0xfb, k); g = lerp(0x8b, 0xbf, k); b = lerp(0xfa, 0x24, k);
  }
  return 'rgb(' + r + ',' + g + ',' + b + ')';
}

// --- Track ---
if (COORDS.length > 1) {
  // Single glow line under the colored segments for visual depth
  L.polyline(COORDS, {color:'#22d3ee', weight:10, opacity:0.18}).addTo(map);

  const allTrack = L.featureGroup().addTo(map);

  if (ALTS.length === COORDS.length && ALTS.length > 1) {
    let aMin = Infinity, aMax = -Infinity;
    for (const a of ALTS) { if (a < aMin) aMin = a; if (a > aMax) aMax = a; }
    const span = (aMax - aMin) || 1;
    // Draw each segment colored by its midpoint altitude
    for (let i = 0; i < COORDS.length - 1; i++) {
      const midAlt = (ALTS[i] + ALTS[i+1]) / 2;
      const t = (midAlt - aMin) / span;
      const seg = L.polyline([COORDS[i], COORDS[i+1]], {
        color: altColor(t), weight: 3.5, opacity: 1.0
      });
      seg.bindTooltip('alt: ' + midAlt.toFixed(1) + ' m', {sticky:true});
      seg.addTo(allTrack);
    }
    // Altitude legend in the bottom-right
    const legend = L.control({position:'bottomright'});
    legend.onAdd = function() {
      const div = L.DomUtil.create('div');
      div.style.cssText = 'background:rgba(17,26,46,0.92);border:1px solid #243154;'
        + 'border-radius:6px;padding:8px 10px;font-family:Inter,sans-serif;'
        + 'color:#e6edf7;font-size:11px;box-shadow:0 2px 8px rgba(0,0,0,0.5)';
      div.innerHTML = '<div style="font-size:10px;letter-spacing:1.5px;color:#8b97b3;'
        + 'font-weight:700;margin-bottom:4px">ALTITUDE</div>'
        + '<div style="height:80px;width:14px;float:left;margin-right:8px;'
        + 'background:linear-gradient(to top, #22d3ee 0%, #a78bfa 50%, #d9a14a 100%);'
        + 'border-radius:3px;border:1px solid #243154"></div>'
        + '<div style="font-family:JetBrains Mono,monospace;line-height:80px;font-size:10px;'
        + 'display:flex;flex-direction:column;justify-content:space-between;height:80px">'
        + '<span>' + aMax.toFixed(0) + ' m</span>'
        + '<span style="color:#8b97b3">' + ((aMin+aMax)/2).toFixed(0) + ' m</span>'
        + '<span>' + aMin.toFixed(0) + ' m</span></div>'
        + '<div style="clear:both"></div>';
      return div;
    };
    legend.addTo(map);
  } else {
    // Fallback (no altitude data): single cyan line
    L.polyline(COORDS, {color:'#22d3ee', weight:3, opacity:1.0}).addTo(allTrack);
  }

  L.circleMarker(COORDS[0], {
    radius:8, color:'#0b1220', fillColor:'#34d399', fillOpacity:1, weight:2
  }).addTo(map).bindTooltip('start', {direction:'top', permanent:false});
  L.circleMarker(COORDS[COORDS.length-1], {
    radius:8, color:'#0b1220', fillColor:'#f87171', fillOpacity:1, weight:2
  }).addTo(map).bindTooltip('end', {direction:'top', permanent:false});

  // Moving marker driven by the master timeline (window.setPos)
  const flightMarker = L.circleMarker(COORDS[0], {
    radius:10, color:'#0b1220', fillColor:'#22d3ee', fillOpacity:1,
    weight:3, className:'flight-marker'
  });
  window.setPos = function(t_sec) {
    if (!TREL || TREL.length !== COORDS.length || TREL.length < 2) return;
    if (t_sec <= TREL[0]) { flightMarker.setLatLng(COORDS[0]).addTo(map); return; }
    if (t_sec >= TREL[TREL.length-1]) {
      flightMarker.setLatLng(COORDS[COORDS.length-1]).addTo(map); return;
    }
    let lo = 0;
    for (let i = 1; i < TREL.length; i++) {
      if (TREL[i] >= t_sec) { lo = i - 1; break; }
    }
    const span = TREL[lo+1] - TREL[lo];
    const f = span > 0 ? (t_sec - TREL[lo]) / span : 0;
    const lat = COORDS[lo][0] + (COORDS[lo+1][0] - COORDS[lo][0]) * f;
    const lng = COORDS[lo][1] + (COORDS[lo+1][1] - COORDS[lo][1]) * f;
    flightMarker.setLatLng([lat, lng]).addTo(map);
  };

  // ---- Geofence polygon ----
  if (FENCE && FENCE.length >= 3) {
    const poly = L.polygon(FENCE, {
      color:'#d9a14a', weight:2, opacity:0.9,
      fillColor:'#d9a14a', fillOpacity:0.08, dashArray:'6,6'
    }).addTo(map);
    poly.bindTooltip('Geofence', {sticky:true});
  }
  // ---- Mission waypoints ----
  if (WAYPOINTS && WAYPOINTS.length) {
    const wpLatLngs = WAYPOINTS.map(w => [w.lat, w.lng]);
    L.polyline(wpLatLngs, {color:'#a78bfa', weight:2, opacity:0.7,
                           dashArray:'8,6'}).addTo(map);
    WAYPOINTS.forEach((w, i) => {
      const m = L.circleMarker([w.lat, w.lng], {
        radius:9, color:'#0b1220', fillColor:'#a78bfa',
        fillOpacity:1, weight:2
      }).addTo(map);
      const lbl = L.divIcon({
        className:'',
        html:'<div style="font-family:Inter,sans-serif;font-size:10px;'
            +'font-weight:700;color:#a78bfa;text-shadow:0 0 4px #0b1220,0 0 4px #0b1220">'
            + (i + 1) + '</div>',
        iconSize:[12,12], iconAnchor:[6,6]
      });
      L.marker([w.lat, w.lng], {icon:lbl, interactive:false}).addTo(map);
      m.bindTooltip(
        'WP ' + (i + 1) + ' / ' + (w.tot || WAYPOINTS.length)
        + (w.alt ? '<br>alt: ' + w.alt.toFixed(1) + ' m' : '')
        + (w.id  ? '<br>cmd: ' + w.id : ''),
        {direction:'top'}
      );
    });
  }

  const bounds = allTrack.getBounds().pad(0.3);
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


def detect_frame_kind(parsed: dict) -> str:
    """Classify the airframe for motor / servo interpretation.
    Returns 'copter' (multirotor incl. VTOL hover side), 'plane', 'heli',
    'rover', 'sub', or 'other'. Drives whether per-RCOU spread / desync
    analysis makes sense."""
    mt = parsed.get("vehicle_type")
    # MAV_TYPE values from pymavlink
    if mt in {2, 3, 13, 14, 15, 19, 20, 21, 22, 23}:
        return "copter"      # quad / hex / oct / tri / coax / VTOL variants
    if mt == 1:
        return "plane"
    if mt == 4:
        return "heli"
    if mt in (10, 11):
        return "rover"
    if mt == 12:
        return "sub"
    params = parsed.get("params") or {}
    if params.get("Q_ENABLE"):
        return "copter"      # quadplane in VTOL mode behaves like a copter
    if "FRAME_CLASS" in params and params.get("FRAME_CLASS"):
        return "copter"      # ArduCopter sets FRAME_CLASS; ArduPlane does not
    return "other"


def analyze_pid_tracking(parsed: dict) -> dict:
    """Per-axis attitude-tracking analysis: how well does the actual angle
    follow the commanded angle? Returns {'roll': {...}, 'pitch': {...},
    'yaw': {...}} where each axis dict has:
      rms_err   — RMS of (actual - desired) in degrees
      peak_err  — peak |actual - desired|
      osc_hz    — dominant oscillation frequency of the error (Hz, 0 = none)
      lag_ms    — best-fit time delay between desired and actual (ms)
      verdict   — 'good' | 'loose' | 'oscillating' | 'lagging' | 'no-data'
      hint      — plain-English suggestion (which gain to nudge)"""
    out = {}
    att = (parsed.get("data") or {}).get("ATT")
    att_t = (parsed.get("times") or {}).get("ATT")
    if not att or att_t is None or len(att_t) < 50:
        return out
    t = np.asarray(att_t, dtype=float)
    # Use only "armed and moving" samples if possible — keeps benchtop data out
    stat = (parsed.get("data") or {}).get("STAT")
    armed_mask = None
    if stat and "Armed" in stat:
        st = np.asarray((parsed.get("times") or {}).get("STAT", []), dtype=float)
        sa = np.asarray(stat["Armed"], dtype=float)
        if len(st) == len(sa) and len(st) > 1:
            armed_mask = np.interp(t, st, sa) > 0.5
    pairs = [("roll", "Roll", "DesRoll"),
             ("pitch", "Pitch", "DesPitch"),
             ("yaw",   "Yaw",   "DesYaw")]
    for axis, actual, desired in pairs:
        if actual not in att or desired not in att:
            continue
        a = np.asarray(att[actual], dtype=float)
        d = np.asarray(att[desired], dtype=float)
        if len(a) != len(t) or len(d) != len(t):
            continue
        m = np.isfinite(a) & np.isfinite(d)
        if armed_mask is not None and armed_mask.shape == m.shape:
            m &= armed_mask
        if m.sum() < 50:
            continue
        a = a[m]; d = d[m]; tt = t[m]
        # Skip axes where the commanded signal is essentially flat — there's
        # no real "tracking" to evaluate. This is especially common for yaw
        # on ArduPlane (planes bank to turn, so DesYaw stays ~0 and the only
        # measured "error" would be the plane's actual heading wandering).
        if float(np.std(d)) < 1.0:
            out[axis] = {
                "rms_err": 0.0, "peak_err": 0.0,
                "osc_hz": 0.0, "lag_ms": 0.0,
                "verdict": "no-command",
                "hint": (f"{axis.upper()} has no real command in this log "
                         f"(desired is flat). On a plane this is normal for yaw — "
                         f"the autopilot banks to turn instead of commanding heading."),
            }
            continue
        err = a - d
        # Yaw can wrap — unwrap relative angle
        if axis == "yaw":
            err = ((err + 180) % 360) - 180
        rms_err = float(np.sqrt(np.mean(err ** 2)))
        peak_err = float(np.nanmax(np.abs(err)))
        # Oscillation frequency: count zero-crossings of (err - mean(err))
        e0 = err - np.mean(err)
        signs = np.sign(e0)
        crossings = int(np.sum(np.abs(np.diff(signs)) > 1))
        duration = float(tt[-1] - tt[0])
        osc_hz = (crossings / 2.0) / duration if duration > 0 else 0.0
        # Lag: best-fit shift of desired to align with actual (cross-correlate,
        # search up to 250 ms of shift)
        try:
            dt = float(np.median(np.diff(tt))) or 0.02
            max_shift = int(0.25 / dt)
            best_shift = 0; best_corr = -1e9
            d_c = d - np.mean(d); a_c = a - np.mean(a)
            for s in range(0, max_shift + 1):
                if s == 0:
                    c = float(np.dot(d_c, a_c))
                else:
                    c = float(np.dot(d_c[:-s], a_c[s:]))
                if c > best_corr:
                    best_corr = c; best_shift = s
            lag_ms = best_shift * dt * 1000.0
        except Exception:
            lag_ms = 0.0
        # Verdict
        # Oscillation: more than ~3 Hz on the error usually means P too high
        # (rate-loop ringing manifests as zero-crossings of error around mean).
        if osc_hz > 4.0 and rms_err > 1.5:
            verdict = "oscillating"
            hint = (f"{axis.upper()} error oscillates at ~{osc_hz:.1f} Hz — "
                    f"P gain likely too high. Reduce *_RATE_P by ~20%.")
        elif rms_err > 8.0:
            verdict = "loose"
            hint = (f"{axis.upper()} tracking is loose (RMS {rms_err:.1f}°). "
                    f"Increase *_RATE_P by ~20% or check FF gain.")
        elif rms_err > 4.0 or peak_err > 25:
            verdict = "loose"
            hint = (f"{axis.upper()} tracks but with delay/overshoot. "
                    f"Consider small P bump or check that *_RATE_I isn't 0.")
        elif lag_ms > 150 and rms_err > 2.0:
            verdict = "lagging"
            hint = (f"{axis.upper()} lags command by ~{lag_ms:.0f} ms — "
                    f"raise *_RATE_P or *_RATE_D slightly.")
        else:
            verdict = "good"
            hint = (f"{axis.upper()} tracks well "
                    f"(RMS {rms_err:.1f}°, peak {peak_err:.0f}°, "
                    f"{osc_hz:.1f} Hz, lag {lag_ms:.0f} ms).")
        out[axis] = {
            "rms_err": rms_err, "peak_err": peak_err,
            "osc_hz": osc_hz, "lag_ms": lag_ms,
            "verdict": verdict, "hint": hint,
        }
    return out


def auto_review(parsed: dict) -> list[dict]:
    """Run a plain-English health check across the parsed log.
    Returns a list of {category, verdict, color, headline, detail} dicts."""
    data = parsed["data"]
    items: list[dict] = []

    # Hover tooltips for each category — plain-English explanations
    TIPS = {
        "Vibration":
            "ArduPilot's VIBE message records 3-axis acceleration variance "
            "from the IMU. Under 30 m/s² is fine, over 60 m/s² degrades EKF "
            "and position hold. Fixes: balance props, clean motor mounts, "
            "soft-mount the flight controller.",
        "IMU clipping":
            "Counter that increments whenever the accelerometer hits its "
            "measurement range limit (saturates). Any clipping at all means "
            "vibration spikes — usually unbalanced props.",
        "GPS":
            "Quality of the GPS fix during the flight. HDop is the geometric "
            "dilution of precision (lower = better, <1.5 excellent). For "
            "Loiter/Auto/RTL you want HDop <1.5 and ≥8 satellites.",
        "Battery":
            "LiPo cells should stay above 3.5V each under load and never "
            "drop below 3.3V. Below that you damage the cells and risk "
            "venting/swelling. Land sooner or use a bigger pack.",
        "Compass":
            "Magnetic-field magnitude variance. Steady = good. >15% swing "
            "usually means a power cable is too close to the compass — "
            "redirect wiring or run Compass-Motor calibration.",
        "EKF (state estimator)":
            "ArduPilot's Extended Kalman Filter fuses IMU+GPS+compass+baro. "
            "Innovation = how much the next measurement disagreed with the "
            "filter's prediction. Spikes above 1.0 indicate the filter is "
            "struggling (bad GPS, magnetic interference, or vibration).",
        "Errors":
            "ERR messages logged by ArduPilot subsystems. Each one corresponds "
            "to a specific failure (sensor failure, RC loss, EKF failsafe, "
            "geofence breach, etc.). Look up Subsys/ECode pairs in the "
            "ArduPilot wiki for details.",
        "Altitude":
            "AGL (above takeoff) altitude profile. Vertical speed peaks "
            "above 8 m/s indicate aggressive throttle inputs.",
        "Attitude":
            "Peak roll/pitch angles. Under 25° = calm, 25-45° = sport, "
            ">45° = acro. Above 60° the drone loses altitude rapidly.",
        "Motor balance":
            "PWM output across motors. Should be within ~60 µs of each "
            "other. Large spreads point to CG offset, bent arm, prop "
            "imbalance, or one worn-out motor.",
        "Power used":
            "Total milliamp-hours drawn during the flight. Try to land "
            "before 80% of pack capacity is used.",
        "RC link":
            "Stability of the RC receiver signal. Brief dropouts at long "
            "range are normal; sustained drops mean RF interference or a "
            "weak link — check antennas.",
        "Autopilot CPU":
            "Maximum 'main loop' execution time. The autopilot runs at "
            "400 Hz (2500 µs budget). Overruns mean the FC is missing "
            "real-time deadlines — reduce logging, disable unused features.",
        "IMU temperature":
            "Temperature drift across the flight. Big swings shift gyro "
            "bias, which the EKF has to compensate for. IMU heaters or "
            "letting the FC warm up before arming help.",
        "Flight modes":
            "Sequence of flight modes used. ArduCopter modes: 0=Stabilize, "
            "5=Loiter, 6=RTL, 9=Land, etc.",
        "Incidents detected":
            "Notable events the auto-analyzer flagged from the data: ERR "
            "codes, extreme attitudes, rapid altitude loss, EKF stress, RC "
            "failsafes, and low-battery alerts.",
        "Takeoff health":
            "Per-takeoff analysis for fixed-wing TAKEOFF mode entries. "
            "Checks throttle ramp speed (torque-roll risk), rotation airspeed "
            "vs stall, roll divergence from commanded, compass interference "
            "under load, and key TKOFF_* parameter values.",
        "PID tracking":
            "Compares commanded (DesRoll/DesPitch/DesYaw) with actual "
            "(Roll/Pitch/Yaw) from the ATT message. Loose tracking → raise "
            "P gain. Oscillation on the error signal → lower P gain. Lag "
            "without oscillation → raise D slightly or check feed-forward.",
        "CPU loop overruns":
            "ArduPilot's main control loop runs at a fixed rate (plane 50 Hz "
            "= 20 000 µs / loop, copter 400 Hz = 2 500 µs / loop). If a loop "
            "overruns the budget, the autopilot is briefly 'blind' — no "
            "servo / motor updates for that time. Usually caused by slow SD "
            "cards stalling on log writes.",
    }
    def add(category, verdict, color, headline, detail):
        items.append({
            "category": category, "verdict": verdict, "color": color,
            "headline": headline, "detail": detail,
            "tip": TIPS.get(category, ""),
        })

    kind = detect_frame_kind(parsed)

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
            add("Vibration", "Marginal", WARN,
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
            add("IMU clipping", "Marginal", WARN,
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
                add("GPS", "Marginal", WARN,
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
                add("Battery", "Marginal", WARN,
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
                add("Compass", "Marginal", WARN,
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
            add("EKF (state estimator)", "Marginal", WARN,
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
                DANGER if n_err > 3 else WARN,
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
            add("Attitude", "Marginal", WARN,
                f"Aggressive tilt angles (peak {peak:.0f}°).",
                f"Roll {peak_roll:.0f}°, pitch {peak_pitch:.0f}°. Above 45° the drone needs more "
                f"throttle just to stay level — fine for acro, watch altitude loss otherwise.")

    # ---------- Throttle / motor output balance ----------
    # Only meaningful on multirotors / helis. On a plane, RCOU channels are
    # servos (aileron/elevator/rudder) sitting at ~1500 µs plus a throttle
    # channel — comparing their spread says nothing about motor health.
    rcou = data.get("RCOU")
    if rcou and kind in ("copter", "heli"):
        ch_keys = [k for k in rcou.keys() if k.startswith("C") and k[1:].isdigit()]
        ch_keys = sorted(ch_keys, key=lambda s: int(s[1:]))[:8]  # first 8 motors
        if len(ch_keys) >= 4:
            named_means: list[tuple[str, float]] = []
            for k in ch_keys:
                arr = np.asarray(rcou[k], dtype=float)
                arr = arr[(arr > 1050) & (arr < 2000)]  # only flying samples
                if len(arr):
                    named_means.append((k, float(np.mean(arr))))
            if len(named_means) >= 4:
                means = [m for _, m in named_means]
                spread = max(means) - min(means)
                avg = sum(means) / len(means)
                # Identify worst offender: motor with largest |Δ| from average
                worst_k, worst_m = max(named_means, key=lambda nm: abs(nm[1] - avg))
                worst_delta = worst_m - avg
                sign = "+" if worst_delta >= 0 else ""
                role = "working harder" if worst_delta > 0 else "underloaded / weaker"
                worst_str = f"{worst_k} ({sign}{worst_delta:.0f} µs vs avg — {role})"
                if spread < 60:
                    add("Motor balance", "Good", SUCCESS,
                        f"Motors well balanced (spread {spread:.0f} µs across {len(means)} motors).",
                        f"Average PWM {avg:.0f} µs. Less than 60 µs spread is healthy. "
                        f"Largest deviation: {worst_str}.")
                elif spread < 150:
                    add("Motor balance", "Marginal", WARN,
                        f"Motors slightly uneven (spread {spread:.0f} µs). Worst: {worst_k}.",
                        f"Could be CG offset, prop wear, or one motor working harder. "
                        f"Outlier: {worst_str}. Check that motor's prop, bell, and arm.")
                else:
                    add("Motor balance", "Bad", DANGER,
                        f"Motor output spread is large ({spread:.0f} µs). Worst: {worst_k}.",
                        f"{worst_str}. Usually a CG / weight imbalance, bent arm, weak motor, "
                        f"or damaged prop on that specific channel. Inspect {worst_k} first.")

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
                    add("RC link", "Marginal", WARN,
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
                add("Autopilot CPU", "Marginal", WARN,
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
                add("IMU temperature", "Marginal", WARN,
                    f"Large IMU temperature swing ({spread:.0f} °C).",
                    "Big temperature shifts can shift gyro bias. Consider IMU heating or letting "
                    "the FC warm up before arming.")

    # ---------- Takeoff health (fixed-wing only) ----------
    params = parsed.get("params") or {}
    times = parsed.get("times") or {}
    if kind == "plane":
        mode_msgs = data.get("MODE")
        mode_t = times.get("MODE")
        att = data.get("ATT")
        att_t = times.get("ATT")
        ctun = data.get("CTUN")
        ctun_t = times.get("CTUN")
        gps = data.get("GPS")
        gps_t = times.get("GPS")
        if (mode_msgs and "Mode" in mode_msgs and mode_t and att and att_t
                and ctun and ctun_t):
            mode_arr = np.asarray(mode_msgs["Mode"], dtype=int)
            mt = np.asarray(mode_t, dtype=float)
            t0_log = parsed.get("t_start") or 0.0
            # ArduPlane TAKEOFF mode = 13
            takeoff_windows = []
            for i, mv in enumerate(mode_arr):
                if int(mv) == 13:
                    t_in = float(mt[i])
                    t_out = float(mt[i + 1]) if i + 1 < len(mt) else float(mt[-1] + 30)
                    if t_out - t_in > 1.0:
                        takeoff_windows.append((t_in, t_out))
            if takeoff_windows:
                ta = np.asarray(att_t, dtype=float)
                roll = np.asarray(att.get("Roll", []), dtype=float)
                desr = np.asarray(att.get("DesRoll", []), dtype=float)
                tc = np.asarray(ctun_t, dtype=float)
                tho = np.asarray(ctun.get("ThO", []), dtype=float)
                gs = None
                if gps and gps_t:
                    tg = np.asarray(gps_t, dtype=float)
                    spd_key = "Spd" if "Spd" in gps else ("GroundSpeed" if "GroundSpeed" in gps else None)
                    if spd_key:
                        gs = (tg, np.asarray(gps[spd_key], dtype=float))
                # Params (string keys for clarity)
                p_slew     = params.get("TKOFF_THR_SLEW")
                p_rotspd   = params.get("TKOFF_ROTATE_SPD")
                p_arsp_use = params.get("ARSPD_USE")
                p_aspd_min = params.get("AIRSPEED_MIN")
                p_lvl_pit  = params.get("TKOFF_LVL_PITCH")
                p_rddr     = params.get("KFF_RDDRMIX")
                lines: list[str] = []
                worst_sev = 0    # 0=ok, 1=warn, 2=bad
                for idx, (ti, tf) in enumerate(takeoff_windows, 1):
                    win_a = (ta >= ti) & (ta <= tf)
                    win_c = (tc >= ti) & (tc <= tf)
                    if win_a.sum() < 5 or win_c.sum() < 5:
                        continue
                    # Throttle ramp time: ThO crossing 10% → 80%
                    tho_w = tho[win_c]; tc_w = tc[win_c]
                    above10 = np.where(tho_w > 10)[0]
                    above80 = np.where(tho_w > 80)[0]
                    ramp_s = None
                    if len(above10) and len(above80):
                        ramp_s = float(tc_w[above80[0]] - tc_w[above10[0]])
                    # Peak roll divergence in the window
                    if len(roll) == len(desr):
                        dev = np.abs(roll[win_a] - desr[win_a])
                        peak_dev = float(np.nanmax(dev)) if dev.size else 0.0
                    else:
                        peak_dev = 0.0
                    # GPS speed at the rotation moment (first time ThO > 60%)
                    rotate_spd = None
                    if gs is not None and len(above10):
                        # find time when throttle first crossed 60%
                        above60 = np.where(tho_w > 60)[0]
                        if len(above60):
                            t_rot = float(tc_w[above60[0]])
                            tg_a, spd_a = gs
                            j = int(np.argmin(np.abs(tg_a - t_rot)))
                            rotate_spd = float(spd_a[j])
                    # Wall-clock start
                    wall = fmt_istanbul(t0_log + ti)
                    bits = [f"<b>Takeoff #{idx}</b> at {wall}"]
                    if ramp_s is not None:
                        if ramp_s < 0.3:
                            worst_sev = max(worst_sev, 2)
                            bits.append(f"throttle slammed 0→80% in <b style='color:{DANGER}'>{ramp_s:.2f}s</b> (torque roll risk)")
                        elif ramp_s < 1.0:
                            worst_sev = max(worst_sev, 1)
                            bits.append(f"throttle ramp {ramp_s:.2f}s (marginal)")
                        else:
                            bits.append(f"throttle ramp {ramp_s:.2f}s")
                    if rotate_spd is not None and p_aspd_min:
                        margin = rotate_spd - float(p_aspd_min)
                        if margin < 0:
                            worst_sev = max(worst_sev, 2)
                            bits.append(f"rotated at <b style='color:{DANGER}'>{rotate_spd:.1f} m/s</b> — {abs(margin):.1f} m/s BELOW stall ({p_aspd_min:.0f})")
                        elif margin < 3:
                            worst_sev = max(worst_sev, 1)
                            bits.append(f"rotated at {rotate_spd:.1f} m/s (only {margin:.1f} m/s stall margin)")
                        else:
                            bits.append(f"rotated at {rotate_spd:.1f} m/s ({margin:+.1f} m/s vs stall)")
                    if peak_dev > 90:
                        worst_sev = max(worst_sev, 2)
                        bits.append(f"Roll diverged <b style='color:{DANGER}'>{peak_dev:.0f}°</b> from command — likely tumble")
                    elif peak_dev > 30:
                        worst_sev = max(worst_sev, 1)
                        bits.append(f"Roll diverged {peak_dev:.0f}° from command")
                    lines.append(" · ".join(bits))
                # Param sanity block
                param_warns: list[str] = []
                if p_slew is not None and float(p_slew) < 1.0:
                    worst_sev = max(worst_sev, 2)
                    param_warns.append(f"TKOFF_THR_SLEW={p_slew:.1f} (set to 2–3 to ramp throttle)")
                if p_rotspd is not None and float(p_rotspd) < 1.0:
                    worst_sev = max(worst_sev, 1)
                    param_warns.append(f"TKOFF_ROTATE_SPD={p_rotspd:.1f} (set to ≥ AIRSPEED_MIN + 3)")
                if p_arsp_use is not None and float(p_arsp_use) == 0.0 and p_aspd_min:
                    param_warns.append(f"ARSPD_USE=0 (no airspeed sensor — launch into the wind!)")
                if p_lvl_pit is not None and float(p_lvl_pit) > 14:
                    worst_sev = max(worst_sev, 1)
                    param_warns.append(f"TKOFF_LVL_PITCH={p_lvl_pit:.0f}° (drop to 12° for safer climb)")
                if p_rddr is not None and float(p_rddr) < 0.5:
                    param_warns.append(f"KFF_RDDRMIX={p_rddr:.2f} (raise to 0.5–0.7 to fight torque roll)")
                detail_html = "<br/>".join(lines) if lines else ""
                if param_warns:
                    detail_html += "<br/><br/><b>Param suggestions:</b><br/>• " + "<br/>• ".join(param_warns)
                if lines or param_warns:
                    verdict = "Good" if worst_sev == 0 else ("Marginal" if worst_sev == 1 else "Bad")
                    color = SUCCESS if worst_sev == 0 else (WARN if worst_sev == 1 else DANGER)
                    headline = f"{len(takeoff_windows)} TAKEOFF mode entry / entries analysed."
                    add("Takeoff health", verdict, color, headline, detail_html)

    # ---------- PID tracking quality ----------
    pid_stats = analyze_pid_tracking(parsed)
    if pid_stats:
        worst_v = "good"
        lines: list[str] = []
        # Worst-verdict precedence (worse wins)
        rank = {"good": 0, "no-command": 0, "lagging": 1, "loose": 1, "oscillating": 2}
        for axis in ("roll", "pitch", "yaw"):
            s = pid_stats.get(axis)
            if not s:
                continue
            if rank.get(s["verdict"], 0) > rank.get(worst_v, 0):
                worst_v = s["verdict"]
            badge = {"good": SUCCESS, "loose": WARN, "lagging": WARN,
                     "oscillating": DANGER, "no-command": TEXT_DIM}[s["verdict"]]
            if s["verdict"] == "no-command":
                lines.append(
                    f"<b style='color:{badge}'>{axis.upper():5s}</b> · "
                    f"<span style='color:{TEXT_DIM}'>{s['hint']}</span>"
                )
            else:
                lines.append(
                    f"<b style='color:{badge}'>{axis.upper():5s}</b> · "
                    f"RMS err {s['rms_err']:.1f}° · peak {s['peak_err']:.0f}° · "
                    f"err osc {s['osc_hz']:.1f} Hz · lag {s['lag_ms']:.0f} ms<br/>"
                    f"<span style='color:{TEXT_DIM}'>&nbsp;&nbsp;{s['hint']}</span>"
                )
        if lines:
            verdict_lbl = {"good": "Good", "loose": "Marginal", "lagging": "Marginal",
                           "oscillating": "Bad", "no-command": "Good"}[worst_v]
            verdict_clr = {"good": SUCCESS, "loose": WARN, "lagging": WARN,
                           "oscillating": DANGER, "no-command": SUCCESS}[worst_v]
            tracked = sum(1 for s in pid_stats.values() if s["verdict"] != "no-command")
            head = (f"Attitude controller — {worst_v} tracking "
                    f"({tracked} axis/axes actively commanded).")
            add("PID tracking", verdict_lbl, verdict_clr, head, "<br/>".join(lines))

    # ---------- CPU loop overruns ----------
    pm = data.get("PM")
    if pm:
        # Plane 50 Hz → 20000 µs budget; copter 400 Hz → 2500 µs; default plane
        loop_budget = 2500 if kind == "copter" else 20000
        max_t_arr = None
        for key in ("MaxT", "Maxt", "maxT"):
            if key in pm:
                max_t_arr = np.asarray(pm[key], dtype=float)
                break
        nlon_arr = None
        for key in ("NLon", "nlon", "NLoop"):
            if key in pm:
                nlon_arr = np.asarray(pm[key], dtype=float)
                break
        load_arr = np.asarray(pm.get("Load", []), dtype=float) if "Load" in pm else None
        if max_t_arr is not None and len(max_t_arr):
            max_t = float(np.nanmax(max_t_arr))
            ratio = max_t / loop_budget
            n_long = int(np.nansum(nlon_arr)) if nlon_arr is not None else 0
            load_pct = (float(np.nanmax(load_arr)) / 10.0) if load_arr is not None and len(load_arr) else None
            extra = f" · {n_long} long-loop event(s)" if n_long else ""
            if load_pct is not None:
                extra += f" · peak CPU load {load_pct:.0f}%"
            if ratio < 1.2:
                add("CPU loop overruns", "Good", SUCCESS,
                    f"Max loop {max_t:.0f} µs (budget {loop_budget} µs).{extra}",
                    "Autopilot is keeping up with its control loop comfortably.")
            elif ratio < 2.0:
                add("CPU loop overruns", "Marginal", WARN,
                    f"Max loop {max_t:.0f} µs — {ratio:.1f}× the {loop_budget} µs budget.{extra}",
                    "Occasional overruns. Usually slow SD card stalls on log writes. "
                    "Use a high-quality class-10 / A1 SD card, format with SDFormatter, "
                    "and consider reducing LOG_BITMASK.")
            else:
                add("CPU loop overruns", "Bad", DANGER,
                    f"Max loop {max_t:.0f} µs — {ratio:.1f}× the {loop_budget} µs budget.{extra}",
                    "Significant overruns mean the autopilot is briefly 'blind' (no servo / "
                    "motor updates). At low airspeed this contributes to wing drop and "
                    "spiral departures. Primary fix: replace the SD card with a good "
                    "class-10 / A1 card and re-format it. Also lower LOG_BITMASK and any "
                    "high-rate MAVLink streams (SR0_*, SR1_*).")

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

    # ---------- Crash / incident detection ----------
    incidents = detect_incidents(parsed)
    if incidents:
        worst = max(incidents, key=lambda x: x["severity"])
        sev_label = {1: "Marginal", 2: "Marginal", 3: "Bad"}[worst["severity"]]
        sev_color = {1: WARN, 2: WARN, 3: DANGER}[worst["severity"]]
        # Attach the raw list so the UI can render clickable rows
        items.append({
            "category": "Incidents detected",
            "verdict": sev_label, "color": sev_color,
            "headline": f"{len(incidents)} notable event(s) detected. Click any row below to jump to that moment on the PLOT tab.",
            "detail": "",
            "tip": TIPS.get("Incidents detected", ""),
            "events": incidents,
        })

    if not items:
        add("No data", "Info", TEXT_DIM,
            "Couldn't run the auto-review.",
            "Standard message types (VIBE, GPS, BAT, MAG, ERR) were not found in this log.")
    return items


def detect_incidents(parsed: dict) -> list[dict]:
    """Scan a parsed log for crash-like or anomaly events. Each event:
    {t: unix_seconds, title: short label, detail: explanation, severity: 1-3}."""
    data = parsed["data"]
    times = parsed["times"]
    events: list[dict] = []

    # 1. ERR messages — explicit subsystem errors logged by autopilot
    if "ERR" in data and "ERR" in times:
        et = np.asarray(times["ERR"], dtype=float)
        subs = data["ERR"].get("Subsys", [])
        codes = data["ERR"].get("ECode", [])
        for i in range(len(et)):
            sub = subs[i] if i < len(subs) else "?"
            code = codes[i] if i < len(codes) else "?"
            if int(code) == 0:
                continue  # 0 = subsystem recovered/cleared
            events.append({
                "t": float(et[i]),
                "title": f"ERR Subsys={sub}",
                "detail": f"Autopilot logged error code {code} on subsystem {sub}",
                "severity": 3,
            })

    # 2. Sudden attitude excursion (>60° roll or pitch)
    if "ATT" in data and "Roll" in data["ATT"] and "Pitch" in data["ATT"]:
        roll = np.asarray(data["ATT"]["Roll"], dtype=float)
        pitch = np.asarray(data["ATT"]["Pitch"], dtype=float)
        att_t = np.asarray(times.get("ATT", []), dtype=float)
        big = np.where((np.abs(roll) > 60) | (np.abs(pitch) > 60))[0]
        if len(big) > 0 and len(att_t) == len(roll):
            # Cluster into one event per ~2 sec
            last_t = -1e18
            for idx in big:
                t = float(att_t[idx])
                if t - last_t > 2.0:
                    events.append({
                        "t": t,
                        "title": "Extreme tilt",
                        "detail": f"Roll/pitch exceeded 60° (R={roll[idx]:.0f}°, P={pitch[idx]:.0f}°)",
                        "severity": 3,
                    })
                    last_t = t

    # 3. Rapid altitude drop (descent > 12 m/s sustained for >0.5s)
    if "POS" in data and "Alt" in data["POS"]:
        alt = np.asarray(data["POS"]["Alt"], dtype=float)
        pt = np.asarray(times.get("POS", []), dtype=float)
        if len(pt) == len(alt) and len(pt) > 4:
            dt = np.diff(pt)
            dz = np.diff(alt)
            with np.errstate(divide="ignore", invalid="ignore"):
                vz = np.where(dt > 0, dz / dt, 0)
            big = np.where(vz < -12)[0]
            last_t = -1e18
            for idx in big:
                t = float(pt[idx + 1])
                if t - last_t > 1.5:
                    events.append({
                        "t": t,
                        "title": "Rapid descent",
                        "detail": f"Vertical speed reached {vz[idx]:.1f} m/s (≈free-fall threshold)",
                        "severity": 3,
                    })
                    last_t = t

    # 4. Battery low (per-cell estimate < 3.3V under load)
    bat = None
    for k in ("BAT", "BAT1", "BATT"):
        if k in data and "Volt" in data[k]:
            bat = (k, data[k]); break
    if bat:
        bt = np.asarray(times.get(bat[0], []), dtype=float)
        v = np.asarray(bat[1]["Volt"], dtype=float)
        if len(bt) == len(v) and len(v) > 5:
            v_start = float(np.median(v[: max(1, len(v) // 20)]))
            cells = round(v_start / 3.85) if v_start > 5 else 0
            if cells:
                per_cell = v / cells
                low = np.where(per_cell < 3.3)[0]
                if len(low) > 0:
                    events.append({
                        "t": float(bt[low[0]]),
                        "title": "Battery critical",
                        "detail": f"Per-cell voltage dropped below 3.3V ({per_cell[low[0]]:.2f}V/cell)",
                        "severity": 2,
                    })

    # 5. EKF failsafe innovations (>1.0)
    xkf = data.get("XKF4") or data.get("NKF4")
    xkf_key = "XKF4" if "XKF4" in data else ("NKF4" if "NKF4" in data else None)
    if xkf and xkf_key and "SV" in xkf and "SP" in xkf and xkf_key in times:
        xt = np.asarray(times[xkf_key], dtype=float)
        sv = np.asarray(xkf["SV"], dtype=float)
        sp = np.asarray(xkf["SP"], dtype=float)
        if len(xt) == len(sv):
            bad = np.where((sv > 1.0) | (sp > 1.0))[0]
            if len(bad) > 0:
                events.append({
                    "t": float(xt[bad[0]]),
                    "title": "EKF stress",
                    "detail": f"EKF innovation peaked above 1.0 (loss-of-fix or sensor disagreement)",
                    "severity": 2,
                })

    # 6. RC failsafe (RCIN.C1 < 900)
    if "RCIN" in data and "C1" in data["RCIN"]:
        c1 = np.asarray(data["RCIN"]["C1"], dtype=float)
        rt = np.asarray(times.get("RCIN", []), dtype=float)
        bad = np.where(c1 < 900)[0]
        if len(rt) == len(c1) and len(bad) > 0:
            events.append({
                "t": float(rt[bad[0]]),
                "title": "RC failsafe",
                "detail": f"RC signal dropped to failsafe level ({int(c1[bad[0]])} µs)",
                "severity": 2,
            })

    events.sort(key=lambda e: e["t"])
    return events


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
        path_lower = self.path.lower()
        try:
            if path_lower.endswith(".tlog") or path_lower.endswith(".log"):
                # MAVLink telemetry log (ground-station recorded). pymavlink's
                # mavutil auto-detects MAVLink versions.
                from pymavlink import mavutil
                mlog = mavutil.mavlink_connection(
                    self.path, dialect="ardupilotmega", robust_parsing=True
                )
            else:
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
    """X axis that displays elapsed seconds (small range, fast) as Istanbul
    wall-clock time. Pass `t_start` (Unix epoch) so labels show real time."""
    def __init__(self, *args, t_start: float = 0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._t_start = float(t_start)

    def set_t_start(self, t_start: float):
        self._t_start = float(t_start)
        self.picture = None  # invalidate cache
        self.update()

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            try:
                dt = datetime.fromtimestamp(float(v) + self._t_start, tz=ISTANBUL_TZ)
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
        self.time_axis = IstanbulTimeAxis(orientation="bottom")
        super().__init__(parent, axisItems={"bottom": self.time_axis})
        self.status_label = status_label
        self._t_start = 0.0
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(ACCENT, width=1, style=Qt.PenStyle.DashLine))
        self.addItem(self.vline, ignoreBounds=True)
        self.vline.hide()
        self.scene().sigMouseMoved.connect(self._on_mouse)
        # Right-click → emit signal with the x position of the click
        self.scene().sigMouseClicked.connect(self._on_click)
        self._last_mouse_x = 0.0
        self.annotation_requested = None  # callback(x_relative_seconds)

    def _on_click(self, ev):
        try:
            from PyQt6.QtCore import Qt as _Qt
            if ev.button() == _Qt.MouseButton.RightButton and callable(self.annotation_requested):
                view_pos = self.plotItem.vb.mapSceneToView(ev.scenePos())
                self.annotation_requested(float(view_pos.x()))
                ev.accept()
        except Exception:
            pass

    def set_t_start(self, t_start: float):
        self._t_start = float(t_start)
        self.time_axis.set_t_start(t_start)

    def _on_mouse(self, pos):
        if not self.sceneBoundingRect().contains(pos):
            return
        view = self.plotItem.vb.mapSceneToView(pos)
        x, y = view.x(), view.y()
        self._last_mouse_x = float(x)
        self.vline.setPos(x)
        self.vline.show()
        # x is relative seconds — add t_start for wall-clock display
        self.status_label.setText(
            f"◇   {fmt_istanbul(x + self._t_start, with_date=False)}  {TZ_LABEL}     y = {y:0.4f}"
        )


class PreferencesDialog(QtWidgets.QDialog):
    """Settings panel — currently a timezone picker."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(420)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QtWidgets.QLabel("PREFERENCES")
        title.setStyleSheet(
            f"color:{TEXT}; font-size:13px; font-weight:700; letter-spacing:3px;"
        )
        layout.addWidget(title)

        tz_label = QtWidgets.QLabel("DISPLAY TIMEZONE")
        tz_label.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; font-weight:700; letter-spacing:2px;"
        )
        layout.addWidget(tz_label)

        self.tz_combo = QtWidgets.QComboBox()
        for zone, label, desc in COMMON_TIMEZONES:
            self.tz_combo.addItem(f"{label}  ·  {desc}", userData=zone)
        # Pre-select the current one
        for i in range(self.tz_combo.count()):
            if self.tz_combo.itemData(i) == TZ_NAME:
                self.tz_combo.setCurrentIndex(i)
                break
        layout.addWidget(self.tz_combo)

        help_txt = QtWidgets.QLabel(
            "All timestamps shown in the app (plot axis, cockpit HUD, status bar, "
            "Info tab, etc.) will use this zone. Changes take effect immediately."
        )
        help_txt.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px;")
        help_txt.setWordWrap(True)
        layout.addWidget(help_txt)

        layout.addStretch(1)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QtWidgets.QPushButton("Apply")
        ok.setObjectName("primary")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self.accept)
        ok.setDefault(True)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def selected_timezone(self) -> str:
        return self.tz_combo.currentData()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UAV Log Viewer")
        # Sensible bounds: must be at least readable, but allow the user to
        # shrink the window for split-screen work. Initial size only matters
        # if the OS can't maximize (we call showMaximized() at startup).
        self.setMinimumSize(960, 600)
        self.resize(1500, 950)

        self.parsed: dict | None = None
        self.curves: dict[tuple[str, str], pg.PlotDataItem] = {}
        self.color_idx = 0
        self.worker: LogParseWorker | None = None
        self.config: dict = self._load_config()
        # Apply saved timezone (if any) before building UI
        tz_name = self.config.get("timezone")
        if tz_name:
            _apply_timezone(tz_name)
        self.recent_files: list[str] = self._load_recent_files()
        self.comparison: dict | None = None
        self.comparison_curves: dict[tuple[str, str], pg.PlotDataItem] = {}
        self._cmp_worker: LogParseWorker | None = None
        self.annotations: list[dict] = []
        self._annotation_items: list = []

        self._build_menu()
        self._build_ui()
        # Drag-and-drop a .bin/.tlog/.log onto the window to open it
        self.setAcceptDrops(True)
        # Restore window position/size/splitter/tab from the previous session
        self._restore_window_state()

    def changeEvent(self, event: QtCore.QEvent):
        """When the window is minimized/maximized/restored, QWebEngineView
        contents (Map, 3D, Cockpit) sometimes go blank until forced to
        re-paint. Force a repaint after every window-state change."""
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            QtCore.QTimer.singleShot(50, self._refresh_web_views)

    def resizeEvent(self, event):
        """Same fix as changeEvent — drag-resizing also blanks WebEngine
        on some macOS / Qt versions."""
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._refresh_web_views)

    def _refresh_web_views(self):
        for attr in ("map_view", "view3d", "instruments_view"):
            v = getattr(self, attr, None)
            if v is not None:
                try:
                    v.update()
                    v.repaint()
                except Exception:
                    pass

    # ----- Window state persistence -----
    def _restore_window_state(self):
        # We always start maximized at launch (see __main__), so do NOT call
        # restoreGeometry here — that used to clobber the maximized state
        # with the previous session's window size. Splitter sizes and last
        # tab are still restored, since those are layout state inside the
        # maximized window.
        sizes = self.config.get("splitter_sizes")
        if isinstance(sizes, list) and len(sizes) == 2:
            try:
                self.splitter.setSizes([int(x) for x in sizes])
            except Exception:
                pass
        tab_idx = self.config.get("last_tab")
        if isinstance(tab_idx, int) and 0 <= tab_idx < self.tabs.count():
            self.tabs.setCurrentIndex(tab_idx)

    # ----- Plot annotations (right-click on plot) -----
    def _on_annotation_request(self, x_rel: float):
        text, ok = QtWidgets.QInputDialog.getText(
            self, "Add annotation",
            f"Label for {fmt_istanbul((self.parsed.get('t_start') or 0) + x_rel) if self.parsed else f'{x_rel:.1f}s'}:")
        if not ok or not text.strip():
            return
        self.annotations.append({"x": float(x_rel), "label": text.strip()})
        self._save_annotations_for_current_log()
        self._render_annotations()

    def _render_annotations(self):
        # Remove any prior annotation items
        for it in getattr(self, "_annotation_items", []):
            try: self.plot.removeItem(it)
            except Exception: pass
        self._annotation_items = []
        for a in self.annotations:
            line = pg.InfiniteLine(
                pos=a["x"], angle=90, movable=False,
                pen=pg.mkPen(ACCENT_2, width=1.2, style=Qt.PenStyle.DashLine),
                label=a["label"],
                labelOpts={"position": 0.05, "color": ACCENT_2,
                           "fill": pg.mkBrush(BG_2), "movable": False},
            )
            self.plot.addItem(line, ignoreBounds=True)
            self._annotation_items.append(line)

    def _annotations_key(self) -> str | None:
        if self.parsed is None:
            return None
        return str(Path(self.parsed["path"]).resolve())

    def _load_annotations_for_current_log(self):
        self.annotations = []
        key = self._annotations_key()
        if not key:
            return
        store = self.config.get("annotations", {})
        items = store.get(key, [])
        if isinstance(items, list):
            self.annotations = [a for a in items if isinstance(a, dict)
                                and "x" in a and "label" in a]

    def _save_annotations_for_current_log(self):
        key = self._annotations_key()
        if not key:
            return
        store = self.config.setdefault("annotations", {})
        store[key] = self.annotations
        # Cap at 200 most-recent annotated logs in the config
        if len(store) > 200:
            for k in list(store.keys())[:-200]:
                store.pop(k, None)
        self._save_config()

    def clear_annotations(self):
        if not self.annotations:
            return
        if QtWidgets.QMessageBox.question(
            self, "Clear annotations",
            f"Remove all {len(self.annotations)} annotation(s) for this log?",
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.annotations = []
        self._save_annotations_for_current_log()
        self._render_annotations()

    # ----- Jump-to-time (incident click) -----
    def _jump_to_time(self, unix_t: float):
        if self.parsed is None:
            return
        t_start = self.parsed.get("t_start") or 0.0
        rel = float(unix_t) - t_start
        # Switch to the PLOT tab
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).strip().upper() == "PLOT":
                self.tabs.setCurrentIndex(i)
                break
        # Zoom the plot to ±10s around the event
        try:
            self.plot.setXRange(rel - 10, rel + 10, padding=0)
        except Exception:
            pass
        # Drop a vertical marker line at the event
        if not hasattr(self, "_incident_marker"):
            self._incident_marker = None
        if self._incident_marker is not None:
            try: self.plot.removeItem(self._incident_marker)
            except Exception: pass
        self._incident_marker = pg.InfiniteLine(
            pos=rel, angle=90,
            pen=pg.mkPen("#f87171", width=2, style=Qt.PenStyle.DashLine),
            label="incident",
            labelOpts={"position": 0.95, "color": "#f87171", "fill": pg.mkBrush(BG_2)},
        )
        self.plot.addItem(self._incident_marker, ignoreBounds=True)
        self.statusBar().showMessage(
            f"Jumped to {fmt_istanbul(unix_t, with_date=True)} {TZ_LABEL}")
        # Also tell the master timeline so the other tabs follow
        try:
            self.master_t = max(0.0, min(rel, float(self.parsed.get("duration", 0))))
            self._master_push()
        except Exception:
            pass

    # ----- Welcome -----
    def show_welcome(self):
        if hasattr(self, "stacked"):
            self._refresh_welcome_recents()
            self.stacked.setCurrentIndex(0)

    # ----- Preferences -----
    def open_preferences(self):
        dlg = PreferencesDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            new_zone = dlg.selected_timezone()
            if new_zone and new_zone != TZ_NAME:
                _apply_timezone(new_zone)
                self.config["timezone"] = new_zone
                self._save_config()
                # Re-render everything that has time-formatted strings baked in
                if self.parsed is not None:
                    self._on_parsed(self.parsed)
                self.statusBar().showMessage(
                    f"Timezone changed to {new_zone} ({TZ_LABEL})."
                )

    def closeEvent(self, e):
        try:
            self.config["window_geometry"] = bytes(self.saveGeometry().toHex()).decode("ascii")
            self.config["splitter_sizes"] = self.splitter.sizes()
            self.config["last_tab"] = self.tabs.currentIndex()
            self.config["timezone"] = TZ_NAME
            self._save_config()
        except Exception:
            pass
        super().closeEvent(e)

    # ----- Drag and drop -----
    @staticmethod
    def _is_log_path(p: str) -> bool:
        return bool(p) and p.lower().endswith((".bin", ".tlog", ".log"))

    def dragEnterEvent(self, e: QtGui.QDragEnterEvent):
        # Be permissive — accept any URL-bearing drag, validate at drop time
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e: QtGui.QDragMoveEvent):
        # Required so the cursor keeps showing "accept" while hovering
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e: QtGui.QDropEvent):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if self._is_log_path(p):
                self.load_file(p)
                e.acceptProposedAction()
                return
        e.ignore()

    # macOS Finder "Open With…" / drag-onto-Dock-icon → QFileOpenEvent
    def event(self, ev):
        if ev.type() == QtCore.QEvent.Type.FileOpen:
            p = ev.file()
            if self._is_log_path(p):
                self.load_file(p)
                return True
        return super().event(ev)

    # ----- UI -----
    def _build_menu(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        open_act = QtGui.QAction("&Open log…", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self.open_file)
        file_menu.addAction(open_act)

        self.recent_menu = file_menu.addMenu("Open &Recent")
        self._rebuild_recent_menu()

        file_menu.addSeparator()
        compare_act = QtGui.QAction("Load &comparison log…", self)
        compare_act.setShortcut("Ctrl+Shift+O")
        compare_act.triggered.connect(self.open_comparison_file)
        file_menu.addAction(compare_act)
        clear_cmp_act = QtGui.QAction("Clear comparison overlay", self)
        clear_cmp_act.triggered.connect(self.clear_comparison)
        file_menu.addAction(clear_cmp_act)

        file_menu.addSeparator()
        report_act = QtGui.QAction("Export flight &report (PDF)…", self)
        report_act.setShortcut("Ctrl+R")
        report_act.triggered.connect(self.export_pdf_report)
        file_menu.addAction(report_act)
        csv_act = QtGui.QAction("Export plotted &series to CSV…", self)
        csv_act.triggered.connect(self.export_plot_csv)
        file_menu.addAction(csv_act)
        png_act = QtGui.QAction("Save plot as &image (PNG)…", self)
        png_act.triggered.connect(self.export_plot_png)
        file_menu.addAction(png_act)

        file_menu.addSeparator()
        quit_act = QtGui.QAction("&Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        view_menu = bar.addMenu("&View")
        welcome_act = QtGui.QAction("Back to &welcome screen", self)
        welcome_act.triggered.connect(self.show_welcome)
        view_menu.addAction(welcome_act)
        view_menu.addSeparator()
        clear_act = QtGui.QAction("Clear plot", self)
        clear_act.triggered.connect(self.clear_plot)
        view_menu.addAction(clear_act)

        clear_ann_act = QtGui.QAction("Clear &annotations on this log", self)
        clear_ann_act.triggered.connect(self.clear_annotations)
        view_menu.addAction(clear_ann_act)

        view_menu.addSeparator()
        prefs_act = QtGui.QAction("&Preferences…", self)
        prefs_act.setShortcut("Ctrl+,")
        prefs_act.triggered.connect(self.open_preferences)
        view_menu.addAction(prefs_act)

    # ----- Persistent config (recent files, window state, timezone) -----
    @staticmethod
    def _config_path() -> Path:
        return Path.home() / ".uav_log_viewer.json"

    def _load_config(self) -> dict:
        # Migrate old recent-only file if present and the new config isn't there yet
        p = self._config_path()
        if not p.exists():
            old = Path.home() / ".uav_log_viewer_recent.json"
            if old.exists():
                try:
                    with open(old) as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        return {"recent": [str(x) for x in data]}
                except Exception:
                    pass
            return {}
        try:
            with open(p) as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save_config(self):
        try:
            with open(self._config_path(), "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def _load_recent_files(self) -> list[str]:
        items = self.config.get("recent", [])
        return [str(x) for x in items if isinstance(x, str) and Path(x).exists()][:10]

    def _push_recent(self, path: str):
        p = str(Path(path).resolve())
        if p in self.recent_files:
            self.recent_files.remove(p)
        self.recent_files.insert(0, p)
        self.recent_files = self.recent_files[:10]
        self.config["recent"] = self.recent_files
        self._save_config()
        self._rebuild_recent_menu()
        self._refresh_welcome_recents()

    def _rebuild_recent_menu(self):
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        if not self.recent_files:
            empty = QtGui.QAction("(no recent files)", self)
            empty.setEnabled(False)
            self.recent_menu.addAction(empty)
            return
        for path in self.recent_files:
            short = Path(path).name
            act = QtGui.QAction(short, self)
            act.setToolTip(path)
            act.triggered.connect(lambda checked=False, p=path: self.load_file(p))
            self.recent_menu.addAction(act)
        self.recent_menu.addSeparator()
        clear = QtGui.QAction("Clear list", self)
        clear.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear)

    def _clear_recent(self):
        self.recent_files = []
        self._save_recent_files()
        self._rebuild_recent_menu()

    # ----- Compare two logs (overlay) -----
    def open_comparison_file(self):
        if self.parsed is None:
            QtWidgets.QMessageBox.information(
                self, "No base log",
                "Load a primary log first, then add a comparison.")
            return
        start_dir = self.config.get("last_open_dir") or str(Path(__file__).parent)
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open comparison log", start_dir,
            "All files (*);;Flight logs (*.bin *.tlog *.log)"
        )
        if not path:
            return
        try:
            self.config["last_open_dir"] = str(Path(path).parent)
            self._save_config()
        except Exception:
            pass
        if hasattr(self, "_cmp_worker") and self._cmp_worker and self._cmp_worker.isRunning():
            return
        self.statusBar().showMessage(f"Parsing comparison {Path(path).name}…")
        self._cmp_worker = LogParseWorker(path)
        self._cmp_worker.done.connect(self._on_comparison_parsed)
        self._cmp_worker.error.connect(lambda m: QtWidgets.QMessageBox.critical(
            self, "Comparison failed", m))
        self._cmp_worker.start()

    def _on_comparison_parsed(self, result: dict):
        self.comparison = result
        # Re-add overlays for every existing curve so user immediately sees the comparison
        existing = list(self.curves.keys())
        for key in existing:
            self._add_comparison_curve(*key)
        self.statusBar().showMessage(
            f"Comparison loaded: {Path(result['path']).name}  "
            f"({result['count']:,} msgs)  ·  dashed overlay = comparison"
        )

    def _add_comparison_curve(self, mtype: str, field: str):
        cmp_curves = getattr(self, "comparison_curves", {})
        if not cmp_curves and not hasattr(self, "comparison_curves"):
            self.comparison_curves = {}
            cmp_curves = self.comparison_curves
        key = (mtype, field)
        if key in self.comparison_curves:
            return
        cmp = getattr(self, "comparison", None)
        if cmp is None:
            return
        if mtype not in cmp["data"] or field not in cmp["data"][mtype]:
            return
        # Time-align: subtract comparison's t_start so both flights play from t=0
        t_start_cmp = cmp.get("t_start") or 0.0
        x = cmp["times"][mtype] - t_start_cmp
        y = cmp["data"][mtype][field]
        if len(x) == 0:
            return
        # Match the colour of the base curve and pair with a dashed pen so the
        # eye can tell at-a-glance which-is-which.
        base_curve = self.curves.get(key)
        col = WARN  # default amber
        if base_curve is not None:
            try:
                col = base_curve.opts.get("pen").color().name()
            except Exception:
                pass
        pen = pg.mkPen(color=col, width=1.6, style=Qt.PenStyle.DashLine)
        curve = self.plot.plot(x, y, pen=pen, name=f"{mtype}.{field} (cmp)")
        self.comparison_curves[key] = curve

    def _remove_comparison_curve(self, key):
        cmp_curves = getattr(self, "comparison_curves", {})
        c = cmp_curves.pop(key, None)
        if c is not None:
            self.plot.removeItem(c)
            self.plot.plotItem.legend.removeItem(c)

    def clear_comparison(self):
        cmp_curves = getattr(self, "comparison_curves", {})
        for k in list(cmp_curves.keys()):
            self._remove_comparison_curve(k)
        self.comparison = None
        self.statusBar().showMessage("Comparison overlay cleared.")

    # ----- Cross-tab sync (used by incident click-to-jump) -----
    def _master_push(self, emit_slider: bool = True):  # emit_slider kept for API compat
        """Push `self.master_t` to every web view that defines window.setPos()."""
        if self.parsed is None:
            return
        code = f"if (typeof window.setPos === 'function') window.setPos({self.master_t});"
        for v in (self.instruments_view, self.view3d, self.map_view):
            try:
                v.page().runJavaScript(code)
            except Exception:
                pass

    # ----- PDF flight report -----
    def export_pdf_report(self):
        if self.parsed is None:
            QtWidgets.QMessageBox.information(
                self, "No log loaded", "Open a flight log before exporting a report.")
            return
        suggested = Path(self.parsed["path"]).with_suffix(".pdf").name
        out, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save flight report", suggested, "PDF (*.pdf)"
        )
        if not out:
            return
        try:
            html = self._build_report_html()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Report failed", str(exc))
            return
        # Render to PDF via QTextDocument + QPrinter (no external deps)
        doc = QtGui.QTextDocument()
        doc.setHtml(html)
        printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QtPrintSupport.QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(out)
        printer.setPageMargins(QtCore.QMarginsF(18, 18, 18, 22),
                                QtGui.QPageLayout.Unit.Millimeter)
        doc.print(printer)
        self.statusBar().showMessage(f"Report saved → {out}")

    def _build_report_html(self) -> str:
        d = self.parsed
        name = Path(d["path"]).name
        start = fmt_istanbul(d["t_start"], with_date=True) if d.get("t_start") else "—"
        end   = fmt_istanbul(d["t_end"],   with_date=True) if d.get("t_end")   else "—"
        dur   = d.get("duration", 0)
        items = auto_review(d)
        incidents = detect_incidents(d)

        # Color tokens for HTML (PDF uses these directly)
        css = """
          body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #0b1220; }
          h1   { font-size: 22pt; margin: 0; letter-spacing: 3px; }
          h2   { font-size: 13pt; color: #0d7a8a; margin: 22px 0 8px;
                 letter-spacing: 2px; border-bottom: 1.5pt solid #0d7a8a;
                 padding-bottom: 4px; }
          .sub { color: #5a6678; font-size: 10pt; letter-spacing: 1px; margin-top:2px;}
          table { width: 100%; border-collapse: collapse; font-size: 10pt; }
          td   { padding: 4px 6px; vertical-align: top; }
          .meta td:first-child { color: #5a6678; width: 28%; font-weight: 600;
                                 letter-spacing: 1px; font-size: 9pt; }
          .card { border: 1pt solid #d6dde8; border-radius: 4pt; padding: 8pt 10pt;
                  margin-bottom: 6pt; }
          .card .cat { font-size: 11pt; font-weight: 700; }
          .card .verdict { float: right; font-size: 9pt; font-weight: 700;
                           letter-spacing: 1.5px; padding: 2pt 8pt; border-radius: 8pt;
                           color: white; }
          .vGood     { background: #15803d; }
          .vMarginal { background: #b45309; }
          .vBad      { background: #b91c1c; }
          .vInfo     { background: #0d7a8a; }
          .card .head { font-size: 10pt; margin-top: 4pt; }
          .card .det  { font-size: 9pt; color: #5a6678; margin-top: 2pt; }
          .footer { color:#5a6678; font-size:8pt; margin-top:20pt;
                    text-align:center; letter-spacing:2px; }
        """
        rows = []
        rows.append(f"<h1>◆ UAV FLIGHT REPORT</h1>")
        rows.append(f"<div class='sub'>{name}</div>")
        rows.append("<h2>SUMMARY</h2>")
        rows.append("<table class='meta'>"
                    f"<tr><td>FILE</td><td>{name}</td></tr>"
                    f"<tr><td>START ({TZ_LABEL})</td><td>{start}</td></tr>"
                    f"<tr><td>END ({TZ_LABEL})</td><td>{end}</td></tr>"
                    f"<tr><td>DURATION</td><td>{dur:0.1f} s ({dur/60:0.2f} min)</td></tr>"
                    f"<tr><td>MESSAGES</td><td>{d.get('count', 0):,}</td></tr>"
                    f"<tr><td>VEHICLE TYPE</td><td>{d.get('vehicle_type','—')}</td></tr>"
                    "</table>")
        # Mode timeline
        mode = d["data"].get("MODE")
        mode_t = d["times"].get("MODE")
        if mode and "Mode" in mode and mode_t is not None and len(mode_t):
            mfield = mode["Mode"]
            seen = []
            for t, m in zip(mode_t, mfield):
                if not seen or seen[-1][1] != m:
                    seen.append((float(t), m))
            rows.append("<h2>FLIGHT MODE TIMELINE</h2><table>")
            for t, m in seen:
                rows.append(f"<tr><td style='font-family:monospace;color:#5a6678;width:30%'>"
                            f"{fmt_istanbul(t)}</td><td><b>{m}</b></td></tr>")
            rows.append("</table>")
        # Auto review cards
        rows.append("<h2>HEALTH REVIEW</h2>")
        verdict_class = {"Good":"vGood","Marginal":"vMarginal","Bad":"vBad","Info":"vInfo"}
        for it in items:
            cls = verdict_class.get(it["verdict"], "vInfo")
            rows.append(
                f"<div class='card'>"
                f"<span class='verdict {cls}'>{it['verdict'].upper()}</span>"
                f"<div class='cat'>{it['category']}</div>"
                f"<div class='head'>{it['headline']}</div>"
                + (f"<div class='det'>{it['detail']}</div>" if it.get("detail") else "")
                + "</div>"
            )
        # Incidents
        if incidents:
            rows.append("<h2>INCIDENTS DETECTED</h2><table>")
            for ev in incidents:
                rows.append(
                    f"<tr><td style='font-family:monospace;color:#5a6678;width:25%'>"
                    f"{fmt_istanbul(ev['t'])}</td>"
                    f"<td><b>{ev['title']}</b><br>"
                    f"<span style='color:#5a6678;font-size:9pt'>{ev['detail']}</span></td></tr>"
                )
            rows.append("</table>")
        rows.append("<div class='footer'>UAV LOG VIEWER  ·  CREATED BY JAVID</div>")
        return f"<html><head><style>{css}</style></head><body>" + "".join(rows) + "</body></html>"

    # ----- PNG export of the plot -----
    def export_plot_png(self):
        if not self.curves:
            QtWidgets.QMessageBox.information(
                self, "Nothing to export",
                "Tick some fields on the PLOT tab first so there's something to render.")
            return
        suggested = "flight_plot.png"
        if self.parsed is not None:
            suggested = Path(self.parsed["path"]).with_suffix(".png").name
        out, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save plot as PNG", suggested, "PNG image (*.png)")
        if not out:
            return
        if not out.lower().endswith(".png"):
            out += ".png"
        try:
            from pyqtgraph.exporters import ImageExporter
            exporter = ImageExporter(self.plot.plotItem)
            # Export at a generous fixed width for crisp images
            exporter.parameters()["width"] = 1800
            exporter.export(out)
            self.statusBar().showMessage(f"Plot saved → {out}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "PNG export failed", str(exc))

    # ----- CSV export of plotted curves -----
    def export_plot_csv(self):
        if not self.curves:
            QtWidgets.QMessageBox.information(
                self, "Nothing to export", "Tick some fields on the PLOT tab first.")
            return
        out, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export plotted series to CSV", "flight_data.csv", "CSV (*.csv)"
        )
        if not out:
            return
        t_start = self.parsed.get("t_start") or 0.0 if self.parsed else 0.0
        # Build a union time grid by interpolation onto first curve's x
        # (cheap: write each curve as its own (time, value) pair set)
        try:
            with open(out, "w") as f:
                # Per-curve sections
                for (mtype, field), curve in self.curves.items():
                    f.write(f"# {mtype}.{field}\n")
                    f.write("time_iso,time_unix,seconds_since_start,value\n")
                    x = self.parsed["times"][mtype]
                    y = self.parsed["data"][mtype][field]
                    n = min(len(x), len(y))
                    for i in range(n):
                        tu = float(x[i])
                        iso = fmt_istanbul(tu, with_date=True)
                        f.write(f"{iso},{tu:.6f},{tu - t_start:.6f},{float(y[i])}\n")
                    f.write("\n")
            self.statusBar().showMessage(f"CSV saved → {out}  ({len(self.curves)} series)")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "CSV export failed", str(exc))

    def _build_ui(self):
        # Use a stacked widget: page 0 = welcome screen, page 1 = main UI.
        # The main UI is built immediately so that tabs/web views are warm
        # by the time the user opens their first log.
        self.stacked = QtWidgets.QStackedWidget()
        self.stacked.addWidget(self._build_welcome_page())  # index 0
        self._build_main_ui()  # populates page 1 via self._main_root
        self.stacked.addWidget(self._main_root)             # index 1
        self.setCentralWidget(self.stacked)
        self.stacked.setCurrentIndex(0)

    def _build_welcome_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(page)
        outer.setContentsMargins(40, 40, 40, 30)
        outer.setSpacing(0)
        outer.addStretch(1)

        # Logo / title block — title stays neutral (white), accent is reserved
        # for the single cyan focal point (the drop card).
        title_row = QtWidgets.QHBoxLayout()
        title_row.setSpacing(14)
        title_row.addStretch(1)
        logo_lbl = QtWidgets.QLabel("[ ◼ ]")
        logo_lbl.setStyleSheet(
            f"color:{ACCENT}; font-size:18px; font-weight:600; letter-spacing:2px;"
            f"font-family: 'JetBrains Mono', 'SF Mono', monospace;"
        )
        title_row.addWidget(logo_lbl)
        title_text_col = QtWidgets.QVBoxLayout()
        title_text_col.setSpacing(2)
        title = QtWidgets.QLabel("UAV LOG ANALYZER")
        title.setStyleSheet(
            f"color:{TEXT}; font-size:24px; font-weight:600; letter-spacing:4px;"
            f"font-family: 'Inter', 'Helvetica Neue', sans-serif;"
        )
        title_text_col.addWidget(title)
        sub = QtWidgets.QLabel("ARDUPILOT TELEMETRY DIAGNOSTIC TOOL")
        sub.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; letter-spacing:3px; font-weight:600;"
        )
        title_text_col.addWidget(sub)
        title_row.addLayout(title_text_col)
        title_row.addStretch(1)
        outer.addLayout(title_row)
        outer.addSpacing(46)

        # Drop card — cleaner, single focal point. Just an icon + text + hint.
        # No button or "or" divider inside; that just creates visual noise.
        self.welcome_drop = QtWidgets.QFrame()
        self.welcome_drop.setMinimumHeight(150)
        self.welcome_drop.setMinimumWidth(360)
        self.welcome_drop.setMaximumWidth(720)
        self.welcome_drop.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred)
        self.welcome_drop.setStyleSheet(
            f"QFrame {{"
            f"  background: {BG_1};"
            f"  border:1px dashed {BORDER};"
            f"  border-radius:2px;"
            f"}}"
        )
        dl = QtWidgets.QVBoxLayout(self.welcome_drop)
        dl.setContentsMargins(48, 36, 48, 36)
        dl.setSpacing(10)
        drop_icon = QtWidgets.QLabel("▼")
        drop_icon.setStyleSheet(
            f"color:{ACCENT}; font-size:28px; font-weight:400; line-height:1;"
        )
        drop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(drop_icon)
        drop_text = QtWidgets.QLabel("DROP FLIGHT LOG TO LOAD")
        drop_text.setStyleSheet(
            f"color:{TEXT}; font-size:13px; font-weight:600; letter-spacing:3px;"
        )
        drop_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(drop_text)
        drop_hint = QtWidgets.QLabel(".bin   ·   .tlog   ·   .log")
        drop_hint.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-weight:600; letter-spacing:3px;"
        )
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(drop_hint)

        wrap = QtWidgets.QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(self.welcome_drop)
        wrap.addStretch(1)
        outer.addLayout(wrap)
        outer.addSpacing(22)

        # Action row: Browse (primary), Preferences (secondary). Centered.
        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)
        browse_btn = QtWidgets.QPushButton("◉  BROWSE FOR A LOG")
        browse_btn.setObjectName("primary")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setMinimumHeight(42)
        browse_btn.setMinimumWidth(220)
        browse_btn.clicked.connect(self.open_file)
        actions.addWidget(browse_btn)
        pref_btn = QtWidgets.QPushButton("⚙  PREFERENCES")
        pref_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pref_btn.setMinimumHeight(42)
        pref_btn.clicked.connect(self.open_preferences)
        actions.addWidget(pref_btn)
        actions.addStretch(1)
        outer.addLayout(actions)
        outer.addSpacing(36)

        # Recent files — quiet, only the section header has a thin divider
        recent_wrap = QtWidgets.QHBoxLayout()
        recent_wrap.addStretch(1)
        recent_col = QtWidgets.QVBoxLayout()
        recent_col.setSpacing(6)
        recent_col.setContentsMargins(0, 0, 0, 0)
        self.welcome_recent_label = QtWidgets.QLabel("RECENT LOGS")
        self.welcome_recent_label.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; font-weight:700; letter-spacing:2.5px;"
            f"padding-bottom:4px; border-bottom:1px solid {BORDER};"
        )
        recent_col.addWidget(self.welcome_recent_label)
        self._welcome_recent_inner = recent_col
        recent_wrap.addLayout(recent_col)
        recent_wrap.addStretch(1)
        outer.addLayout(recent_wrap)
        outer.addStretch(2)

        # Footer credit + quit
        footer_row = QtWidgets.QHBoxLayout()
        footer_row.setContentsMargins(0, 12, 0, 0)
        quit_btn = QtWidgets.QPushButton("✕  QUIT")
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.clicked.connect(self.close)
        footer_row.addWidget(quit_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        footer_row.addStretch(1)
        credit = QtWidgets.QLabel(
            f"<span style='color:{TEXT_DIM};font-size:10px;letter-spacing:2px;font-weight:600;'>CREATED BY</span>"
            f"&nbsp;&nbsp;<span style='color:{ACCENT};font-size:14px;font-weight:800;letter-spacing:2px;'>JAVID</span>"
        )
        credit.setTextFormat(Qt.TextFormat.RichText)
        footer_row.addWidget(credit, alignment=Qt.AlignmentFlag.AlignRight)
        outer.addLayout(footer_row)

        self._refresh_welcome_recents()
        return page

    def _refresh_welcome_recents(self):
        # Rebuild the recent-files rows; keep the 'RECENT LOGS' header at the
        # top of the column.
        if not hasattr(self, "_welcome_recent_inner"):
            return
        layout = self._welcome_recent_inner
        # Remove every widget except the section header (index 0)
        while layout.count() > 1:
            it = layout.takeAt(1)
            w = it.widget()
            if w: w.deleteLater()
        if not self.recent_files:
            empty = QtWidgets.QLabel("(none yet — drop a log above)")
            empty.setStyleSheet(
                f"color:{TEXT_DIM}; font-size:11px; font-style:italic;"
                f"padding:6px 4px;"
            )
            layout.addWidget(empty)
            return
        for path in self.recent_files[:5]:
            short = Path(path).name
            row = QtWidgets.QPushButton(f"  {short}")
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setToolTip(path)
            row.setMinimumWidth(0)
            row.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed)
            row.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{TEXT_DIM};"
                f" border:none; padding:6px 4px; text-align:left;"
                f" font-family:'JetBrains Mono','SF Mono',Menlo,monospace;"
                f" font-size:12px; }}"
                f"QPushButton:hover {{ color:{ACCENT}; }}"
            )
            row.clicked.connect(lambda checked=False, p=path: self.load_file(p))
            layout.addWidget(row)

    def _build_main_ui(self):
        """Build the original tabbed UI; stored as self._main_root (a QWidget)."""
        # Root container with header on top, splitter below
        root = QtWidgets.QWidget()
        self._main_root = root
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Header bar ---
        header = QtWidgets.QFrame()
        header.setObjectName("header")
        header.setStyleSheet(
            f"QFrame#header {{ background:{BG_1}; "
            f"border-bottom: 1px solid {BORDER}; }}"
        )
        header.setFixedHeight(64)
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
            f"color:{TEXT}; font-size:18px; font-weight:900; letter-spacing:4px;"
            f"font-family: 'Inter Display', 'Inter', 'Helvetica Neue', sans-serif;"
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

        # Telemetry summary chip — must be allowed to shrink so the
        # right-hand action buttons stay visible on narrow windows.
        self.header_summary = QtWidgets.QLabel("no log loaded")
        self.header_summary.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; padding:6px 12px;"
            f"background:{BG_2}; border:1px solid {BORDER}; border-radius:2px;"
            f"font-family: 'JetBrains Mono', 'SF Mono', Menlo, monospace;"
        )
        self.header_summary.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred)
        self.header_summary.setMinimumWidth(0)
        h.addWidget(self.header_summary, 1)

        # Prominent credit badge in the header
        credit_badge = QtWidgets.QLabel(
            f"<span style='color:{TEXT_DIM};font-size:10px;letter-spacing:2px;font-weight:600;'>CREATED BY</span>"
            f"&nbsp;&nbsp;<span style='color:{ACCENT};font-size:18px;font-weight:900;letter-spacing:2px;"
            f"font-family:Inter Display,Inter,Helvetica Neue,sans-serif;'>JAVID</span>"
        )
        credit_badge.setTextFormat(Qt.TextFormat.RichText)
        credit_badge.setStyleSheet(
            f"padding:8px 14px;"
            f"background:{BG_2};"
            f"border:1px solid {BORDER}; border-radius:2px;"
        )
        h.addWidget(credit_badge)

        # Export PDF report button — same row, distinct violet accent
        self.export_btn = QtWidgets.QPushButton("⎙  EXPORT PDF")
        self.export_btn.setObjectName("violet")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setMinimumHeight(38)
        self.export_btn.setToolTip(
            "Save a one-page flight report (Auto Review + mode timeline + incidents) as PDF.")
        self.export_btn.clicked.connect(self.export_pdf_report)
        h.addWidget(self.export_btn)

        # Preferences gear — always visible in the header so it's discoverable
        self.prefs_btn = QtWidgets.QPushButton("⚙")
        self.prefs_btn.setObjectName("icon")
        self.prefs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prefs_btn.setMinimumHeight(38)
        self.prefs_btn.setMinimumWidth(42)
        self.prefs_btn.setToolTip("Preferences (timezone, etc.) — ⌘,")
        self.prefs_btn.clicked.connect(self.open_preferences)
        h.addWidget(self.prefs_btn)

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

        # Master playback bar removed — each tab has its own play controls.
        # We keep a master time variable so incident-click can still sync
        # the cockpit/3D/map views via runJavaScript(setPos).
        self.master_t = 0.0
        self.master_playing = False

        # --- Body splitter ---
        self.splitter = splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
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
        self.search.setPlaceholderText("Filter messages or fields…")
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
            f"font-family: 'JetBrains Mono', 'SF Mono', Menlo, Monaco, Consolas, monospace; font-size:11px;"
        )
        self.plot = CrosshairPlot(self.cursor_label)
        self.plot.annotation_requested = self._on_annotation_request
        # Performance: only render the visible window, and downsample with
        # peak-preserving mode so dense curves don't drown the GPU/CPU.
        # Without these, a single 3,500-point antialiased curve can take
        # nearly a second to paint per redraw on macOS.
        self.plot.setClipToView(True)
        self.plot.setDownsampling(auto=True, mode="peak")
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
        self.tabs.addTab(plot_container, "  PLOT  ")

        # Map tab
        self.map_view = QWebEngineView()
        self.map_view.loadFinished.connect(self._on_map_loaded)
        self._set_map_coords([])
        self.tabs.addTab(self.map_view, "  MAP  ")

        # 3D tab (Plotly via WebEngine — same tech as the map, no GL conflict)
        self.view3d = QWebEngineView()
        self.view3d.loadFinished.connect(self._on_3d_loaded)
        self._set_3d_points(None)
        self.tabs.addTab(self.view3d, "  3D  ")

        # FFT vibration tab — three stacked spectrum plots
        fft_container = QtWidgets.QWidget()
        fft_layout = QtWidgets.QVBoxLayout(fft_container)
        fft_layout.setContentsMargins(8, 8, 8, 8)
        fft_layout.setSpacing(6)
        fft_header = QtWidgets.QLabel("VIBRATION FREQUENCY SPECTRUM")
        fft_header.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-weight:700;"
            f"letter-spacing:2px; padding:4px 6px;"
        )
        fft_layout.addWidget(fft_header)
        self.fft_info = QtWidgets.QLabel(
            "  Open a log with IMU messages to see motor / airframe resonance peaks.")
        self.fft_info.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; padding:4px 10px;"
            f"background:{BG_2}; border:1px solid {BORDER}; border-radius:6px;"
            f"font-family: 'JetBrains Mono', monospace;"
        )
        fft_layout.addWidget(self.fft_info)
        self.fft_plots = []
        for axis in ("X", "Y", "Z"):
            p = pg.PlotWidget()
            p.setBackground(BG_1)
            p.showGrid(x=True, y=True, alpha=0.15)
            p.setLabel("bottom", f"Frequency · {axis} axis", units="Hz", color=TEXT_DIM)
            p.setLabel("left", "Magnitude (m/s²)", color=TEXT_DIM)
            p.setClipToView(True)
            p.setDownsampling(auto=True, mode="peak")
            for ax in ("left", "bottom"):
                a = p.getAxis(ax)
                a.setPen(pg.mkPen(BORDER))
                a.setTextPen(pg.mkPen(TEXT_DIM))
            self.fft_plots.append(p)
            fft_layout.addWidget(p, 1)

        # ---- Spectrogram (FFT over time) under the three spectra ----
        spec_header = QtWidgets.QLabel("SPECTROGRAM · FFT MAGNITUDE OVER TIME (PRIMARY IMU, |AccX|+|AccY|+|AccZ|)")
        spec_header.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-weight:700;"
            f"letter-spacing:2px; padding:10px 6px 2px;"
        )
        fft_layout.addWidget(spec_header)
        self.spectrogram_plot = pg.PlotWidget()
        self.spectrogram_plot.setBackground(BG_1)
        self.spectrogram_plot.setLabel("bottom", "Time", color=TEXT_DIM)
        self.spectrogram_plot.setLabel("left", "Frequency (Hz)", color=TEXT_DIM)
        for ax in ("left", "bottom"):
            a = self.spectrogram_plot.getAxis(ax)
            a.setPen(pg.mkPen(BORDER))
            a.setTextPen(pg.mkPen(TEXT_DIM))
        self.spectrogram_image = pg.ImageItem()
        # Custom colormap: dark navy → cyan → violet → amber (matches app palette)
        cmap_stops = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        cmap_colors = np.array([
            [11,  18,  32,  255],   # BG_0 (dark navy)
            [34,  211, 238, 255],   # cyan
            [167, 139, 250, 255],   # violet
            [251, 191, 36,  255],   # amber
            [248, 113, 113, 255],   # red
        ], dtype=np.uint8)
        self.spectrogram_image.setLookupTable(
            pg.ColorMap(cmap_stops, cmap_colors).getLookupTable(0, 1, 256)
        )
        self.spectrogram_plot.addItem(self.spectrogram_image)
        fft_layout.addWidget(self.spectrogram_plot, 2)

        self.tabs.addTab(fft_container, "  FFT  ")

        # PID tuning helper — desired vs actual Roll/Pitch/Yaw
        pid_container = QtWidgets.QWidget()
        pid_layout = QtWidgets.QVBoxLayout(pid_container)
        pid_layout.setContentsMargins(8, 8, 8, 8)
        pid_layout.setSpacing(6)
        pid_header = QtWidgets.QLabel("PID TUNING · DESIRED VS ACTUAL ATTITUDE")
        pid_header.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-weight:700;"
            f"letter-spacing:2px; padding:4px 6px;"
        )
        pid_layout.addWidget(pid_header)
        self.pid_info = QtWidgets.QLabel(
            "  Open a log with ATT messages to compare commanded vs actual attitude.")
        self.pid_info.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; padding:4px 10px;"
            f"background:{BG_2}; border:1px solid {BORDER}; border-radius:6px;"
            f"font-family: 'JetBrains Mono', monospace;"
        )
        pid_layout.addWidget(self.pid_info)
        self.pid_plots = []
        for axis in ("ROLL", "PITCH", "YAW"):
            p = pg.PlotWidget(axisItems={"bottom": IstanbulTimeAxis(orientation="bottom")})
            p.setBackground(BG_1)
            p.showGrid(x=True, y=True, alpha=0.15)
            p.setLabel("bottom", f"{axis}", color=TEXT_DIM)
            p.setLabel("left", "deg", color=TEXT_DIM)
            p.setClipToView(True)
            p.setDownsampling(auto=True, mode="peak")
            for ax in ("left", "bottom"):
                a = p.getAxis(ax); a.setPen(pg.mkPen(BORDER)); a.setTextPen(pg.mkPen(TEXT_DIM))
            p.addLegend(brush=pg.mkBrush(BG_2), pen=pg.mkPen(BORDER), labelTextColor=TEXT)
            self.pid_plots.append(p)
            pid_layout.addWidget(p, 1)
        self.tabs.addTab(pid_container, "  PID TUNING  ")

        # Motors tab — per-motor PWM, balance, desync detection
        motors_container = QtWidgets.QWidget()
        motors_layout = QtWidgets.QVBoxLayout(motors_container)
        motors_layout.setContentsMargins(8, 8, 8, 8)
        motors_layout.setSpacing(6)
        motors_header = QtWidgets.QLabel("MOTORS · RCOU PWM PER CHANNEL · BALANCE · DESYNC EVENTS")
        motors_header.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-weight:700;"
            f"letter-spacing:2px; padding:4px 6px;"
        )
        motors_layout.addWidget(motors_header)
        self.motors_stats = QtWidgets.QLabel(
            "  Open a log with RCOU messages to see per-motor PWM analysis.")
        self.motors_stats.setStyleSheet(
            f"color:{TEXT}; font-size:11px; padding:8px 12px;"
            f"background:{BG_2}; border:1px solid {BORDER}; border-radius:6px;"
            f"font-family: 'JetBrains Mono', monospace;"
        )
        self.motors_stats.setTextFormat(Qt.TextFormat.RichText)
        motors_layout.addWidget(self.motors_stats)

        self.motors_plot = pg.PlotWidget(axisItems={"bottom": IstanbulTimeAxis(orientation="bottom")})
        self.motors_plot.setBackground(BG_1)
        self.motors_plot.showGrid(x=True, y=True, alpha=0.15)
        self.motors_plot.setLabel("bottom", "Time", color=TEXT_DIM)
        self.motors_plot.setLabel("left", "PWM (µs)", color=TEXT_DIM)
        self.motors_plot.setClipToView(True)
        self.motors_plot.setDownsampling(auto=True, mode="peak")
        for ax in ("left", "bottom"):
            a = self.motors_plot.getAxis(ax); a.setPen(pg.mkPen(BORDER)); a.setTextPen(pg.mkPen(TEXT_DIM))
        self.motors_plot.addLegend(brush=pg.mkBrush(BG_2), pen=pg.mkPen(BORDER), labelTextColor=TEXT)
        motors_layout.addWidget(self.motors_plot, 2)

        self.motors_events = QtWidgets.QLabel("")
        self.motors_events.setStyleSheet(
            f"color:{TEXT}; font-size:11px; padding:8px 12px;"
            f"background:{BG_2}; border:1px solid {BORDER}; border-radius:6px;"
            f"font-family: 'JetBrains Mono', monospace;"
        )
        self.motors_events.setTextFormat(Qt.TextFormat.RichText)
        self.motors_events.setWordWrap(True)
        motors_layout.addWidget(self.motors_events)

        self.tabs.addTab(motors_container, "  MOTORS  ")

        # Params tab — searchable list of all flight-controller parameters
        params_container = QtWidgets.QWidget()
        params_layout = QtWidgets.QVBoxLayout(params_container)
        params_layout.setContentsMargins(8, 8, 8, 8)
        params_layout.setSpacing(6)
        params_header = QtWidgets.QLabel("PARAMS · FLIGHT CONTROLLER PARAMETERS FROM THE LOG")
        params_header.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-weight:700;"
            f"letter-spacing:2px; padding:4px 6px;"
        )
        params_layout.addWidget(params_header)
        self.params_filter = QtWidgets.QLineEdit()
        self.params_filter.setPlaceholderText("Search parameters (e.g. TKOFF, COMPASS, ARSPD)…")
        self.params_filter.setStyleSheet(
            f"background:{BG_2}; border:1px solid {BORDER}; border-radius:6px;"
            f"padding:6px 10px; color:{TEXT}; font-family:'JetBrains Mono',monospace; font-size:12px;"
        )
        self.params_filter.textChanged.connect(self._filter_params)
        params_layout.addWidget(self.params_filter)
        self.params_table = QtWidgets.QTableWidget(0, 2)
        self.params_table.setHorizontalHeaderLabels(["NAME", "VALUE"])
        self.params_table.horizontalHeader().setStretchLastSection(True)
        self.params_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.params_table.verticalHeader().setVisible(False)
        self.params_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.params_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.params_table.setStyleSheet(
            f"QTableWidget {{ background:{BG_1}; border:1px solid {BORDER}; "
            f"color:{TEXT}; font-family:'JetBrains Mono',monospace; font-size:11px; "
            f"gridline-color:{BORDER}; }}"
            f"QHeaderView::section {{ background:{BG_2}; color:{TEXT_DIM}; "
            f"border:0; border-bottom:1px solid {BORDER}; padding:6px 10px; "
            f"font-weight:700; letter-spacing:1px; }}"
        )
        params_layout.addWidget(self.params_table, 1)
        self.params_status = QtWidgets.QLabel("")
        self.params_status.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; padding:4px 6px; "
            f"font-family:'JetBrains Mono',monospace;"
        )
        params_layout.addWidget(self.params_status)
        self.tabs.addTab(params_container, "  PARAMS  ")

        # Instruments tab (cockpit: attitude, heading, altitude, sticks)
        self.instruments_view = QWebEngineView()
        self.instruments_view.loadFinished.connect(self._on_instruments_loaded)
        self._set_instruments(None)
        self.tabs.addTab(self.instruments_view, "  COCKPIT  ")

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
        self.tabs.addTab(review_container, "  REVIEW  ")

        # Info tab
        self.info_text = QtWidgets.QPlainTextEdit()
        self.info_text.setReadOnly(True)
        self.tabs.addTab(self.info_text, "  INFO  ")

        rv.addWidget(self.tabs)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 1160])
        root_layout.addWidget(splitter, 1)

        # NOTE: don't call setCentralWidget here — _build_ui wraps this root
        # into a QStackedWidget alongside the welcome page.
        self.statusBar().showMessage("Drop a .bin log onto the window to begin")

    # ----- File loading -----
    def open_file(self):
        # Start in: (1) last-used folder, (2) most recent log's folder,
        # (3) ~/Desktop, (4) ~/Downloads, (5) the app's own folder
        start_dir = self.config.get("last_open_dir")
        if not start_dir or not Path(start_dir).is_dir():
            if self.recent_files:
                start_dir = str(Path(self.recent_files[0]).parent)
            else:
                for cand in (Path.home() / "Desktop", Path.home() / "Downloads",
                             Path(__file__).parent):
                    if cand.is_dir():
                        start_dir = str(cand); break
        # Permissive filter — All files first so nothing is greyed out
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open flight log", start_dir or "",
            "All files (*);;Flight logs (*.bin *.tlog *.log)"
        )
        if not path:
            return
        # Remember the folder for next time
        try:
            self.config["last_open_dir"] = str(Path(path).parent)
            self._save_config()
        except Exception:
            pass
        self.load_file(path)

    def load_file(self, path: str):
        if self.worker and self.worker.isRunning():
            return
        self.statusBar().showMessage(f"Parsing {Path(path).name}…")
        self.tree.clear()
        self.clear_plot()
        self.info_text.clear()
        self._push_recent(path)
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
        # Make the plot axis show wall-clock Istanbul time without losing
        # float precision (X values stay as small "seconds since log start").
        t0 = result.get("t_start") or 0.0
        self.plot.set_t_start(t0)
        for pid_plot in getattr(self, "pid_plots", []):
            ax = pid_plot.getAxis("bottom")
            if hasattr(ax, "set_t_start"):
                ax.set_t_start(t0)
        if hasattr(self, "motors_plot"):
            ax = self.motors_plot.getAxis("bottom")
            if hasattr(ax, "set_t_start"):
                ax.set_t_start(t0)
        # Reset cross-tab sync state (each tab has its own play controls)
        self.master_t = 0.0
        self.master_playing = False
        # Hide the welcome screen and show the main UI
        if hasattr(self, "stacked"):
            self.stacked.setCurrentIndex(1)
        name = Path(result["path"]).name
        start_txt = fmt_istanbul(result["t_start"], with_date=True) if result.get("t_start") else "—"
        msg = f"◉  LOG ACTIVE   ·   {name}   ·   {result['count']:,} MSGS   ·   {result['duration']:0.1f}s   ·   START {start_txt} {TZ_LABEL}"
        self.statusBar().showMessage(msg)
        self.header_summary.setText(
            f"<span style='color:{TEXT}'>{name}</span>"
            f"   ·   <span style='color:{ACCENT}'>{result['count']:,}</span> msgs"
            f"   ·   <span style='color:{ACCENT}'>{result['duration']:0.1f}s</span>"
            f"   ·   <span style='color:{TEXT_DIM}'>{start_txt} {TZ_LABEL}</span>"
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
        self._populate_instruments()
        self._populate_fft()
        self._populate_pid()
        self._populate_motors()
        self._populate_params()
        self._populate_review()
        # Restore any saved right-click annotations for this log
        self._load_annotations_for_current_log()
        self._render_annotations()

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
        # Subtract t_start so X values are small (~0–duration_sec). Plotting at
        # Unix-timestamp magnitudes (~1.7e9) is multi-second slow in pyqtgraph.
        t_start = self.parsed.get("t_start") or 0.0
        x = self.parsed["times"][mtype] - t_start
        y = self.parsed["data"][mtype][field]
        if len(x) == 0:
            return
        color = PLOT_COLORS[self.color_idx % len(PLOT_COLORS)]
        self.color_idx += 1
        pen = pg.mkPen(color=color, width=1.8)
        curve = self.plot.plot(x, y, pen=pen, name=f"{mtype}.{field}")
        self.curves[key] = curve
        self._update_plot_count()
        # If a comparison log is loaded, mirror this field as a dashed overlay
        if getattr(self, "comparison", None) is not None:
            self._add_comparison_curve(mtype, field)

    def _remove_curve(self, key: tuple[str, str]):
        curve = self.curves.pop(key, None)
        if curve is not None:
            self.plot.removeItem(curve)
            self.plot.plotItem.legend.removeItem(curve)
        # Also remove the matching comparison overlay if present
        self._remove_comparison_curve(key)
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
            lines.append(f"Start ({TZ_LABEL}):   {fmt_istanbul(d['t_start'], with_date=True)}")
            lines.append(f"End   ({TZ_LABEL}):   {fmt_istanbul(d['t_end'],   with_date=True)}")
        lines.append(f"Vehicle type: {d.get('vehicle_type')}")
        lines.append("")

        # Mode changes
        mode_msgs = d["data"].get("MODE")
        mode_times = d["times"].get("MODE")
        if mode_msgs is not None and mode_times is not None and len(mode_times):
            lines.append(f"Flight modes (local time, {TZ_LABEL}):")
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
            overall_color, overall_text = WARN, "Acceptable"
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
            ("marginal", n_marg, WARN),
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
            tip = it.get("tip", "")
            if tip:
                # Wrap long tooltip text to ~70 chars per line for readability
                import textwrap
                card.setToolTip(textwrap.fill(tip, width=72))
            v = QtWidgets.QVBoxLayout(card)
            v.setContentsMargins(16, 12, 16, 12)
            v.setSpacing(4)

            top = QtWidgets.QHBoxLayout()
            cat_lbl_txt = it["category"] + ("  ⓘ" if tip else "")
            cat = QtWidgets.QLabel(cat_lbl_txt)
            cat.setStyleSheet(
                f"color:{TEXT}; font-size:13px; font-weight:600; letter-spacing:0.3px;"
            )
            if tip:
                cat.setToolTip(textwrap.fill(tip, width=72))
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

            # Clickable incident rows — jump to PLOT at that moment
            events = it.get("events")
            if events:
                for ev in events[:20]:
                    row = QtWidgets.QPushButton(
                        f"  {fmt_istanbul(ev['t'])}   ◆   {ev['title']}   ·   {ev['detail']}"
                    )
                    row.setCursor(Qt.CursorShape.PointingHandCursor)
                    row.setStyleSheet(
                        f"QPushButton {{ background:{BG_1}; color:{TEXT};"
                        f" border:1px solid {BORDER}; border-left:3px solid {it['color']};"
                        f" border-radius:5px; padding:6px 10px; text-align:left;"
                        f" font-family:'JetBrains Mono','SF Mono',Menlo,monospace;"
                        f" font-size:11px; margin-top:4px; }}"
                        f"QPushButton:hover {{ background:{BG_3}; border-color:{it['color']}; color:{ACCENT}; }}"
                    )
                    row.clicked.connect(
                        lambda checked=False, t=float(ev["t"]): self._jump_to_time(t))
                    v.addWidget(row)
                if len(events) > 20:
                    more = QtWidgets.QLabel(f"  (+{len(events) - 20} more)")
                    more.setStyleSheet(f"color:{TEXT_DIM}; font-size:11px; padding-top:4px;")
                    v.addWidget(more)

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
            ts = np.asarray(self.parsed["times"].get(mt, []), dtype=float)
            if np.nanmax(np.abs(lats)) > 200:
                lats = lats / 1e7; lngs = lngs / 1e7
            mask = (np.abs(lats) > 0.0001) & (np.abs(lngs) > 0.0001)
            if mt.startswith("GPS"):
                if "Status" in block:
                    mask &= np.asarray(block["Status"], dtype=float) >= 3
                if "NSats" in block:
                    mask &= np.asarray(block["NSats"], dtype=float) >= 4
            lats = lats[mask]; lngs = lngs[mask]; alts = alts[mask]
            if len(ts) == len(mask):
                ts = ts[mask]
            else:
                ts = np.zeros_like(lats)
            if len(lats) >= 2:
                coords = (lats, lngs, alts, ts)
                break

        if coords is None:
            self._set_3d_points(None)
            return

        lats, lngs, alts, ts = coords
        lat0, lng0 = float(lats[0]), float(lngs[0])
        alt0 = float(alts[0])
        m_per_deg_lat = 111320.0
        m_per_deg_lng = 111320.0 * np.cos(np.radians(lat0))
        x = (lngs - lng0) * m_per_deg_lng     # East
        y = (lats - lat0) * m_per_deg_lat     # North
        z = alts - alt0                        # Altitude AGL

        if len(x) > 4000:
            step = len(x) // 4000
            x = x[::step]; y = y[::step]; z = z[::step]; ts = ts[::step]

        # Pre-format Istanbul wall-clock strings for each sample
        time_strs = [fmt_istanbul(float(t)) if t > 0 else "" for t in ts]
        t_rel = [float(t - ts[0]) if t > 0 else 0.0 for t in ts]

        self._set_3d_points({
            "x": [float(v) for v in x],
            "y": [float(v) for v in y],
            "z": [float(v) for v in z],
            "tstr": time_strs,
            "trel": t_rel,
        })

    def _set_3d_points(self, pts):
        html = PLOT3D_HTML_TEMPLATE.replace("__PTS__", json.dumps(pts) if pts else "null")
        html = html.replace("__TZLABEL__", TZ_LABEL)
        # Load airplane mesh (or fall back to "null" so JS uses a procedural shape)
        mesh_path = Path(__file__).parent / "airplane_mesh.json"
        if mesh_path.exists():
            with open(mesh_path, "r") as f:
                html = html.replace("__MESH__", f.read())
        else:
            html = html.replace("__MESH__", "null")
        self.view3d.setHtml(html, QtCore.QUrl("https://localhost/"))

    def _on_3d_loaded(self, ok: bool):
        if not ok:
            self.statusBar().showMessage("3D view failed to load.")

    # ----- Instruments tab -----
    def _populate_instruments(self):
        if self.parsed is None:
            self._set_instruments(None)
            return
        d = self.parsed["data"]
        t = self.parsed["times"]
        t_start = self.parsed.get("t_start") or 0.0
        t_end = self.parsed.get("t_end") or 0.0
        if t_end <= t_start:
            self._set_instruments(None)
            return

        # Dense timeline — 800 samples across the flight so interpolation has
        # plenty of waypoints (avoids the "teleport between frames" effect).
        N = 800
        timeline = np.linspace(t_start, t_end, N)

        def sample(mt, field, default=0.0):
            block = d.get(mt)
            times = t.get(mt)
            if not block or field not in block or times is None or len(times) == 0:
                return [default] * N
            ts = np.asarray(times, dtype=float)
            vs = np.asarray(block[field], dtype=float)
            order = np.argsort(ts)
            ts = ts[order]; vs = vs[order]
            return np.interp(timeline, ts, vs).tolist()

        # Attitude
        roll  = sample("ATT", "Roll", 0.0)
        pitch = sample("ATT", "Pitch", 0.0)
        yaw   = sample("ATT", "Yaw", 0.0)

        # Altitude — prefer BARO.Alt, fall back to POS.Alt
        if "BARO" in d and "Alt" in d["BARO"]:
            alt = sample("BARO", "Alt", 0.0)
        else:
            alt = sample("POS", "Alt", 0.0)
        # Make altitude relative to first sample
        if alt and alt[0] is not None:
            a0 = alt[0]
            alt = [a - a0 for a in alt]

        # Ground speed
        if "GPS" in d and "Spd" in d["GPS"]:
            spd = sample("GPS", "Spd", 0.0)
        else:
            spd = [0.0] * N

        # RC sticks (Mode 2 convention: C1=roll, C2=pitch, C3=throttle, C4=yaw)
        c1 = sample("RCIN", "C1", 1500.0)
        c2 = sample("RCIN", "C2", 1500.0)
        c3 = sample("RCIN", "C3", 1500.0)
        c4 = sample("RCIN", "C4", 1500.0)

        # Format Istanbul time strings + relative seconds
        tstr = [fmt_istanbul(float(ts_)) for ts_ in timeline]
        trel = [float(ts_ - t_start) for ts_ in timeline]

        self._set_instruments({
            "n": N,
            "roll": roll, "pitch": pitch, "yaw": yaw,
            "alt": alt, "spd": spd,
            "c1": c1, "c2": c2, "c3": c3, "c4": c4,
            "tstr": tstr, "trel": trel,
        })

    def _set_instruments(self, data):
        html = INSTRUMENTS_HTML_TEMPLATE.replace(
            "__DATA__", json.dumps(data) if data else "null"
        )
        html = html.replace("__TZLABEL__", TZ_LABEL)
        self.instruments_view.setHtml(html, QtCore.QUrl("https://localhost/"))

    def _on_instruments_loaded(self, ok: bool):
        if not ok:
            self.statusBar().showMessage("Instruments view failed to load.")

    # ----- FFT vibration tab -----
    def _populate_fft(self):
        for p in self.fft_plots:
            p.clear()
            if p.plotItem.legend is None:
                p.addLegend(brush=pg.mkBrush(BG_2), pen=pg.mkPen(BORDER),
                            labelTextColor=TEXT)
            else:
                # Clear stale legend rows from a previous log
                p.plotItem.legend.clear()
        if self.parsed is None:
            self.fft_info.setText("  No log loaded.")
            return

        # Collect every IMU we can find: IMU (=IMU1), IMU2, IMU3
        imus = []
        for name in ("IMU", "IMU2", "IMU3"):
            block = self.parsed["data"].get(name)
            ts = self.parsed["times"].get(name)
            if block and ts is not None and len(ts) >= 256:
                imus.append((name, block, np.asarray(ts, dtype=float)))
        if not imus:
            self.fft_info.setText("  Not enough IMU samples for FFT (need ≥256).")
            return

        # Use primary IMU's sample rate for the info line
        primary_t = imus[0][2]
        dts = np.diff(primary_t); dts = dts[dts > 0]
        if len(dts) == 0:
            self.fft_info.setText("  IMU timestamps unusable.")
            return
        fs_primary = 1.0 / float(np.median(dts))
        names = ", ".join(n for n, _, _ in imus)
        self.fft_info.setText(
            f"  IMU sources: {names}  ·  primary sample rate ≈ {fs_primary:.0f} Hz "
            f"·  Nyquist {fs_primary/2:.0f} Hz  ·  {len(primary_t):,} samples  "
            f"·  peaks near motor RPM/60 = resonance"
        )

        # Per-axis (one plot row), one curve per IMU
        # IMU1 = solid bright, IMU2 = solid dimmed, IMU3 = dashed
        axis_colors = {"X": "#22d3ee", "Y": "#a78bfa", "Z": WARN}
        line_styles = [
            ("IMU",  None,          1.6),  # solid
            ("IMU2", "#67e8f9",     1.4),  # dimmer cyan tint
            ("IMU3", WARN,     1.2),  # dashed amber
        ]
        for k, axis_letter in enumerate(("X", "Y", "Z")):
            plot = self.fft_plots[k]
            axis_field = f"Acc{axis_letter}"
            peaks_to_label = None  # only label peaks of primary IMU
            for (imu_name, block, ts) in imus:
                arr = block.get(axis_field)
                if arr is None or len(arr) < 256:
                    continue
                sig = np.asarray(arr, dtype=float) - np.mean(arr)
                n = len(sig)
                win = np.hanning(n)
                spec = np.abs(np.fft.rfft(sig * win)) * (2.0 / np.sum(win))
                # Per-IMU sample rate
                dts_i = np.diff(ts); dts_i = dts_i[dts_i > 0]
                fs_i = 1.0 / float(np.median(dts_i)) if len(dts_i) else fs_primary
                freqs = np.fft.rfftfreq(n, d=1.0 / fs_i)
                freqs = freqs[1:]; spec = spec[1:]

                # Choose pen
                base = axis_colors[axis_letter]
                if imu_name == "IMU":
                    pen = pg.mkPen(base, width=1.8)
                elif imu_name == "IMU2":
                    pen = pg.mkPen(base, width=1.3, style=Qt.PenStyle.DashLine)
                else:  # IMU3
                    pen = pg.mkPen(base, width=1.0, style=Qt.PenStyle.DotLine)
                plot.plot(freqs, spec, pen=pen,
                          name=f"{imu_name}.{axis_field}")
                if imu_name == "IMU":
                    peaks_to_label = (freqs, spec)
            # Top-3 peaks of the primary IMU only
            if peaks_to_label is not None:
                freqs, spec = peaks_to_label
                if len(spec) > 10:
                    top_idx = np.argpartition(spec, -3)[-3:]
                    top_idx = top_idx[np.argsort(spec[top_idx])][::-1]
                    for idx in top_idx:
                        f = float(freqs[idx])
                        if f < 2: continue
                        line = pg.InfiniteLine(pos=f, angle=90,
                            pen=pg.mkPen("#f87171", style=Qt.PenStyle.DashLine, width=1),
                            label=f"{f:.1f} Hz",
                            labelOpts={"position":0.92, "color":"#f87171",
                                       "fill":pg.mkBrush(BG_2)})
                        plot.addItem(line, ignoreBounds=True)
            plot.setXRange(0, fs_primary / 2)

        # ---- Spectrogram: sliding-window FFT of |Acc| magnitude ----
        try:
            primary = imus[0]
            block_imu = primary[1]
            ts_imu = primary[2]
            ax_x = np.asarray(block_imu.get("AccX", []), dtype=float)
            ax_y = np.asarray(block_imu.get("AccY", []), dtype=float)
            ax_z = np.asarray(block_imu.get("AccZ", []), dtype=float)
            min_len = min(len(ax_x), len(ax_y), len(ax_z), len(ts_imu))
            if min_len > 1024:
                mag = np.sqrt(
                    ax_x[:min_len]**2 + ax_y[:min_len]**2 + ax_z[:min_len]**2
                )
                mag = mag - np.mean(mag)
                # Sliding FFT — window length ~1 second, 50% overlap
                win_len = int(min(2048, max(256, fs_primary)))
                hop = max(1, win_len // 2)
                hann = np.hanning(win_len)
                n_frames = max(1, (min_len - win_len) // hop + 1)
                n_bins = win_len // 2 + 1
                spec = np.zeros((n_frames, n_bins), dtype=np.float32)
                for fi in range(n_frames):
                    start = fi * hop
                    seg = mag[start:start + win_len] * hann
                    spec[fi] = np.abs(np.fft.rfft(seg)) * (2.0 / np.sum(hann))
                # dB scale, clipped
                spec_db = 20 * np.log10(spec + 1e-6)
                # Limit to Nyquist
                # spec_db shape: (frames, bins); X=time, Y=freq
                t0 = float(ts_imu[0]) - (self.parsed.get("t_start") or 0.0)
                t1 = float(ts_imu[min_len-1]) - (self.parsed.get("t_start") or 0.0)
                freq_max = fs_primary / 2
                self.spectrogram_image.setImage(spec_db, autoLevels=True)
                self.spectrogram_image.setRect(QtCore.QRectF(
                    t0, 0, max(0.001, t1 - t0), freq_max
                ))
                # Make the time axis show Istanbul wall-clock via IstanbulTimeAxis
                old_axis = self.spectrogram_plot.getAxis("bottom")
                if not isinstance(old_axis, IstanbulTimeAxis):
                    new_axis = IstanbulTimeAxis(orientation="bottom")
                    self.spectrogram_plot.setAxisItems({"bottom": new_axis})
                    new_axis.setPen(pg.mkPen(BORDER))
                    new_axis.setTextPen(pg.mkPen(TEXT_DIM))
                self.spectrogram_plot.getAxis("bottom").set_t_start(
                    self.parsed.get("t_start") or 0.0)
                self.spectrogram_plot.setXRange(t0, t1)
                self.spectrogram_plot.setYRange(0, freq_max)
        except Exception:
            pass

    # ----- PID tuning tab -----
    def _populate_pid(self):
        for p in self.pid_plots:
            p.clear()
        if self.parsed is None:
            self.pid_info.setText("  No log loaded.")
            return
        d = self.parsed["data"]
        t_start = self.parsed.get("t_start") or 0.0
        att = d.get("ATT")
        att_t = self.parsed["times"].get("ATT")
        if not att or att_t is None or len(att_t) < 10:
            self.pid_info.setText("  No ATT (attitude) messages — can't compare desired vs actual.")
            return
        x = np.asarray(att_t, dtype=float) - t_start
        pairs = [
            ("Roll",  "DesRoll",  "ROLL  · cyan = command,  amber = actual"),
            ("Pitch", "DesPitch", "PITCH · cyan = command,  amber = actual"),
            ("Yaw",   "DesYaw",   "YAW   · cyan = command,  amber = actual"),
        ]
        n_traces = 0
        for k, (actual, desired, _title) in enumerate(pairs):
            plot = self.pid_plots[k]
            if actual in att:
                plot.plot(x, np.asarray(att[actual], dtype=float),
                          pen=pg.mkPen(WARN, width=1.5), name=actual)
                n_traces += 1
            if desired in att:
                plot.plot(x, np.asarray(att[desired], dtype=float),
                          pen=pg.mkPen("#22d3ee", width=1.5, style=Qt.PenStyle.DashLine),
                          name=desired)
        if n_traces == 0:
            self.pid_info.setText("  ATT has no Roll/Pitch/Yaw — incompatible log.")
        else:
            self.pid_info.setTextFormat(Qt.TextFormat.RichText)
            stats = analyze_pid_tracking(self.parsed)
            header = (
                "  Cyan dashed = command  ·  Amber solid = vehicle response  ·  "
                "Big gap = loose tuning, ringing = P too high"
            )
            if stats:
                lines = [header]
                for axis in ("roll", "pitch", "yaw"):
                    s = stats.get(axis)
                    if not s: continue
                    badge = {"good": SUCCESS, "loose": WARN,
                             "lagging": WARN, "oscillating": DANGER,
                             "no-command": TEXT_DIM}[s["verdict"]]
                    if s["verdict"] == "no-command":
                        lines.append(
                            f"&nbsp;&nbsp;<b style='color:{badge}'>{axis.upper():5s}</b> · "
                            f"<span style='color:{TEXT_DIM}'>{s['hint']}</span>"
                        )
                    else:
                        lines.append(
                            f"&nbsp;&nbsp;<b style='color:{badge}'>{axis.upper():5s}</b> · "
                            f"RMS {s['rms_err']:.1f}° · peak {s['peak_err']:.0f}° · "
                            f"osc {s['osc_hz']:.1f} Hz · lag {s['lag_ms']:.0f} ms · "
                            f"<span style='color:{TEXT_DIM}'>{s['hint']}</span>"
                        )
                self.pid_info.setText("<br/>".join(lines))
            else:
                self.pid_info.setText(header)

    # ----- Motors tab -----
    def _populate_motors(self):
        self.motors_plot.clear()
        self.motors_events.setText("")
        if self.parsed is None:
            self.motors_stats.setText("  No log loaded.")
            return
        d = self.parsed["data"]
        rcou = d.get("RCOU")
        rcou_t = self.parsed["times"].get("RCOU")
        kind = detect_frame_kind(self.parsed)
        if not rcou or rcou_t is None or len(rcou_t) < 10:
            self.motors_stats.setText(
                "  No RCOU (motor output) messages in this log — can't analyse per-channel PWM.")
            return
        ch_keys = sorted(
            [k for k in rcou.keys() if k.startswith("C") and k[1:].isdigit()],
            key=lambda s: int(s[1:]),
        )[:8]
        if not ch_keys:
            self.motors_stats.setText("  RCOU has no C1..Cn channels — incompatible log.")
            return
        t_start = self.parsed.get("t_start") or 0.0
        x = np.asarray(rcou_t, dtype=float) - t_start
        # Per-motor traces — cycle through palette
        palette = ["#22d3ee", WARN, "#34d399", "#f87171",
                   "#a78bfa", "#f472b6", "#60a5fa", "#facc15"]
        motors = []   # list of (name, arr)
        for i, k in enumerate(ch_keys):
            arr = np.asarray(rcou[k], dtype=float)
            if len(arr) != len(x):
                continue
            # Filter obvious garbage (pre-arm zeros, full-scale outliers)
            finite = np.isfinite(arr)
            if not finite.any() or np.nanmax(arr[finite]) < 900:
                continue
            motors.append((k, arr))
            self.motors_plot.plot(x, arr, pen=pg.mkPen(palette[i % len(palette)], width=1.3), name=k)
        if not motors:
            self.motors_stats.setText("  RCOU channels are empty or below 900 µs — no usable channel data.")
            return
        # ---- Plane / rover / unknown frame: don't pretend channels are motors ----
        if kind in ("plane", "rover", "sub", "other"):
            label_map = {"plane": "SERVOS / THROTTLE", "rover": "RC OUTPUTS",
                         "sub": "RC OUTPUTS", "other": "RC OUTPUTS"}
            hint_map = {
                "plane": ("On a fixed-wing, RCOU channels are aileron / elevator / throttle / "
                          "rudder servos — not independent motors. Comparing means or spread "
                          "between them is meaningless. Look at the throttle channel (usually C3) "
                          "for engine output; the rest should sit near 1500 µs at trim."),
                "rover": "Ground vehicle — RCOU channels are throttle / steering servos.",
                "sub":   "Submarine — RCOU channels drive thrusters in a mixed configuration.",
                "other": "Vehicle type not recognised — showing raw per-channel PWM only.",
            }
            rows_html = (
                f"<table cellspacing='0' cellpadding='4' style='font-family:JetBrains Mono,monospace;font-size:11px'>"
                f"<tr style='color:{TEXT_DIM}'>"
                f"<td>CHANNEL</td><td>MIN</td><td>MEAN</td><td>MAX</td><td>RANGE</td><td>LIKELY ROLE</td></tr>"
            )
            plane_roles = {"C1": "aileron", "C2": "elevator", "C3": "throttle",
                           "C4": "rudder", "C5": "aux", "C6": "aux", "C7": "aux", "C8": "aux"}
            for name, arr in motors:
                finite = arr[np.isfinite(arr)]
                if not len(finite):
                    continue
                mn, mx = float(np.min(finite)), float(np.max(finite))
                mean = float(np.mean(finite))
                role = plane_roles.get(name, "—") if kind == "plane" else "—"
                rows_html += (
                    f"<tr>"
                    f"<td style='color:{TEXT}'>{name}</td>"
                    f"<td style='color:{TEXT}'>{mn:.0f}</td>"
                    f"<td style='color:{TEXT}'>{mean:.0f}</td>"
                    f"<td style='color:{TEXT}'>{mx:.0f}</td>"
                    f"<td style='color:{TEXT}'>{mx - mn:.0f} µs</td>"
                    f"<td style='color:{TEXT_DIM}'>{role}</td>"
                    f"</tr>"
                )
            rows_html += "</table>"
            self.motors_stats.setText(
                f"<div style='font-size:11px'>"
                f"<span style='color:{ACCENT};font-weight:700;letter-spacing:1px'>{label_map[kind]}</span> "
                f"<span style='color:{TEXT_DIM}'>· frame type: {kind} · {len(motors)} channels</span>"
                f"<br/><span style='color:{TEXT_DIM}'>{hint_map[kind]}</span></div>"
                f"{rows_html}"
            )
            return
        # ---- Per-motor stats (only count "armed" samples: any motor > 1100 µs) ----
        all_arr = np.vstack([m[1] for m in motors])
        armed_mask = np.any(all_arr > 1100, axis=0)
        n_armed = int(armed_mask.sum())
        if n_armed < 10:
            self.motors_stats.setText(
                "  Motors never appear armed (no PWM > 1100 µs) — log may be from bench / unarmed.")
            return
        rows = []
        means = []
        for name, arr in motors:
            a = arr[armed_mask]
            mean = float(np.mean(a))
            sat_pct = float(np.mean(a > 1900) * 100.0)
            means.append(mean)
            rows.append((name, mean, sat_pct, a))
        overall = float(np.mean(means))
        spread = float(max(means) - min(means))
        # Worst-offender motor: largest |Δ| from the average
        worst_idx = int(np.argmax([abs(m - overall) for m in means]))
        worst_name = rows[worst_idx][0]
        worst_delta = means[worst_idx] - overall
        worst_role = "working harder" if worst_delta > 0 else "weaker / underloaded"
        worst_sign = "+" if worst_delta >= 0 else ""
        # Verdict for the whole airframe — name the suspect motor in the headline
        if spread < 60:
            verdict_color = SUCCESS
            verdict = f"GOOD · spread {spread:.0f} µs"
        elif spread < 120:
            verdict_color = WARN
            verdict = (f"MARGINAL · spread {spread:.0f} µs · "
                       f"suspect {worst_name} ({worst_sign}{worst_delta:.0f} µs, {worst_role})")
        else:
            verdict_color = DANGER
            verdict = (f"BAD · spread {spread:.0f} µs · "
                       f"check {worst_name} first ({worst_sign}{worst_delta:.0f} µs, {worst_role})")
        # Diagonal-pair check for quads (Motor 1+2 vs 3+4 in ArduPilot Quad-X mixing)
        diag_line = ""
        if len(motors) >= 4:
            d1 = (means[0] + means[1]) / 2.0
            d2 = (means[2] + means[3]) / 2.0
            diff = d1 - d2
            tag = ("balanced" if abs(diff) < 30
                   else f"front/back or CG offset — pair (M1+M2) {'higher' if diff > 0 else 'lower'} by {abs(diff):.0f} µs")
            diag_line = (
                f"<br/><span style='color:{TEXT_DIM}'>DIAGONAL PAIRS · "
                f"(M1+M2)/2 = {d1:.0f} µs &nbsp;·&nbsp; (M3+M4)/2 = {d2:.0f} µs &nbsp;·&nbsp; "
                f"{tag}</span>"
            )
        # Build table
        hdr = (
            f"<table cellspacing='0' cellpadding='4' style='font-family:JetBrains Mono,monospace;font-size:11px'>"
            f"<tr style='color:{TEXT_DIM}'>"
            f"<td>MOTOR</td><td>MEAN PWM</td><td>Δ vs AVG</td><td>SATURATED &gt;1900</td><td>VERDICT</td></tr>"
        )
        for (name, mean, sat_pct, _a) in rows:
            delta = mean - overall
            if abs(delta) < 30:
                m_color = SUCCESS;  m_verdict = "ok"
            elif abs(delta) < 60:
                m_color = WARN; m_verdict = "watch"
            else:
                m_color = DANGER;   m_verdict = "working harder" if delta > 0 else "weaker / underloaded"
            sign = "+" if delta >= 0 else ""
            hdr += (
                f"<tr>"
                f"<td style='color:{TEXT}'>{name}</td>"
                f"<td style='color:{TEXT}'>{mean:.0f} µs</td>"
                f"<td style='color:{m_color}'>{sign}{delta:.0f} µs</td>"
                f"<td style='color:{TEXT}'>{sat_pct:.1f} %</td>"
                f"<td style='color:{m_color}'>{m_verdict}</td>"
                f"</tr>"
            )
        hdr += "</table>"
        self.motors_stats.setText(
            f"<div style='font-size:11px'>"
            f"<span style='color:{verdict_color};font-weight:700;letter-spacing:1px'>{verdict}</span>"
            f" &nbsp;·&nbsp; <span style='color:{TEXT_DIM}'>avg {overall:.0f} µs · {n_armed} armed samples</span>"
            f"{diag_line}</div>{hdr}"
        )
        # ---- Desync / spike detector ----
        # At each armed sample, compare each motor to the mean of the others.
        # A spike of >150 µs sustained for >0.1s is suspicious (ESC desync,
        # demag, motor stall, prop strike).
        try:
            t_arr = x[armed_mask]
            stacked = all_arr[:, armed_mask]
            n_motors = stacked.shape[0]
            # mean of "others" for each motor
            total = stacked.sum(axis=0)
            others_mean = (total[None, :] - stacked) / max(1, n_motors - 1)
            dev = stacked - others_mean
            # rough sample period
            if len(t_arr) > 1:
                dt = float(np.median(np.diff(t_arr)))
                dt = dt if dt > 0 else 0.02
            else:
                dt = 0.02
            min_run = max(2, int(0.1 / dt))
            events = []  # (t_sec, motor_name, peak_dev)
            for mi in range(n_motors):
                flag = np.abs(dev[mi]) > 150.0
                if not flag.any():
                    continue
                # find runs of True
                idx = np.where(flag)[0]
                if len(idx) == 0:
                    continue
                splits = np.where(np.diff(idx) > 1)[0]
                groups = np.split(idx, splits + 1) if len(splits) else [idx]
                for g in groups:
                    if len(g) < min_run:
                        continue
                    seg = dev[mi, g]
                    peak_i = int(np.argmax(np.abs(seg)))
                    events.append((float(t_arr[g[peak_i]]), motors[mi][0], float(seg[peak_i])))
            events.sort(key=lambda e: -abs(e[2]))
            if not events:
                self.motors_events.setText(
                    f"<span style='color:{SUCCESS};font-weight:700'>NO DESYNC EVENTS</span> "
                    f"<span style='color:{TEXT_DIM}'>· no motor deviated >150 µs from the others "
                    f"for &gt;0.1 s. Healthy ESC/motor behaviour.</span>"
                )
            else:
                lines = [
                    f"<span style='color:{DANGER};font-weight:700'>{len(events)} DESYNC / SPIKE EVENT(S)</span> "
                    f"<span style='color:{TEXT_DIM}'>· motor PWM diverged &gt;150 µs from the others "
                    f"for &gt;0.1 s. Likely ESC desync, demag, prop strike, or stalled motor.</span><br/>"
                ]
                for t_sec, name, peak in events[:8]:
                    wall = fmt_istanbul(t_start + t_sec)
                    sign = "+" if peak >= 0 else ""
                    lines.append(
                        f"<span style='color:{TEXT_DIM}'>t+{t_sec:6.1f}s ({wall})</span> "
                        f"&nbsp; <span style='color:{ACCENT};font-weight:700'>{name}</span> "
                        f"<span style='color:{DANGER}'>{sign}{peak:.0f} µs vs others</span>"
                    )
                if len(events) > 8:
                    lines.append(f"<span style='color:{TEXT_DIM}'>… and {len(events) - 8} more</span>")
                self.motors_events.setText("<br/>".join(lines))
        except Exception:
            self.motors_events.setText("")

    # ----- Params tab -----
    def _populate_params(self):
        self.params_table.setRowCount(0)
        if self.parsed is None:
            self.params_status.setText("")
            return
        params = self.parsed.get("params") or {}
        if not params:
            self.params_status.setText("  No PARM messages in this log.")
            return
        sorted_items = sorted(params.items(), key=lambda kv: kv[0])
        self.params_table.setRowCount(len(sorted_items))
        for row, (name, val) in enumerate(sorted_items):
            try:
                vstr = f"{float(val):.6g}"
            except (TypeError, ValueError):
                vstr = str(val)
            name_item = QtWidgets.QTableWidgetItem(str(name))
            val_item  = QtWidgets.QTableWidgetItem(vstr)
            name_item.setForeground(QtGui.QColor(ACCENT))
            val_item.setForeground(QtGui.QColor(TEXT))
            self.params_table.setItem(row, 0, name_item)
            self.params_table.setItem(row, 1, val_item)
        self.params_table.resizeColumnToContents(0)
        self.params_status.setText(f"  {len(sorted_items)} parameter(s)")
        self._filter_params(self.params_filter.text())

    def _filter_params(self, text: str):
        needle = (text or "").strip().upper()
        shown = 0
        for row in range(self.params_table.rowCount()):
            item = self.params_table.item(row, 0)
            if item is None:
                continue
            match = (not needle) or (needle in item.text().upper())
            self.params_table.setRowHidden(row, not match)
            if match:
                shown += 1
        total = self.params_table.rowCount()
        if needle:
            self.params_status.setText(f"  {shown} of {total} match '{needle}'")
        else:
            self.params_status.setText(f"  {total} parameter(s)")

    # ----- Map tab -----
    def _populate_map(self):
        track = self._extract_track()
        self._set_map_coords(track)

    def _extract_track(self) -> dict:
        """Return a clean lat/lng/alt + relative-seconds track."""
        if self.parsed is None:
            return {"coords": [], "alts": [], "trel": []}
        t_start = self.parsed.get("t_start") or 0.0
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
            alts = np.asarray(block.get("Alt", np.zeros_like(lats)), dtype=float)
            ts = np.asarray(self.parsed["times"].get(mt, []), dtype=float)
            if len(ts) != len(lats):
                ts = np.zeros_like(lats)
            if len(lats) == 0:
                continue

            if np.nanmax(np.abs(lats)) > 200:
                lats = lats / 1e7
                lngs = lngs / 1e7

            mask = (np.abs(lats) > 0.0001) & (np.abs(lngs) > 0.0001)
            if mt.startswith("GPS"):
                status = block.get("Status")
                nsats = block.get("NSats")
                if status is not None:
                    mask &= np.asarray(status, dtype=float) >= 3
                if nsats is not None:
                    mask &= np.asarray(nsats, dtype=float) >= 4

            lats = lats[mask]; lngs = lngs[mask]; alts = alts[mask]; ts = ts[mask]
            if len(lats) < 2:
                continue

            med_la, med_lo = float(np.median(lats)), float(np.median(lngs))
            jump_mask = (np.abs(lats - med_la) < 0.01) & (np.abs(lngs - med_lo) < 0.01)
            lats = lats[jump_mask]; lngs = lngs[jump_mask]
            alts = alts[jump_mask]; ts = ts[jump_mask]
            if len(lats) < 2:
                continue

            if len(lats) > 3000:
                step = len(lats) // 3000
                lats = lats[::step]; lngs = lngs[::step]
                alts = alts[::step]; ts = ts[::step]
            return {
                "coords": [[float(la), float(lo)] for la, lo in zip(lats, lngs)],
                "alts":   [float(a) for a in alts],
                "trel":   [float(t - t_start) if t > 0 else 0.0 for t in ts],
            }
        return {"coords": [], "alts": [], "trel": []}

    def _extract_mission_and_fence(self) -> dict:
        """Return planned mission waypoints + geofence polygon if present."""
        if self.parsed is None:
            return {"waypoints": [], "fence": []}
        d = self.parsed["data"]
        wps: list[dict] = []
        # CMD message holds the planned mission (one row per waypoint).
        # Field names vary slightly between firmware versions; handle both.
        cmd = d.get("CMD")
        if cmd:
            lat_key = next((k for k in ("Lat", "lat") if k in cmd), None)
            lng_key = next((k for k in ("Lng", "Lon", "lng", "lon") if k in cmd), None)
            alt_key = next((k for k in ("Alt", "alt") if k in cmd), None)
            cnum_key = next((k for k in ("CNum", "WPNum", "Num") if k in cmd), None)
            ctot_key = next((k for k in ("CTot", "WPTot") if k in cmd), None)
            cid_key = next((k for k in ("CId", "Id") if k in cmd), None)
            if lat_key and lng_key:
                lats = np.asarray(cmd[lat_key], dtype=float)
                lngs = np.asarray(cmd[lng_key], dtype=float)
                if len(lats) and np.nanmax(np.abs(lats)) > 200:
                    lats = lats / 1e7; lngs = lngs / 1e7
                for i in range(len(lats)):
                    la, lo = float(lats[i]), float(lngs[i])
                    if abs(la) < 0.0001 and abs(lo) < 0.0001:
                        continue
                    wps.append({
                        "lat": la, "lng": lo,
                        "alt": float(cmd[alt_key][i]) if alt_key and i < len(cmd[alt_key]) else 0.0,
                        "n":   int(cmd[cnum_key][i]) if cnum_key and i < len(cmd[cnum_key]) else (i + 1),
                        "tot": int(cmd[ctot_key][i]) if ctot_key and i < len(cmd[ctot_key]) else 0,
                        "id":  int(cmd[cid_key][i])  if cid_key  and i < len(cmd[cid_key])  else 0,
                    })

        # FENCE polygon — points are stored across multiple rows
        fence: list[list[float]] = []
        f = d.get("FNCE") or d.get("FENC") or d.get("FENCE")
        if f:
            lat_key = next((k for k in ("Lat", "lat") if k in f), None)
            lng_key = next((k for k in ("Lng", "Lon", "lng", "lon") if k in f), None)
            if lat_key and lng_key:
                lats = np.asarray(f[lat_key], dtype=float)
                lngs = np.asarray(f[lng_key], dtype=float)
                if len(lats) and np.nanmax(np.abs(lats)) > 200:
                    lats = lats / 1e7; lngs = lngs / 1e7
                for la, lo in zip(lats, lngs):
                    if abs(la) > 0.0001 and abs(lo) > 0.0001:
                        fence.append([float(la), float(lo)])
        return {"waypoints": wps, "fence": fence}

    def _set_map_coords(self, track):
        # Back-compat: list of [lat,lng] still works
        if isinstance(track, list):
            track = {"coords": track, "alts": []}
        # Attach mission + fence overlays
        extras = self._extract_mission_and_fence()
        track = {**track, **extras}
        html = MAP_HTML_TEMPLATE.replace("__TRACK__", json.dumps(track))
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
    # Always start maximized — fills the screen but keeps the title bar
    # so the user can still minimize / close normally.
    win.showMaximized()

    # App-wide drag-and-drop filter — catches drops landing on any child
    # widget (esp. QWebEngineView, which would otherwise swallow them).
    class _DropFilter(QtCore.QObject):
        def __init__(self, target: "MainWindow"):
            super().__init__(target)
            self.target = target
        def eventFilter(self, obj, ev):
            t = ev.type()
            if t == QtCore.QEvent.Type.DragEnter or t == QtCore.QEvent.Type.DragMove:
                if ev.mimeData().hasUrls():
                    ev.acceptProposedAction()
                    return True
            elif t == QtCore.QEvent.Type.Drop:
                for url in ev.mimeData().urls():
                    p = url.toLocalFile()
                    if self.target._is_log_path(p):
                        self.target.load_file(p)
                        ev.acceptProposedAction()
                        return True
            elif t == QtCore.QEvent.Type.FileOpen:
                p = ev.file()
                if self.target._is_log_path(p):
                    self.target.load_file(p)
                    return True
            return False
    win._drop_filter = _DropFilter(win)
    app.installEventFilter(win._drop_filter)

    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        QtCore.QTimer.singleShot(50, lambda: win.load_file(sys.argv[1]))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
