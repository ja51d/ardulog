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
from PyQt6 import QtCore, QtGui, QtPrintSupport, QtWidgets
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
# Antialias OFF — on macOS, anti-aliased software paths take ~1s for 3,500
# points which makes plotting feel like the UI is frozen. Lines still look
# fine with Qt's default rendering at typical screen sizes.
pg.setConfigOptions(antialias=False)

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
    font-family: "JetBrains Mono", "SF Mono", Menlo, "Cascadia Code", Consolas, monospace;
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
  .panel{background:linear-gradient(180deg,#16223c 0%,#111a2e 100%);
         border:1px solid #243154;border-radius:12px;
         padding:14px;display:flex;flex-direction:column;align-items:center;
         min-height:0;box-shadow:0 4px 18px rgba(0,0,0,0.25)}
  .panel h3{margin:0 0 10px;color:#8b97b3;font-size:10px;letter-spacing:2.5px;
            font-weight:700;text-align:center}
  .panel svg{flex:1;min-height:0;width:100%}
  .readout{margin-top:8px;font-family:"JetBrains Mono","SF Mono",Menlo,monospace;
           color:#22d3ee;font-size:13px;font-weight:700;letter-spacing:1px;
           text-align:center;white-space:nowrap}
  .readout .dim{color:#8b97b3;font-weight:400;letter-spacing:1.5px;font-size:10px}

  /* Radio transmitter — single teal-cyan housing with two circular gimbals */
  .rc-housing{
    background:linear-gradient(180deg,#0f9d9e 0%,#0d7a8a 100%);
    border:1px solid #22d3ee;border-radius:18px;
    box-shadow:0 8px 26px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.15);
    padding:18px 24px;
    display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:center;
    position:relative;min-height:0
  }
  .rc-housing::before, .rc-housing::after{
    content:'';position:absolute;width:14px;height:14px;color:#e6edf7;opacity:0.5;font-size:14px
  }
  .rc-housing::before{top:10px;left:14px;content:'✥'}
  .rc-housing::after{bottom:10px;right:14px;content:'▲';transform:rotate(45deg)}
  .gimbal-wrap{display:flex;flex-direction:column;align-items:center;gap:8px;min-height:0}
  .gimbal-wrap svg{flex:1;min-height:0;width:100%;max-width:200px}
  .gimbal-label{font-size:9px;letter-spacing:2.5px;font-weight:700;color:#0b1220;text-align:center;text-transform:uppercase}
  .gimbal-readout{font-family:"JetBrains Mono","SF Mono",Menlo,monospace;color:#0b1220;
                  font-size:11px;font-weight:700;letter-spacing:0.5px;text-align:center;white-space:nowrap}

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
  .ai-bg{fill:#0b1220}
  .ai-sky{fill:#1d4ed8}
  .ai-ground{fill:#854d0e}
  .ai-horizon{stroke:#e6edf7;stroke-width:1.5}
  .ai-pitch-tick{stroke:#e6edf7;stroke-width:1;stroke-linecap:round}
  .ai-pitch-label{fill:#e6edf7;font-size:7px;font-family:"JetBrains Mono",monospace;font-weight:700}
  .ai-frame{fill:none;stroke:#243154;stroke-width:2}
  .ai-aircraft{fill:none;stroke:#fbbf24;stroke-width:2.5;stroke-linecap:round}
  .ai-roll-tick{stroke:#e6edf7;stroke-width:1.2}
  .ai-roll-pointer{fill:#fbbf24}
  .hsi-card{fill:#0b1220;stroke:#243154}
  .hsi-tick{stroke:#e6edf7;stroke-width:1.2;stroke-linecap:round}
  .hsi-cardinal{fill:#22d3ee;font-size:14px;font-weight:800;font-family:"Inter",sans-serif;text-anchor:middle}
  .hsi-deg{fill:#8b97b3;font-size:8px;font-family:"JetBrains Mono",monospace;text-anchor:middle}
  .hsi-aircraft{fill:#fbbf24;stroke:#0b1220;stroke-width:1}
  .tape-bg{fill:#0b1220;stroke:#243154}
  .tape-tick{stroke:#8b97b3;stroke-width:1}
  .tape-tick-major{stroke:#e6edf7;stroke-width:1.5}
  .tape-label{fill:#8b97b3;font-size:9px;font-family:"JetBrains Mono",monospace}
  .tape-marker{fill:#22d3ee}
  .tape-current{fill:#22d3ee;font-size:14px;font-weight:800;font-family:"JetBrains Mono",monospace;text-anchor:middle}
  .stick-frame{fill:#0b1220;stroke:#243154;stroke-width:1.5}
  .stick-cross{stroke:#243154;stroke-width:1}
  .stick-dot{fill:#22d3ee;stroke:#0b1220;stroke-width:2}
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
            <circle cx="0" cy="0" r="2.5" fill="#fbbf24"/>
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
          <polygon fill="#fbbf24" points="0,-90 -5,-78 5,-78"/>
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
            THR <span id="stick-l-thr">1500</span> &nbsp;·&nbsp; YAW <span id="stick-l-yaw">1500</span>
          </div>
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
            PIT <span id="stick-r-pit">1500</span> &nbsp;·&nbsp; ROLL <span id="stick-r-rol">1500</span>
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
    document.getElementById('t-time').textContent = tstr + ' TR';
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
    VERT_COLORS = ['#22d3ee','#22d3ee','#a78bfa','#a78bfa','#22d3ee','#a78bfa','#fbbf24'];
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

  // ---- Traces ----
  const fullRoute = {
    type:'scatter3d', mode:'lines',
    x:X, y:Y, z:Z,
    line:{ width:2, color:'rgba(167,139,250,0.30)' },
    name:'route', hoverinfo:'skip', showlegend:true
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
    document.getElementById('hud-time').textContent    = 'TIME ' + t + ' TR';
    document.getElementById('hud-elapsed').textContent = 'T+' + tr.toFixed(1) + 's';
    document.getElementById('hud-alt').textContent     = 'ALT ' + alt.toFixed(1) + ' m';
    document.getElementById('hud-d').textContent       = 'DIST ' + dist.toFixed(1) + ' m';
    document.getElementById('hud-i').textContent       = 'SAMPLE ' + (lo+1) + '/' + N;
    document.getElementById('t3d-time').textContent    = t + ' TR';
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

  Plotly.newPlot('plot', [fullRoute, flownTrail, aircraft, startMarker, endMarker], layout, config)
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
const COORDS = TRACK.coords || [];
const ALTS   = TRACK.alts   || [];
const TREL   = TRACK.trel   || [];
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
        + 'background:linear-gradient(to top, #22d3ee 0%, #a78bfa 50%, #fbbf24 100%);'
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

    # ---------- Crash / incident detection ----------
    incidents = detect_incidents(parsed)
    if incidents:
        worst = max(incidents, key=lambda x: x["severity"])
        sev_label = {1: "Marginal", 2: "Marginal", 3: "Bad"}[worst["severity"]]
        sev_color = {1: "#fbbf24", 2: "#fbbf24", 3: DANGER}[worst["severity"]]
        bullets = []
        for ev in incidents[:8]:
            bullets.append(f"{fmt_istanbul(ev['t'])}  {ev['title']} — {ev['detail']}")
        more = f"  (+{len(incidents)-8} more)" if len(incidents) > 8 else ""
        add("Incidents detected", sev_label, sev_color,
            f"{len(incidents)} notable event(s) detected.",
            "\n".join(bullets) + more)

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

    def set_t_start(self, t_start: float):
        self._t_start = float(t_start)
        self.time_axis.set_t_start(t_start)

    def _on_mouse(self, pos):
        if not self.sceneBoundingRect().contains(pos):
            return
        view = self.plotItem.vb.mapSceneToView(pos)
        x, y = view.x(), view.y()
        self.vline.setPos(x)
        self.vline.show()
        # x is relative seconds — add t_start for wall-clock display
        self.status_label.setText(
            f"◇   {fmt_istanbul(x + self._t_start, with_date=False)}  TR     y = {y:0.4f}"
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
        self.recent_files: list[str] = self._load_recent_files()
        self.comparison: dict | None = None
        self.comparison_curves: dict[tuple[str, str], pg.PlotDataItem] = {}
        self._cmp_worker: LogParseWorker | None = None

        self._build_menu()
        self._build_ui()
        # Drag-and-drop a .bin/.tlog/.log onto the window to open it
        self.setAcceptDrops(True)

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

        file_menu.addSeparator()
        quit_act = QtGui.QAction("&Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        view_menu = bar.addMenu("&View")
        clear_act = QtGui.QAction("Clear plot", self)
        clear_act.triggered.connect(self.clear_plot)
        view_menu.addAction(clear_act)

    # ----- Recent files -----
    @staticmethod
    def _recent_files_path() -> Path:
        return Path.home() / ".uav_log_viewer_recent.json"

    def _load_recent_files(self) -> list[str]:
        p = self._recent_files_path()
        if not p.exists():
            return []
        try:
            with open(p) as f:
                data = json.load(f)
            return [str(x) for x in data if isinstance(x, str) and Path(x).exists()][:10]
        except Exception:
            return []

    def _save_recent_files(self):
        try:
            with open(self._recent_files_path(), "w") as f:
                json.dump(self.recent_files, f)
        except Exception:
            pass

    def _push_recent(self, path: str):
        p = str(Path(path).resolve())
        if p in self.recent_files:
            self.recent_files.remove(p)
        self.recent_files.insert(0, p)
        self.recent_files = self.recent_files[:10]
        self._save_recent_files()
        self._rebuild_recent_menu()

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
        start_dir = str(Path(__file__).parent)
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open comparison log", start_dir,
            "Flight logs (*.bin *.BIN *.tlog *.TLOG *.log);;All files (*)"
        )
        if not path:
            return
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
        col = "#fbbf24"  # default amber
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

    # ----- Master synchronized playback -----
    def _toggle_master_play(self):
        if self.parsed is None:
            return
        if self.master_playing:
            self.master_playing = False
            self.master_timer.stop()
            self.master_play_btn.setText("▶ PLAY ALL")
        else:
            duration = float(self.parsed.get("duration", 0))
            if self.master_t >= duration - 0.05:
                self.master_t = 0.0
            self.master_playing = True
            self.master_play_btn.setText("❚❚ PAUSE")
            self.master_last_ts = time.monotonic()
            self.master_timer.start()

    def _master_reset(self):
        self.master_playing = False
        self.master_timer.stop()
        self.master_play_btn.setText("▶ PLAY ALL")
        self.master_t = 0.0
        self._master_push()

    def _master_tick(self):
        if not self.master_playing or self.parsed is None:
            return
        now = time.monotonic()
        dt = now - self.master_last_ts
        self.master_last_ts = now
        duration = float(self.parsed.get("duration", 0))
        self.master_t += dt
        if self.master_t >= duration:
            self.master_t = duration
            self._toggle_master_play()
        self._master_push()

    def _on_master_slider_changed(self, value: int):
        if self.parsed is None:
            return
        duration = float(self.parsed.get("duration", 0))
        new_t = (value / 1000.0) * duration
        # Only act if change came from user interaction (not our own update)
        if abs(new_t - self.master_t) < 1e-6:
            return
        # If user scrubs while playing, pause
        if self.master_playing:
            self._toggle_master_play()
        self.master_t = new_t
        self._master_push(emit_slider=False)

    def _master_push(self, emit_slider: bool = True):
        if self.parsed is None:
            return
        duration = max(0.001, float(self.parsed.get("duration", 0)))
        # Time label
        self.master_time_label.setText(
            f"T+{self.master_t:6.1f}s  ·  {self.master_t/duration*100:5.1f}%"
        )
        # Slider sync (block signal to avoid feedback)
        if emit_slider:
            self.master_slider.blockSignals(True)
            self.master_slider.setValue(int((self.master_t / duration) * 1000))
            self.master_slider.blockSignals(False)
        # Push to web views
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
                    f"<tr><td>START (TR)</td><td>{start}</td></tr>"
                    f"<tr><td>END (TR)</td><td>{end}</td></tr>"
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

        # Telemetry summary chip
        self.header_summary = QtWidgets.QLabel("no log loaded")
        self.header_summary.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; padding:8px 14px;"
            f"background:{BG_2}; border:1px solid {BORDER}; border-radius:8px;"
            f"font-family: 'JetBrains Mono', 'SF Mono', Menlo, monospace;"
        )
        h.addWidget(self.header_summary)

        # Prominent credit badge in the header
        credit_badge = QtWidgets.QLabel(
            f"<span style='color:{TEXT_DIM};font-size:10px;letter-spacing:2px;font-weight:600;'>CREATED BY</span>"
            f"&nbsp;&nbsp;<span style='color:{ACCENT};font-size:18px;font-weight:900;letter-spacing:2px;"
            f"font-family:Inter Display,Inter,Helvetica Neue,sans-serif;'>JAVID</span>"
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

        # Master playback bar — drives Cockpit + 3D + Map at the same wall-clock
        self.master_bar = QtWidgets.QFrame()
        self.master_bar.setStyleSheet(
            f"background:{BG_1};border-bottom:1px solid {BORDER};"
        )
        self.master_bar.setFixedHeight(48)
        mb = QtWidgets.QHBoxLayout(self.master_bar)
        mb.setContentsMargins(16, 6, 16, 6)
        mb.setSpacing(12)

        mlabel = QtWidgets.QLabel("◈ MASTER TIMELINE")
        mlabel.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; font-weight:700;"
            f"letter-spacing:2px;"
        )
        mb.addWidget(mlabel)

        self.master_play_btn = QtWidgets.QPushButton("▶ PLAY ALL")
        self.master_play_btn.setObjectName("primary")
        self.master_play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.master_play_btn.setMinimumWidth(110)
        self.master_play_btn.clicked.connect(self._toggle_master_play)
        mb.addWidget(self.master_play_btn)

        self.master_reset_btn = QtWidgets.QPushButton("⏮")
        self.master_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.master_reset_btn.clicked.connect(self._master_reset)
        mb.addWidget(self.master_reset_btn)

        self.master_slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.master_slider.setMinimum(0)
        self.master_slider.setMaximum(1000)
        self.master_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ height:6px; background:{BG_3}; border-radius:3px; }}"
            f"QSlider::handle:horizontal {{ width:16px; margin:-6px 0; background:{ACCENT};"
            f"border:2px solid {BG_0}; border-radius:9px; }}"
            f"QSlider::sub-page:horizontal {{ background:{ACCENT}; border-radius:3px; }}"
        )
        self.master_slider.valueChanged.connect(self._on_master_slider_changed)
        mb.addWidget(self.master_slider, 1)

        self.master_time_label = QtWidgets.QLabel("T+0.0s")
        self.master_time_label.setStyleSheet(
            f"color:{ACCENT};font-family:'JetBrains Mono','SF Mono',Menlo,monospace;"
            f"font-weight:700;min-width:140px;font-size:12px;"
        )
        self.master_time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        mb.addWidget(self.master_time_label)

        root_layout.addWidget(self.master_bar)

        # Master playback state
        self.master_t = 0.0           # seconds since flight start
        self.master_playing = False
        self.master_last_ts = 0.0
        self.master_timer = QtCore.QTimer(self)
        self.master_timer.setInterval(33)  # ~30 fps
        self.master_timer.timeout.connect(self._master_tick)
        self.master_bar.setEnabled(False)
        self.master_bar.setVisible(False)

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

        self.setCentralWidget(root)

        self.statusBar().showMessage("Open a .bin log (⌘O / Ctrl+O) to begin")

    # ----- File loading -----
    def open_file(self):
        start_dir = str(Path(__file__).parent)
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open flight log", start_dir,
            "Flight logs (*.bin *.BIN *.tlog *.TLOG *.log);;DataFlash binary (*.bin);;MAVLink telemetry (*.tlog);;All files (*)"
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
        # Reset & enable master timeline
        self.master_playing = False
        self.master_timer.stop()
        self.master_t = 0.0
        self.master_bar.setEnabled(True)
        self.master_bar.setVisible(True)
        self.master_play_btn.setText("▶ PLAY ALL")
        # Push initial position once web views finish loading
        QtCore.QTimer.singleShot(800, lambda: self._master_push(emit_slider=True))
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
        self._populate_instruments()
        self._populate_fft()
        self._populate_pid()
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
        self.instruments_view.setHtml(html, QtCore.QUrl("https://localhost/"))

    def _on_instruments_loaded(self, ok: bool):
        if not ok:
            self.statusBar().showMessage("Instruments view failed to load.")

    # ----- FFT vibration tab -----
    def _populate_fft(self):
        for p in self.fft_plots:
            p.clear()
        if self.parsed is None:
            self.fft_info.setText("  No log loaded.")
            return
        imu = self.parsed["data"].get("IMU")
        imu_t = self.parsed["times"].get("IMU")
        if not imu or imu_t is None or len(imu_t) < 256:
            self.fft_info.setText("  Not enough IMU samples for FFT (need ≥256).")
            return
        t = np.asarray(imu_t, dtype=float)
        dts = np.diff(t)
        dts = dts[dts > 0]
        if len(dts) == 0:
            self.fft_info.setText("  IMU timestamps unusable.")
            return
        fs = 1.0 / float(np.median(dts))
        self.fft_info.setText(
            f"  IMU sample rate ≈ {fs:.0f} Hz  ·  Nyquist {fs/2:.0f} Hz  ·  "
            f"{len(t):,} samples  ·  peaks near motor RPM/60 = resonance"
        )
        peak_colors = ["#22d3ee", "#a78bfa", "#fbbf24"]
        for k, axis_field in enumerate(("AccX", "AccY", "AccZ")):
            plot = self.fft_plots[k]
            arr = imu.get(axis_field)
            if arr is None or len(arr) < 256:
                continue
            sig = np.asarray(arr, dtype=float)
            sig = sig - np.mean(sig)
            n = len(sig)
            # Hann window for cleaner peaks
            win = np.hanning(n)
            spec = np.abs(np.fft.rfft(sig * win)) * (2.0 / np.sum(win))
            freqs = np.fft.rfftfreq(n, d=1.0 / fs)
            # Drop the DC bin
            freqs = freqs[1:]; spec = spec[1:]
            plot.plot(freqs, spec, pen=pg.mkPen(peak_colors[k], width=1.5),
                      name=f"Acc{axis_field[-1]}")
            # Annotate top 3 peaks
            if len(spec) > 10:
                top_idx = np.argpartition(spec, -3)[-3:]
                top_idx = top_idx[np.argsort(spec[top_idx])][::-1]
                for idx in top_idx:
                    f = float(freqs[idx])
                    if f < 2: continue  # ignore near-DC drift
                    line = pg.InfiniteLine(pos=f, angle=90,
                        pen=pg.mkPen("#f87171", style=Qt.PenStyle.DashLine, width=1),
                        label=f"{f:.1f} Hz",
                        labelOpts={"position":0.92, "color":"#f87171",
                                   "fill":pg.mkBrush(BG_2)})
                    plot.addItem(line, ignoreBounds=True)
            plot.setXRange(0, fs / 2)

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
                          pen=pg.mkPen("#fbbf24", width=1.5), name=actual)
                n_traces += 1
            if desired in att:
                plot.plot(x, np.asarray(att[desired], dtype=float),
                          pen=pg.mkPen("#22d3ee", width=1.5, style=Qt.PenStyle.DashLine),
                          name=desired)
        if n_traces == 0:
            self.pid_info.setText("  ATT has no Roll/Pitch/Yaw — incompatible log.")
        else:
            self.pid_info.setText(
                "  Cyan dashed = pilot/autopilot command.  Amber solid = vehicle response."
                "  Large gap → controller can't keep up (loose tuning)."
                "  Oscillation around command → gain too high."
            )

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

    def _set_map_coords(self, track):
        # Back-compat: list of [lat,lng] still works
        if isinstance(track, list):
            track = {"coords": track, "alts": []}
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
    win.show()

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
