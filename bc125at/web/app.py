#!/usr/bin/env python3
"""
BC125AT Web GUI

A clean, modern web interface for the BC125AT scanner programming tool.
Runs a local Flask server and opens in the browser.
"""

import atexit
import json
import os
import signal
import sys
import webbrowser
import threading
from flask import Flask, render_template_string, jsonify, request, send_file, after_this_request
from datetime import datetime
from io import StringIO
import tempfile

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bc125at.connection import ScannerConnection
from bc125at.channels import Channel, ChannelManager, NUM_CHANNELS, CHANNELS_PER_BANK
from bc125at.channels import CTCSS_TONES, DCS_CODES, MODULATION_MODES, DELAY_VALUES
from bc125at.channels import tone_code_to_string, is_valid_frequency, FREQ_RANGES
from bc125at.settings import (
    SettingsManager, ScannerSettings, BACKLIGHT_OPTIONS,
    PRIORITY_OPTIONS,
)
from bc125at.search import (
    SearchManager, CloseCallSettings, SearchSettings, CustomSearchRange,
    CC_MODE_OPTIONS, CC_BANDS, SERVICE_GROUPS,
)
from bc125at.presets import list_presets, get_preset_channels, PRESET_CATALOG
from bc125at.io import export_channels_csv, export_channels_json, export_full_backup, export_bc125at_ss

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Global connection (reused across requests)
_conn = None

def get_conn():
    """Get or create a scanner connection. Auto-reconnects if disconnected."""
    global _conn
    if _conn is not None:
        # Check if still connected by testing the device
        try:
            if _conn.dev is None:
                raise ConnectionError("Device gone")
            _conn.dev.is_kernel_driver_active(0)
        except Exception:
            try:
                _conn.disconnect()
            except Exception:
                pass
            _conn = None

    if _conn is None:
        conn = ScannerConnection()
        conn.connect()
        _conn = conn
    return _conn

def safe_disconnect():
    """Safely disconnect from scanner, exiting program mode first."""
    global _conn
    if _conn:
        try:
            _conn.disconnect()
        except Exception:
            pass
        _conn = None


def _friendly_connection_error(exc):
    msg = str(exc)
    lower = msg.lower()

    if "not found" in lower:
        return (
            "Scanner not detected. Make sure the BC125AT is powered on, reconnect the USB cable, "
            "and try again. If needed, unplug it, power-cycle the scanner, and reconnect."
        )
    if "access denied" in lower or "insufficient permissions" in lower:
        return (
            "The scanner was found but could not be claimed. Close any other scanner software, "
            "reconnect the USB cable, and try again."
        )
    if "usb write error" in lower or "usb read error" in lower or "timeout" in lower:
        return (
            "The scanner connection was interrupted. Release the scanner, reconnect the USB cable, "
            "and try again. If needed, power-cycle the scanner before reconnecting."
        )
    if "program mode" in lower:
        return (
            "The scanner did not enter programming mode. Make sure it is not in a menu or direct-entry "
            "screen, then reconnect and try again."
        )
    return msg


def safe_exit_program_mode():
    """Return scanner to normal scan/hold mode if we left it in program mode."""
    global _conn
    if _conn and getattr(_conn, "in_program_mode", False):
        try:
            _conn.exit_program_mode()
        except Exception:
            pass


def _clean_display_text(value):
    """Keep scanner display text readable for the web UI."""
    if not value:
        return ""
    cleaned = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in str(value))
    return " ".join(cleaned.split()).strip()


def _parse_status_response(status_resp):
    """Extract a friendly status label and display text from STS output."""
    if not status_resp or not status_resp.startswith("STS"):
        return {"status": status_resp or "-", "display_lines": []}

    parts = status_resp.split(",")
    display_lines = []
    for part in parts[2:]:
        cleaned = _clean_display_text(part)
        if cleaned and not cleaned.isdigit() and cleaned != "0.0000":
            display_lines.append(cleaned)

    status = "Monitoring"
    if any("Close Call" in line for line in display_lines):
        status = "Close Call"
    elif any("Scan" in line for line in display_lines):
        status = "Scanning"
    elif any("Hold" in line for line in display_lines):
        status = "Hold"

    return {"status": status, "display_lines": display_lines}


def _require_json_dict():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object request body")
    return data


def _parse_import_bank(raw_value):
    """Parse optional bank selector from form/json input."""
    if raw_value in (None, "", "keep", "file"):
        return None
    bank = int(raw_value)
    if bank not in range(10):
        raise ValueError("Bank must be 0-9")
    return bank


def _apply_import_options(channels, target_bank=None, clear_bank_first=False):
    """Apply destination bank options before writing channels."""
    channels = list(channels)
    if target_bank is None:
        if clear_bank_first:
            raise ValueError("Choose a destination bank before using clear-bank import")
        return channels, None

    start = 451 if target_bank == 0 else (target_bank - 1) * CHANNELS_PER_BANK + 1
    max_fit = CHANNELS_PER_BANK
    truncated = None
    if len(channels) > max_fit:
        truncated = len(channels) - max_fit
        channels = channels[:max_fit]
    for i, ch in enumerate(channels):
        ch.index = start + i
    return channels, truncated


def _build_import_preview(channels, target_bank=None, clear_bank_first=False, truncated=None, kind="channels"):
    """Build a compact preview payload for the web UI."""
    preview_items = []
    for ch in channels[:12]:
        preview_items.append({
            "channel": ch.index,
            "name": ch.name,
            "frequency": ch.frequency,
            "modulation": ch.modulation,
            "tone": ch.tone_string,
            "bank": ch.bank,
        })

    if target_bank is None:
        destination = "Use channel numbers from import data"
    else:
        destination = f"Sequentially load into bank {target_bank}"

    if clear_bank_first and target_bank is not None:
        destination += " after clearing that bank"

    return {
        "kind": kind,
        "count": len(channels),
        "destination": destination,
        "truncated": truncated or 0,
        "preview_items": preview_items,
    }


def _session_active():
    """Whether the web app currently owns the scanner connection."""
    return _conn is not None


def _require_programming_session():
    """Require an explicit programming session before scanner operations."""
    if not _session_active():
        raise ConnectionError(
            "Start a programming session first. While active, the app may interrupt normal scanning."
        )
    return get_conn()

# Register cleanup handlers
atexit.register(safe_disconnect)

def _signal_handler(signum, frame):
    safe_disconnect()
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


@app.after_request
def _leave_program_mode_after_request(response):
    safe_exit_program_mode()
    return response


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BC125AT Scanner Tool v2</title>
<style>
:root {
    --bg: #0f1117;
    --bg2: #1a1d27;
    --bg3: #242836;
    --border: #2e3345;
    --text: #e4e6ef;
    --text2: #8b8fa3;
    --accent: #6c5ce7;
    --accent2: #a29bfe;
    --green: #00b894;
    --red: #e17055;
    --orange: #fdcb6e;
    --blue: #74b9ff;
    --radius: 10px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    min-height: 100vh;
}
.app {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}
/* Header */
.header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 24px;
}
.header h1 {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.5px;
}
.header h1 span { color: var(--accent2); }
.connection-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: var(--bg2);
    border-radius: 20px;
    font-size: 13px;
}
.connection-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
}
.connection-dot.disconnected { background: var(--red); box-shadow: 0 0 8px var(--red); }
.header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}
.session-banner {
    background: linear-gradient(135deg, rgba(116, 185, 255, 0.12), rgba(108, 92, 231, 0.12));
    border: 1px solid rgba(116, 185, 255, 0.25);
    border-radius: var(--radius);
    padding: 16px 18px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
}
.session-banner strong {
    display: block;
    margin-bottom: 4px;
}
.session-banner p {
    color: var(--text2);
    font-size: 13px;
}
.nav button.disabled {
    opacity: 0.45;
}
.nav button.disabled:hover {
    color: var(--text2);
    background: transparent;
}
/* Navigation */
.nav {
    display: flex;
    gap: 4px;
    background: var(--bg2);
    padding: 4px;
    border-radius: var(--radius);
    margin-bottom: 24px;
    overflow-x: auto;
}
.nav button {
    padding: 10px 20px;
    border: none;
    background: transparent;
    color: var(--text2);
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    white-space: nowrap;
    transition: all 0.2s;
}
.nav button:hover { color: var(--text); background: var(--bg3); }
.nav button.active { background: var(--accent); color: white; }
/* Panels */
.panel { display: none; }
.panel.active { display: block; }
/* Cards */
.card {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    margin-bottom: 16px;
}
.card h2 {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 16px;
    color: var(--accent2);
}
.card h3 {
    font-size: 14px;
    font-weight: 600;
    margin: 16px 0 8px;
    color: var(--text2);
}
/* Info Grid */
.info-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px;
}
.info-item {
    background: var(--bg3);
    padding: 14px;
    border-radius: 8px;
}
.info-item .label { font-size: 11px; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; }
.info-item .value { font-size: 18px; font-weight: 600; margin-top: 4px; }
/* Channel Table */
.channel-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
.channel-table th {
    text-align: left;
    padding: 10px 12px;
    background: var(--bg3);
    color: var(--text2);
    font-weight: 500;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    position: sticky;
    top: 0;
}
.channel-table td {
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
}
.channel-table tr:hover td { background: var(--bg3); }
.channel-table .freq { font-family: 'SF Mono', 'Menlo', monospace; color: var(--blue); font-weight: 500; }
.channel-table .empty { color: var(--text2); font-style: italic; }
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
}
.badge.lockout { background: rgba(225, 112, 85, 0.2); color: var(--red); }
.badge.priority { background: rgba(253, 203, 110, 0.2); color: var(--orange); }
.badge.mod { background: rgba(108, 92, 231, 0.15); color: var(--accent2); }
/* Bank Tabs */
.bank-tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 16px;
    flex-wrap: wrap;
}
.bank-tabs button {
    padding: 6px 16px;
    border: 1px solid var(--border);
    background: var(--bg3);
    color: var(--text2);
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    transition: all 0.2s;
}
.bank-tabs button:hover { border-color: var(--accent); color: var(--text); }
.bank-tabs button.active { background: var(--accent); color: white; border-color: var(--accent); }
/* Preset Cards */
.preset-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
}
.preset-card {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    cursor: pointer;
    transition: all 0.2s;
}
.preset-card:hover { border-color: var(--accent); transform: translateY(-1px); }
.preset-card .name { font-weight: 600; font-size: 15px; margin-bottom: 4px; }
.preset-card .desc { font-size: 12px; color: var(--text2); margin-bottom: 8px; }
.preset-card .meta { font-size: 11px; color: var(--accent2); }
/* Buttons */
.btn {
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.btn-primary { background: var(--accent); color: white; }
.btn-primary:hover { background: var(--accent2); }
.btn-secondary { background: var(--bg3); color: var(--text); border: 1px solid var(--border); }
.btn-secondary:hover { border-color: var(--accent); }
.btn-danger { background: rgba(225, 112, 85, 0.15); color: var(--red); border: 1px solid rgba(225, 112, 85, 0.3); }
.btn-success { background: rgba(0, 184, 148, 0.15); color: var(--green); border: 1px solid rgba(0, 184, 148, 0.3); }
.btn-sm { padding: 6px 12px; font-size: 12px; }
/* Forms */
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 12px; color: var(--text2); margin-bottom: 4px; }
.form-group input, .form-group select {
    width: 100%;
    padding: 8px 12px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-size: 14px;
}
.form-group textarea {
    width: 100%;
    min-height: 140px;
    padding: 10px 12px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-size: 14px;
    font-family: 'SF Mono', 'Menlo', monospace;
}
.form-group input:focus, .form-group select:focus { outline: none; border-color: var(--accent); }
.check-row {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 38px;
    margin-top: 22px;
    color: var(--text);
    font-size: 14px;
}
.check-row input[type="checkbox"] {
    width: auto;
    margin: 0;
}
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
/* Settings */
.setting-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid var(--border);
}
.setting-row:last-child { border-bottom: none; }
.setting-label { font-size: 14px; }
.setting-value { color: var(--accent2); font-weight: 500; }
.setting-value .inline-edit {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 13px;
    min-width: 140px;
}
.setting-value input.inline-edit {
    width: 160px;
}
.setting-help {
    color: var(--text2);
    font-size: 12px;
    margin-top: 10px;
}
.setting-section-title {
    margin: 18px 0 8px;
    color: var(--accent2);
    font-size: 14px;
    font-weight: 600;
}
.stack-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
/* Modal */
.modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.7);
    z-index: 100;
    align-items: center;
    justify-content: center;
}
.modal-overlay.active { display: flex; }
.modal {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    max-width: 500px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
}
.modal h2 { margin-bottom: 16px; }
.modal-actions { display: flex; gap: 8px; margin-top: 20px; justify-content: flex-end; }
/* Progress */
.progress-bar {
    height: 4px;
    background: var(--bg3);
    border-radius: 2px;
    overflow: hidden;
    margin-top: 8px;
}
.progress-bar .fill {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s;
    border-radius: 2px;
}
/* Toast */
.toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    padding: 12px 20px;
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 14px;
    z-index: 200;
    transition: all 0.3s;
    opacity: 0;
    transform: translateY(10px);
    max-width: min(520px, calc(100vw - 48px));
    white-space: normal;
    line-height: 1.4;
    cursor: pointer;
}
.toast.show { opacity: 1; transform: translateY(0); }
.toast.success { border-color: var(--green); }
.toast.error { border-color: var(--red); }
/* Loading spinner */
.spinner {
    display: inline-block;
    width: 16px; height: 16px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
/* Scrollable table container */
.table-container { max-height: 500px; overflow-y: auto; border-radius: 8px; }
/* Channel edit row */
.channel-table .editing td { background: var(--bg); }
.channel-table input.inline-edit {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 13px;
    width: 100%;
}
.channel-table select.inline-edit {
    background: var(--bg3);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 13px;
}
</style>
</head>
<body>
<div class="app">
    <div class="header">
        <h1><span>BC125AT</span> Scanner Tool</h1>
        <div class="header-actions">
            <div class="connection-badge">
                <div class="connection-dot disconnected" id="connDot"></div>
                <span id="connStatus">Scanner released</span>
            </div>
            <button class="btn btn-primary btn-sm" id="sessionBtn" onclick="toggleProgrammingSession()">Start Programming Session</button>
        </div>
    </div>

    <div class="session-banner">
        <div>
            <strong id="sessionBannerTitle">Programming session inactive</strong>
            <p id="sessionBannerText">The scanner is currently free to scan normally. Start a programming session before opening channels, settings, search, or import tools.</p>
        </div>
    </div>

    <nav class="nav">
        <button class="active" data-panel="dashboard" onclick="showPanel('dashboard', this)">Dashboard</button>
        <button data-panel="channels" onclick="showPanel('channels', this)">Channels</button>
        <button data-panel="presets" onclick="showPanel('presets', this)">Presets</button>
        <button data-panel="search" onclick="showPanel('search', this)">Search & Close Call</button>
        <button data-panel="settings" onclick="showPanel('settings', this)">Settings</button>
        <button data-panel="backup" onclick="showPanel('backup', this)">Backup & Import</button>
    </nav>

    <!-- DASHBOARD -->
    <div class="panel active" id="panel-dashboard">
        <div class="card">
            <h2>Scanner Info</h2>
            <div class="info-grid" id="infoGrid">
                <div class="info-item"><div class="label">Model</div><div class="value" id="infoModel">-</div></div>
                <div class="info-item"><div class="label">Firmware</div><div class="value" id="infoFirmware">-</div></div>
                <div class="info-item"><div class="label">Volume</div><div class="value" id="infoVolume">-</div></div>
                <div class="info-item"><div class="label">Squelch</div><div class="value" id="infoSquelch">-</div></div>
                <div class="info-item"><div class="label">Backlight</div><div class="value" id="infoBacklight">-</div></div>
                <div class="info-item"><div class="label">Priority</div><div class="value" id="infoPriority">-</div></div>
            </div>
        </div>
        <div class="card">
            <h2>Banks</h2>
            <div class="info-grid" id="bankGrid"></div>
        </div>
        <div class="card">
            <h2>Quick Stats</h2>
            <div class="info-grid">
                <div class="info-item"><div class="label">Programmed Channels</div><div class="value" id="statChannels">Open Channels tab</div></div>
                <div class="info-item"><div class="label">Programmed Banks</div><div class="value" id="statProgBanks">Open Channels tab</div></div>
                <div class="info-item"><div class="label">Enabled Banks</div><div class="value" id="statEnabledBanks">-</div></div>
                <div class="info-item"><div class="label">Close Call Mode</div><div class="value" id="statCC">-</div></div>
                <div class="info-item"><div class="label">Weather Alert</div><div class="value" id="statWX">-</div></div>
                <div class="info-item"><div class="label">Band Plan</div><div class="value" id="statBand">-</div></div>
            </div>
            <div class="setting-help">To avoid disturbing live scanner behavior, the dashboard no longer reads all 500 channels automatically.</div>
        </div>
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h2 style="margin-bottom:0">Status Snapshot</h2>
                <button class="btn btn-secondary btn-sm" onclick="loadLiveMonitor()">Refresh Snapshot</button>
            </div>
            <div class="info-grid">
                <div class="info-item"><div class="label">Frequency</div><div class="value" id="liveFreq">-</div></div>
                <div class="info-item"><div class="label">Modulation</div><div class="value" id="liveMod">-</div></div>
                <div class="info-item"><div class="label">Channel</div><div class="value" id="liveChannel">-</div></div>
                <div class="info-item"><div class="label">Name</div><div class="value" id="liveName">-</div></div>
                <div class="info-item"><div class="label">Squelch</div><div class="value" id="liveSql">-</div></div>
                <div class="info-item"><div class="label">Status</div><div class="value" id="liveStatus">-</div></div>
            </div>
            <div class="setting-help">This is a manual snapshot only. Continuous live control/status polling is intentionally disabled because it can interfere with normal scanning.</div>
        </div>
    </div>

    <!-- CHANNELS -->
    <div class="panel" id="panel-channels">
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h2 style="margin-bottom:0">Channel Editor</h2>
                <div style="display:flex;gap:8px;">
                    <button class="btn btn-primary btn-sm" onclick="showAddChannel()">+ Add Channel</button>
                    <button class="btn btn-danger btn-sm" onclick="clearCurrentBank()">Clear Current Bank</button>
                </div>
            </div>
            <div class="bank-tabs" id="bankTabs"></div>
            <div id="channelLoading" style="text-align:center;padding:40px;color:var(--text2);">
                <div class="spinner"></div> Loading channels...
            </div>
            <div class="table-container" id="channelTableContainer" style="display:none;">
                <table class="channel-table">
                    <thead>
                        <tr>
                            <th>CH</th>
                            <th>Name</th>
                            <th>Frequency</th>
                            <th>Mod</th>
                            <th>Tone</th>
                            <th>Delay</th>
                            <th>Flags</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="channelBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- PRESETS -->
    <div class="panel" id="panel-presets">
        <div class="card">
            <h2>Frequency Presets</h2>
            <p style="color:var(--text2);margin-bottom:16px;font-size:14px;">
                One-click loading of popular frequency sets. Select a preset and choose which bank to load it into.
            </p>
            <div class="preset-grid" id="presetGrid"></div>
        </div>
    </div>

    <!-- SEARCH -->
    <div class="panel" id="panel-search">
        <div class="card">
            <h2>Search & Close Call Settings</h2>
            <div id="searchContent">
                <div class="spinner"></div> Loading...
            </div>
        </div>
    </div>

    <!-- SETTINGS -->
    <div class="panel" id="panel-settings">
        <div class="card">
            <h2>Scanner Settings</h2>
            <div id="settingsContent">
                <div class="spinner"></div> Loading...
            </div>
        </div>
    </div>

    <!-- BACKUP -->
    <div class="panel" id="panel-backup">
        <div class="card">
            <h2>Backup & Export</h2>
            <p style="color:var(--text2);margin-bottom:16px;font-size:14px;">
                Save your scanner programming, settings, and search configuration to a file for safekeeping or transfer.
            </p>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <button class="btn btn-primary" onclick="doExport('json')">Export Channels (JSON)</button>
                <button class="btn btn-secondary" onclick="doExport('csv')">Export Channels (CSV)</button>
                <button class="btn btn-success" onclick="doExport('backup')">Full Backup (Channels + Settings + Search)</button>
                <button class="btn btn-secondary" onclick="doExport('bc125at_ss')">Export BC125AT Season File</button>
            </div>
        </div>
        <div class="card">
            <h2>Import & Restore</h2>
            <p style="color:var(--text2);margin-bottom:16px;font-size:14px;">
                Load channels from CSV/JSON, paste channel text directly, restore a full backup JSON file, or import a BC125AT season file.
            </p>
            <p style="color:var(--text2);margin-bottom:16px;font-size:13px;line-height:1.5;">
                Best option: export a sample from this app first, then match that format. The importer also accepts common aliases such as
                <code>channel_index</code>, <code>alpha_tag</code>, <code>freq</code>, and <code>ctcss_dcs</code>.
                JSON can be either a top-level list or an object with <code>channels</code>. Race CSV files with columns like
                <code>Car</code>, <code>Driver</code>, <code>Primary</code>, and <code>Secondary</code> are also supported.
                Pasted text can also be simple lines like
                <code>146.520 Simplex</code>.
            </p>
            <div class="form-row">
                <div class="form-group">
                    <label>Import Destination</label>
                    <select id="importBankTarget">
                        <option value="keep">Use channel numbers from file/text</option>
                        <option value="1">Load sequentially into Bank 1 (CH 1-50)</option>
                        <option value="2">Load sequentially into Bank 2 (CH 51-100)</option>
                        <option value="3">Load sequentially into Bank 3 (CH 101-150)</option>
                        <option value="4">Load sequentially into Bank 4 (CH 151-200)</option>
                        <option value="5">Load sequentially into Bank 5 (CH 201-250)</option>
                        <option value="6">Load sequentially into Bank 6 (CH 251-300)</option>
                        <option value="7">Load sequentially into Bank 7 (CH 301-350)</option>
                        <option value="8">Load sequentially into Bank 8 (CH 351-400)</option>
                        <option value="9">Load sequentially into Bank 9 (CH 401-450)</option>
                        <option value="0">Load sequentially into Bank 0 (CH 451-500)</option>
                    </select>
                </div>
                <div class="form-group">
                    <div class="check-row">
                        <input type="checkbox" id="importClearBank">
                        Clear destination bank first
                    </div>
                </div>
            </div>
            <input type="file" id="importFile" accept=".json,.csv,.bc125at_ss" style="display:none;" onchange="previewFileImport(this)">
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
                <button class="btn btn-secondary" onclick="document.getElementById('importFile').click()">Import File...</button>
                <button class="btn btn-primary" onclick="previewPasteImport()">Preview Pasted Text</button>
            </div>
            <textarea id="pasteImportText" rows="8" placeholder="Paste JSON, CSV with a header row, or simple lines like:
146.520 Simplex
147.435 Renegade
449.780 PAPA System"></textarea>
            <div id="importStatus" style="margin-top:12px;"></div>
        </div>
    </div>
</div>

<div class="modal-overlay" id="importPreviewModal">
    <div class="modal" style="max-width:760px;">
        <h2>Import Preview</h2>
        <p id="importPreviewSummary" style="color:var(--text2);font-size:13px;margin-bottom:16px;"></p>
        <div id="importPreviewList" style="max-height:280px;overflow-y:auto;margin-bottom:16px;"></div>
        <div class="modal-actions">
            <button class="btn btn-secondary" onclick="closeModal('importPreviewModal')">Cancel</button>
            <button class="btn btn-primary" id="importPreviewConfirmBtn" onclick="confirmImportPreview()">Import Now</button>
        </div>
    </div>
</div>

<!-- Preset Load Modal -->
<div class="modal-overlay" id="presetModal">
    <div class="modal">
        <h2 id="presetModalTitle">Load Preset</h2>
        <p id="presetModalDesc" style="color:var(--text2);font-size:13px;margin-bottom:16px;"></p>
        <div id="presetModalFreqs" style="max-height:200px;overflow-y:auto;margin-bottom:16px;"></div>
        <div class="form-group">
            <label>Load into Bank</label>
            <select id="presetBank">
                <option value="1">Bank 1 (CH 1-50)</option>
                <option value="2">Bank 2 (CH 51-100)</option>
                <option value="3">Bank 3 (CH 101-150)</option>
                <option value="4">Bank 4 (CH 151-200)</option>
                <option value="5">Bank 5 (CH 201-250)</option>
                <option value="6">Bank 6 (CH 251-300)</option>
                <option value="7">Bank 7 (CH 301-350)</option>
                <option value="8">Bank 8 (CH 351-400)</option>
                <option value="9">Bank 9 (CH 401-450)</option>
                <option value="0">Bank 0 (CH 451-500)</option>
            </select>
        </div>
        <div id="presetProgress" style="display:none;">
            <div style="color:var(--text2);font-size:13px;">Writing channels...</div>
            <div class="progress-bar"><div class="fill" id="presetProgressFill" style="width:0%"></div></div>
        </div>
        <div class="modal-actions">
            <button class="btn btn-secondary" onclick="closeModal('presetModal')">Cancel</button>
            <button class="btn btn-primary" id="presetLoadBtn" onclick="loadPreset()">Load Preset</button>
        </div>
    </div>
</div>

<!-- Add Channel Modal -->
<div class="modal-overlay" id="channelModal">
    <div class="modal">
        <h2 id="channelModalTitle">Program Channel</h2>
        <div class="form-row">
            <div class="form-group">
                <label>Channel Number (1-500)</label>
                <input type="number" id="chIndex" min="1" max="500" value="1">
            </div>
            <div class="form-group">
                <label>Frequency (MHz)</label>
                <input type="text" id="chFreq" placeholder="e.g. 155.0000">
            </div>
        </div>
        <div class="form-group">
            <label>Name (max 16 chars)</label>
            <input type="text" id="chName" maxlength="16" placeholder="Channel name">
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Modulation</label>
                <select id="chMod">
                    <option value="AUTO">AUTO</option>
                    <option value="AM">AM</option>
                    <option value="FM">FM</option>
                    <option value="NFM">NFM</option>
                </select>
            </div>
            <div class="form-group">
                <label>Delay (seconds)</label>
                <select id="chDelay">
                    <option value="-10">-10</option>
                    <option value="-5">-5</option>
                    <option value="0">0</option>
                    <option value="1">1</option>
                    <option value="2" selected>2</option>
                    <option value="3">3</option>
                    <option value="4">4</option>
                    <option value="5">5</option>
                </select>
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>CTCSS/DCS Tone</label>
                <select id="chTone"><option value="0">None</option></select>
            </div>
            <div class="form-group" style="display:flex;gap:16px;align-items:end;padding-bottom:2px;">
                <label><input type="checkbox" id="chLockout"> Lockout</label>
                <label><input type="checkbox" id="chPriority"> Priority</label>
            </div>
        </div>
        <div class="modal-actions">
            <button class="btn btn-secondary" onclick="closeModal('channelModal')">Cancel</button>
            <button class="btn btn-primary" onclick="saveChannel()">Save Channel</button>
        </div>
    </div>
</div>

<div class="toast" id="toast"></div>

<script>
// State
let currentBank = 1;
let selectedPreset = null;
let channels = {};
let activePanel = 'dashboard';
let pendingImportPreview = null;
let sessionActive = false;
let toastTimer = null;

// --- Navigation ---
function showPanel(name, button=null) {
    if (name !== 'dashboard' && !sessionActive) {
        toast('Start a programming session first', 'error');
        return;
    }
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));
    document.getElementById('panel-' + name).classList.add('active');
    activePanel = name;

    const targetButton = button || document.querySelector('.nav button[data-panel="' + name + '"]');
    if (targetButton) targetButton.classList.add('active');

    if (name === 'dashboard') loadDashboard();
    if (name === 'channels') loadBank(currentBank);
    if (name === 'presets') loadPresets();
    if (name === 'search') loadSearch();
    if (name === 'settings') loadSettings();
}

// --- Toast ---
function toast(msg, type='success') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast show ' + type;
    t.title = type === 'error' ? 'Click to dismiss' : '';
    if (toastTimer) clearTimeout(toastTimer);
    const duration = type === 'error' ? 12000 : 3000;
    toastTimer = setTimeout(() => {
        t.className = 'toast';
        toastTimer = null;
    }, duration);
}

document.getElementById('toast').addEventListener('click', () => {
    const t = document.getElementById('toast');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = null;
    t.className = 'toast';
});

// --- Modal ---
function closeModal(id) {
    document.getElementById(id).classList.remove('active');
    if (id === 'importPreviewModal') pendingImportPreview = null;
}

function importRefreshViews(message) {
    document.getElementById('importStatus').innerHTML = '<span style="color:var(--green)">' + message + '</span>';
    toast(message);
    loadDashboard();
    if (activePanel === 'channels') loadBank(currentBank);
    if (activePanel === 'search') loadSearch();
    if (activePanel === 'settings') loadSettings();
}

function renderImportPreview(preview) {
    pendingImportPreview = preview;
    let summary = preview.count + ' ' + preview.kind + ' ready. Destination: ' + preview.destination + '.';
    if (preview.truncated) {
        summary += ' ' + preview.truncated + ' channel' + (preview.truncated === 1 ? ' was' : 's were') + ' skipped because a bank only holds 50.';
    }
    document.getElementById('importPreviewSummary').textContent = summary;

    let html = '<table class="channel-table"><thead><tr><th>CH</th><th>Name</th><th>Freq</th><th>Mode</th><th>Tone</th><th>Bank</th></tr></thead><tbody>';
    for (const ch of preview.preview_items) {
        const freq = ch.frequency == null ? '' : Number(ch.frequency).toFixed(4);
        html += '<tr>' +
            '<td>' + ch.channel + '</td>' +
            '<td>' + (ch.name || '') + '</td>' +
            '<td>' + freq + '</td>' +
            '<td>' + (ch.modulation || '') + '</td>' +
            '<td>' + (ch.tone || '') + '</td>' +
            '<td>' + ch.bank + '</td>' +
            '</tr>';
    }
    if (preview.count > preview.preview_items.length) {
        html += '<tr><td colspan="6" style="color:var(--text2);font-style:italic;">Showing first ' + preview.preview_items.length + ' of ' + preview.count + ' channels</td></tr>';
    }
    html += '</tbody></table>';
    document.getElementById('importPreviewList').innerHTML = html;
    document.getElementById('importPreviewModal').classList.add('active');
}

function currentImportOptions() {
    return {
        bank_target: document.getElementById('importBankTarget').value,
        clear_bank_first: document.getElementById('importClearBank').checked
    };
}

function updateSessionUI(state) {
    sessionActive = Boolean(state.active);
    const dot = document.getElementById('connDot');
    const status = document.getElementById('connStatus');
    const btn = document.getElementById('sessionBtn');
    const title = document.getElementById('sessionBannerTitle');
    const text = document.getElementById('sessionBannerText');

    if (sessionActive) {
        dot.classList.remove('disconnected');
        status.textContent = state.model ? (state.model + ' connected for programming') : 'Programming session active';
        btn.textContent = 'Release Scanner';
        btn.className = 'btn btn-secondary btn-sm';
        title.textContent = 'Programming session active';
        text.textContent = 'The app currently owns the scanner connection. While active, opening tabs and editing data may interrupt normal scanning or leave the radio on hold between requests.';
    } else {
        dot.classList.add('disconnected');
        status.textContent = 'Scanner released';
        btn.textContent = 'Start Programming Session';
        btn.className = 'btn btn-primary btn-sm';
        title.textContent = 'Programming session inactive';
        text.textContent = 'The scanner is currently free to scan normally. Start a programming session before opening channels, settings, search, or import tools.';
    }

    document.querySelectorAll('.nav button[data-panel]').forEach(button => {
        if (button.dataset.panel === 'dashboard') return;
        button.classList.toggle('disabled', !sessionActive);
    });

    if (!sessionActive && activePanel !== 'dashboard') {
        showPanel('dashboard');
    }
}

async function refreshSessionState(showToast=false) {
    try {
        const resp = await fetch('/api/session');
        const data = await resp.json();
        updateSessionUI(data);
        if (showToast) {
            toast(sessionActive ? 'Programming session started' : 'Scanner released');
        }
    } catch (e) {
        updateSessionUI({ active: false });
        if (showToast) toast('Could not read scanner session state', 'error');
    }
}

async function toggleProgrammingSession() {
    try {
        const resp = await fetch('/api/session/' + (sessionActive ? 'stop' : 'start'), {
            method: 'POST'
        });
        const data = await resp.json();
        if (data.error) {
            toast(data.error, 'error');
            return;
        }
        updateSessionUI(data);
        toast(sessionActive ? 'Programming session started' : 'Scanner released');
        if (sessionActive || activePanel === 'dashboard') {
            loadDashboard();
        }
    } catch (e) {
        toast('Could not change programming session', 'error');
    }
}

// --- API Helper ---
async function api(endpoint, opts={}) {
    try {
        const resp = await fetch('/api/' + endpoint, {
            method: opts.method || 'GET',
            headers: opts.body ? {'Content-Type': 'application/json'} : {},
            body: opts.body ? JSON.stringify(opts.body) : undefined,
        });
        const data = await resp.json();
        if (data.error) { toast(data.error, 'error'); return null; }
        return data;
    } catch(e) {
        toast('Connection error: ' + e.message, 'error');
        return null;
    }
}

// --- Dashboard ---
async function loadDashboard() {
    if (!sessionActive) {
        document.getElementById('infoModel').textContent = '-';
        document.getElementById('infoFirmware').textContent = '-';
        document.getElementById('infoVolume').textContent = '-';
        document.getElementById('infoSquelch').textContent = '-';
        document.getElementById('infoBacklight').textContent = '-';
        document.getElementById('infoPriority').textContent = '-';
        document.getElementById('statEnabledBanks').textContent = '-';
        document.getElementById('statCC').textContent = '-';
        document.getElementById('statWX').textContent = '-';
        document.getElementById('statBand').textContent = '-';
        document.getElementById('liveFreq').textContent = '-';
        document.getElementById('liveMod').textContent = '-';
        document.getElementById('liveChannel').textContent = '-';
        document.getElementById('liveName').textContent = '-';
        document.getElementById('liveSql').textContent = '-';
        document.getElementById('liveStatus').textContent = 'Scanner released';
        document.getElementById('bankGrid').innerHTML = '';
        return;
    }
    const data = await api('info');
    if (!data) return;

    document.getElementById('infoModel').textContent = data.model;
    document.getElementById('infoFirmware').textContent = data.firmware;
    document.getElementById('infoVolume').textContent = data.settings.volume + '/15';
    document.getElementById('infoSquelch').textContent = data.settings.squelch + '/15';
    document.getElementById('infoBacklight').textContent = data.settings.backlight_display;
    document.getElementById('infoPriority').textContent = data.settings.priority_display;

    document.getElementById('statCC').textContent = data.close_call_mode || '-';
    document.getElementById('statWX').textContent = data.settings.weather_alert ? 'On' : 'Off';
    document.getElementById('statBand').textContent = data.settings.band_plan_display;
    document.getElementById('statEnabledBanks').textContent = data.enabled_banks;

    // Banks
    const bg = document.getElementById('bankGrid');
    bg.innerHTML = '';
    for (const bank of [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]) {
        const enabled = Boolean(data.banks[bank]);
        const div = document.createElement('div');
        div.className = 'info-item';
        div.innerHTML = '<div class="label">Bank ' + bank + '</div>' +
            '<div class="value" style="color:' + (enabled ? 'var(--green)' : 'var(--red)') + '">' +
            (enabled ? 'Enabled' : 'Disabled') + '</div>' +
            '<div style="color:var(--text2);font-size:12px;margin-top:6px;">Use the Channels tab to read exact contents for this bank</div>' +
            '<div style="margin-top:10px;"><button class="btn btn-sm ' + (enabled ? 'btn-danger' : 'btn-success') +
            '" onclick="setBankEnabled(' + bank + ',' + (!enabled) + ')">' + (enabled ? 'Disable' : 'Enable') + '</button> ' +
            '<button class="btn btn-sm btn-secondary" onclick="clearBank(' + bank + ')">Clear</button></div>';
        bg.appendChild(div);
    }
}

async function setBankEnabled(bank, enabled) {
    const result = await api('banks/set', { method: 'POST', body: { bank: bank, enabled: enabled } });
    if (result) {
        toast('Bank ' + bank + ' ' + (enabled ? 'enabled' : 'disabled'));
        loadDashboard();
    }
}

async function clearBank(bank) {
    if (!confirm('Clear all 50 channels in Bank ' + bank + '?')) return;
    const result = await api('banks/clear', { method: 'POST', body: { bank: bank } });
    if (result) {
        toast('Bank ' + bank + ' cleared');
        loadDashboard();
        if (currentBank === bank) loadBank(bank);
    }
}

function clearCurrentBank() {
    clearBank(currentBank);
}

async function loadLiveMonitor() {
    if (!sessionActive) {
        toast('Start a programming session first', 'error');
        return;
    }
    const data = await api('live');
    if (!data) return;
    document.getElementById('liveFreq').textContent = data.frequency || '-';
    document.getElementById('liveMod').textContent = data.modulation || '-';
    document.getElementById('liveChannel').textContent = data.channel || '-';
    document.getElementById('liveName').textContent = data.name || '-';
    document.getElementById('liveSql').textContent = data.squelch_open ? 'Open' : 'Closed';
    document.getElementById('liveStatus').textContent = data.status || '-';

}

// --- Channels ---
function initBankTabs() {
    const container = document.getElementById('bankTabs');
    container.innerHTML = '';
    for (let i = 1; i <= 10; i++) {
        const bank = i % 10;
        const btn = document.createElement('button');
        btn.textContent = 'Bank ' + (bank || '0');
        btn.onclick = () => loadBank(bank);
        if (bank === currentBank) btn.classList.add('active');
        container.appendChild(btn);
    }
}

async function loadBank(bank) {
    currentBank = bank;
    initBankTabs();
    document.getElementById('channelLoading').style.display = 'block';
    document.getElementById('channelTableContainer').style.display = 'none';

    const data = await api('channels/bank/' + bank);
    if (!data) return;

    document.getElementById('channelLoading').style.display = 'none';
    document.getElementById('channelTableContainer').style.display = 'block';

    const body = document.getElementById('channelBody');
    body.innerHTML = '';
    data.channels.forEach(ch => {
        channels[ch.channel] = ch;
        const tr = document.createElement('tr');
        const isEmpty = !ch.frequency;
        tr.innerHTML =
            '<td>' + ch.channel + '</td>' +
            '<td>' + (ch.name || (isEmpty ? '<span class="empty">empty</span>' : '')) + '</td>' +
            '<td class="freq">' + (ch.frequency ? ch.frequency.toFixed(4) + ' MHz' : '') + '</td>' +
            '<td>' + (isEmpty ? '' : '<span class="badge mod">' + ch.modulation + '</span>') + '</td>' +
            '<td>' + (isEmpty ? '' : ch.tone) + '</td>' +
            '<td>' + (isEmpty ? '' : ch.delay + 's') + '</td>' +
            '<td>' +
                (ch.lockout ? '<span class="badge lockout">L/O</span> ' : '') +
                (ch.priority ? '<span class="badge priority">PRI</span>' : '') +
            '</td>' +
            '<td>' +
                (isEmpty ?
                    '<button class="btn btn-sm btn-secondary" onclick="editChannel(' + ch.channel + ')">Program</button>' :
                    '<button class="btn btn-sm btn-secondary" onclick="editChannel(' + ch.channel + ')">Edit</button> ' +
                    '<button class="btn btn-sm btn-danger" onclick="deleteChannel(' + ch.channel + ')">Del</button>'
                ) +
            '</td>';
        body.appendChild(tr);
    });
}

function showAddChannel() {
    document.getElementById('channelModalTitle').textContent = 'Program Channel';
    const start = currentBank === 0 ? 451 : (currentBank - 1) * 50 + 1;
    document.getElementById('chIndex').value = start;
    document.getElementById('chFreq').value = '';
    document.getElementById('chName').value = '';
    document.getElementById('chMod').value = 'AUTO';
    document.getElementById('chDelay').value = '2';
    document.getElementById('chTone').value = '0';
    document.getElementById('chLockout').checked = false;
    document.getElementById('chPriority').checked = false;
    document.getElementById('channelModal').classList.add('active');
}

function editChannel(idx) {
    const ch = channels[idx];
    document.getElementById('channelModalTitle').textContent = 'Edit Channel ' + idx;
    document.getElementById('chIndex').value = idx;
    document.getElementById('chFreq').value = ch.frequency ? ch.frequency.toFixed(4) : '';
    document.getElementById('chName').value = ch.name || '';
    document.getElementById('chMod').value = ch.modulation || 'AUTO';
    document.getElementById('chDelay').value = ch.delay || 2;
    document.getElementById('chTone').value = ch.tone_code || 0;
    document.getElementById('chLockout').checked = ch.lockout;
    document.getElementById('chPriority').checked = ch.priority;
    document.getElementById('channelModal').classList.add('active');
}

async function saveChannel() {
    const channelValue = parseInt(document.getElementById('chIndex').value, 10);
    const frequencyRaw = document.getElementById('chFreq').value.trim();
    const frequencyValue = parseFloat(frequencyRaw);
    const nameValue = document.getElementById('chName').value.trim();

    if (!Number.isInteger(channelValue) || channelValue < 1 || channelValue > 500) {
        toast('Channel must be between 1 and 500', 'error');
        return;
    }
    if (!frequencyRaw || Number.isNaN(frequencyValue)) {
        toast('Enter a valid frequency in MHz', 'error');
        return;
    }
    if (nameValue.length > 16) {
        toast('Channel name must be 16 characters or fewer', 'error');
        return;
    }

    const data = {
        channel: channelValue,
        frequency: frequencyValue,
        name: nameValue,
        modulation: document.getElementById('chMod').value,
        delay: parseInt(document.getElementById('chDelay').value),
        tone_code: parseInt(document.getElementById('chTone').value),
        lockout: document.getElementById('chLockout').checked,
        priority: document.getElementById('chPriority').checked,
    };
    const result = await api('channels/set', { method: 'POST', body: data });
    if (result) {
        toast('Channel ' + data.channel + ' saved');
        closeModal('channelModal');
        loadBank(currentBank);
    }
}

async function deleteChannel(idx) {
    if (!confirm('Delete channel ' + idx + '?')) return;
    const result = await api('channels/delete/' + idx, { method: 'POST' });
    if (result) {
        toast('Channel ' + idx + ' deleted');
        loadBank(currentBank);
    }
}

// --- Presets ---
async function loadPresets() {
    const data = await api('presets');
    if (!data) return;
    const grid = document.getElementById('presetGrid');
    grid.innerHTML = '';
    Object.entries(data).forEach(([key, preset]) => {
        const card = document.createElement('div');
        card.className = 'preset-card';
        card.onclick = () => showPresetModal(key, preset);
        card.innerHTML =
            '<div class="name">' + preset.name + '</div>' +
            '<div class="desc">' + preset.description + '</div>' +
            '<div class="meta">' + preset.channel_count + ' channels &middot; Suggested: Bank ' + preset.bank_suggestion + '</div>';
        grid.appendChild(card);
    });
}

async function showPresetModal(key, info) {
    selectedPreset = key;
    document.getElementById('presetModalTitle').textContent = info.name;
    document.getElementById('presetModalDesc').textContent = info.description;
    document.getElementById('presetBank').value = info.bank_suggestion;
    document.getElementById('presetProgress').style.display = 'none';
    document.getElementById('presetLoadBtn').disabled = false;

    const data = await api('presets/' + key);
    if (data) {
        const div = document.getElementById('presetModalFreqs');
        div.innerHTML = '<table class="channel-table" style="font-size:12px;"><thead><tr><th>#</th><th>Name</th><th>Frequency</th></tr></thead><tbody>' +
            data.frequencies.map((f, i) =>
                '<tr><td>' + (i+1) + '</td><td>' + f[0] + '</td><td class="freq">' + f[1].toFixed(4) + ' MHz</td></tr>'
            ).join('') + '</tbody></table>';
    }
    document.getElementById('presetModal').classList.add('active');
}

async function loadPreset() {
    const bank = parseInt(document.getElementById('presetBank').value);
    document.getElementById('presetProgress').style.display = 'block';
    document.getElementById('presetLoadBtn').disabled = true;
    document.getElementById('presetProgressFill').style.width = '0%';

    const result = await api('presets/load', {
        method: 'POST',
        body: { preset: selectedPreset, bank: bank }
    });

    document.getElementById('presetProgressFill').style.width = '100%';
    if (result) {
        toast(result.message);
        setTimeout(() => closeModal('presetModal'), 500);
    }
    document.getElementById('presetLoadBtn').disabled = false;
}

// --- Search ---
async function loadSearch() {
    const data = await api('search');
    if (!data) return;
    const c = document.getElementById('searchContent');
    let html = '';

    function dropdownRow(label, id, options, currentVal) {
        const opts = options.map(o =>
            '<option value="' + o.v + '"' + (String(currentVal) === String(o.v) ? ' selected' : '') + '>' + o.l + '</option>'
        ).join('');
        return '<div class="setting-row"><div class="setting-label">' + label + '</div><div class="setting-value"><select id="' + id + '" class="inline-edit">' + opts + '</select></div></div>';
    }

    html += '<div class="setting-section-title">Search</div>';
    html += dropdownRow('Search Delay', 'searchDelay', data.delay_options.map(v => ({ v: v, l: v + ' sec' })), data.delay);
    html += dropdownRow('CTCSS/DCS Code Search', 'searchCode', [{ v: 0, l: 'Off' }, { v: 1, l: 'On' }], data.code_search ? 1 : 0);

    html += '<div class="setting-section-title">Close Call</div>';
    html += dropdownRow('Mode', 'ccMode', Object.entries(data.close_call.mode_options).map(([v, l]) => ({ v: v, l: l })), data.close_call.mode);
    html += dropdownRow('Alert Beep', 'ccBeep', [{ v: 0, l: 'Off' }, { v: 1, l: 'On' }], data.close_call.alert_beep ? 1 : 0);
    html += dropdownRow('Alert Light', 'ccLight', [{ v: 0, l: 'Off' }, { v: 1, l: 'On' }], data.close_call.alert_light ? 1 : 0);
    html += dropdownRow('Temporary Lockout', 'ccLockout', [{ v: 0, l: 'Off' }, { v: 1, l: 'On' }], data.close_call.lockout ? 1 : 0);

    html += '<div class="setting-section-title">Close Call Bands</div>';
    data.close_call.bands.forEach((enabled, i) => {
        html += dropdownRow(data.close_call.band_labels[i], 'ccBand' + i, [{ v: 0, l: 'Off' }, { v: 1, l: 'On' }], enabled ? 1 : 0);
    });

    html += '<div class="setting-section-title">Service Search Groups</div>';
    Object.entries(data.service_groups).forEach(([name, enabled], idx) => {
        html += dropdownRow(name, 'serviceGroup' + idx, [{ v: 0, l: 'Off' }, { v: 1, l: 'On' }], enabled ? 1 : 0);
    });

    html += '<div class="setting-section-title">Custom Search Groups</div>';
    Object.entries(data.custom_groups).sort((a, b) => Number(a[0]) - Number(b[0])).forEach(([group, enabled]) => {
        html += dropdownRow('Group ' + group, 'customGroup' + group, [{ v: 0, l: 'Off' }, { v: 1, l: 'On' }], enabled ? 1 : 0);
    });

    html += '<div class="setting-section-title">Custom Search Ranges</div>';
    data.search_ranges.forEach(r => {
        html += '<div class="setting-row"><div class="setting-label">Range ' + r.index + '</div><div class="setting-value">' +
            '<input id="rangeLower' + r.index + '" class="inline-edit" type="number" step="0.0001" value="' + r.lower.toFixed(4) + '">' +
            ' <input id="rangeUpper' + r.index + '" class="inline-edit" type="number" step="0.0001" value="' + r.upper.toFixed(4) + '">' +
            ' <button class="btn btn-sm btn-secondary" onclick="saveSearchRange(' + r.index + ')">Save</button></div></div>';
    });

    html += '<div class="setting-section-title">Global Lockout Frequencies</div>';
    html += '<div class="setting-row"><div class="setting-label">Add Frequency</div><div class="setting-value">' +
        '<input id="newLockoutFreq" class="inline-edit" type="number" step="0.0001" placeholder="155.2500">' +
        ' <button class="btn btn-sm btn-secondary" onclick="addLockoutFrequency()">Add</button></div></div>';
    if (data.lockout_frequencies.length) {
        data.lockout_frequencies.forEach(freq => {
            html += '<div class="setting-row"><div class="setting-label">' + freq.toFixed(4) + ' MHz</div><div class="setting-value">' +
                '<button class="btn btn-sm btn-danger" onclick="removeLockoutFrequency(' + freq + ')">Remove</button></div></div>';
        });
    } else {
        html += '<div class="setting-help">No global lockout frequencies are currently stored.</div>';
    }

    c.innerHTML = html;

    document.getElementById('searchDelay').addEventListener('change', (e) => saveSearchSetting('delay', e.target.value));
    document.getElementById('searchCode').addEventListener('change', (e) => saveSearchSetting('code_search', e.target.value));
    document.getElementById('ccMode').addEventListener('change', (e) => saveSearchSetting('cc_mode', e.target.value));
    document.getElementById('ccBeep').addEventListener('change', (e) => saveSearchSetting('cc_alert_beep', e.target.value));
    document.getElementById('ccLight').addEventListener('change', (e) => saveSearchSetting('cc_alert_light', e.target.value));
    document.getElementById('ccLockout').addEventListener('change', (e) => saveSearchSetting('cc_lockout', e.target.value));
    data.close_call.bands.forEach((enabled, i) => {
        document.getElementById('ccBand' + i).addEventListener('change', (e) => saveCloseCallBand(i, e.target.value));
    });
    Object.entries(data.service_groups).forEach(([name], idx) => {
        document.getElementById('serviceGroup' + idx).addEventListener('change', (e) => saveServiceGroup(name, e.target.value));
    });
    Object.keys(data.custom_groups).forEach(group => {
        document.getElementById('customGroup' + group).addEventListener('change', (e) => saveCustomGroup(group, e.target.value));
    });
}

async function saveSearchSetting(setting, value) {
    const result = await api('search/set', { method: 'POST', body: { setting: setting, value: value } });
    if (result) {
        toast('Search setting updated');
        loadSearch();
        loadDashboard();
    }
}

async function saveCloseCallBand(index, value) {
    const result = await api('search/closecall-band', { method: 'POST', body: { index: index, enabled: String(value) === '1' } });
    if (result) {
        toast('Close Call band updated');
        loadSearch();
        loadDashboard();
    }
}

async function saveServiceGroup(name, value) {
    const result = await api('search/service-group', { method: 'POST', body: { name: name, enabled: String(value) === '1' } });
    if (result) {
        toast('Service search group updated');
        loadSearch();
    }
}

async function saveCustomGroup(group, value) {
    const result = await api('search/custom-group', { method: 'POST', body: { group: Number(group), enabled: String(value) === '1' } });
    if (result) {
        toast('Custom search group updated');
        loadSearch();
    }
}

async function saveSearchRange(index) {
    const lower = document.getElementById('rangeLower' + index).value;
    const upper = document.getElementById('rangeUpper' + index).value;
    if (!lower || !upper || Number(lower) >= Number(upper)) {
        toast('Enter a valid lower and upper range', 'error');
        return;
    }
    const result = await api('search/range', { method: 'POST', body: { index: index, lower: lower, upper: upper } });
    if (result) {
        toast('Search range ' + index + ' updated');
        loadSearch();
    }
}

async function addLockoutFrequency() {
    const input = document.getElementById('newLockoutFreq');
    const frequency = input.value;
    if (!frequency || Number(frequency) <= 0) {
        toast('Enter a valid lockout frequency', 'error');
        return;
    }
    const result = await api('search/lockout', { method: 'POST', body: { frequency: frequency } });
    if (result) {
        toast('Lockout frequency added');
        input.value = '';
        loadSearch();
    }
}

async function removeLockoutFrequency(frequency) {
    const result = await fetch('/api/search/lockout', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frequency: frequency }),
    });
    const data = await result.json();
    if (data.error) {
        toast(data.error, 'error');
        return;
    }
    toast('Lockout frequency removed');
    loadSearch();
}

// --- Settings ---
async function loadSettings() {
    const data = await api('settings');
    if (!data) return;
    const c = document.getElementById('settingsContent');
    let html = '';

    // Helper: build a slider row
    function slider(label, id, min, max, val, spanId) {
        return '<div class="setting-row"><div class="setting-label">'+label+'</div><div class="setting-value">' +
            '<input type="range" min="'+min+'" max="'+max+'" value="'+val+'" id="'+id+'">' +
            ' <span id="'+spanId+'">'+val+'</span>/'+max+'</div></div>';
    }
    function dropdown(label, id, options, currentVal) {
        let opts = options.map(o =>
            '<option value="'+o.v+'"'+(String(currentVal)===String(o.v)?' selected':'')+'>'+o.l+'</option>'
        ).join('');
        return '<div class="setting-row"><div class="setting-label">'+label+'</div><div class="setting-value">' +
            '<select id="'+id+'" class="inline-edit">'+opts+'</select></div></div>';
    }

    // Volume slider
    html += slider('Volume', 'setVolume', 0, 15, data.volume, 'volVal');

    // Squelch slider
    html += slider('Squelch', 'setSquelch', 0, 15, data.squelch, 'sqlVal');

    // Contrast slider
    html += slider('Contrast', 'setContrast', 1, 15, data.contrast, 'cntVal');

    // Backlight dropdown
    html += dropdown('Backlight', 'setBacklight', [
        {v:'AF',l:'Always Off'},{v:'KY',l:'Keypress'},{v:'SQ',l:'Squelch'},{v:'KS',l:'Key+Squelch'},{v:'AO',l:'Always On'}
    ], data.backlight);

    // Priority dropdown
    html += dropdown('Priority Mode', 'setPriority', [
        {v:0,l:'Off'},{v:1,l:'On'},{v:2,l:'Plus On'},{v:3,l:'Do Not Disturb'}
    ], data.priority_mode);

    // Weather Alert toggle
    html += dropdown('Weather Alert', 'setWxAlert', [
        {v:0,l:'Off'},{v:1,l:'On'}
    ], data.weather_alert ? 1 : 0);

    // Key Beep toggle
    html += dropdown('Key Beep', 'setKeyBeep', [
        {v:0,l:'Auto'},{v:99,l:'Off'}
    ], data.key_beep_level);

    // Key Lock toggle
    html += dropdown('Key Lock', 'setKeyLock', [
        {v:0,l:'Off'},{v:1,l:'On'}
    ], data.key_lock ? 1 : 0);

    // Band Plan dropdown
    html += dropdown('Band Plan', 'setBandPlan', [
        {v:0,l:'USA'},{v:1,l:'Canada'}
    ], data.band_plan);

    // Battery charge timer dropdown
    html += dropdown('Battery Timer', 'setBatteryTimer', [
        {v:1,l:'1 hour'},{v:2,l:'2 hours'},{v:3,l:'3 hours'},{v:4,l:'4 hours'},
        {v:5,l:'5 hours'},{v:6,l:'6 hours'},{v:7,l:'7 hours'},{v:8,l:'8 hours'},
        {v:9,l:'9 hours'},{v:10,l:'10 hours'},{v:11,l:'11 hours'},{v:12,l:'12 hours'},
        {v:13,l:'13 hours'},{v:14,l:'14 hours'},{v:15,l:'15 hours'},{v:16,l:'16 hours'}
    ], data.battery_charge_time);

    // Current values
    html += '<div class="setting-row"><div class="setting-label">Current Backlight</div><div class="setting-value">' + data.backlight_display + '</div></div>';
    html += '<div class="setting-row"><div class="setting-label">Current Priority</div><div class="setting-value">' + data.priority_display + '</div></div>';
    html += '<div class="setting-row"><div class="setting-label">Current Key Beep</div><div class="setting-value">' + data.key_beep_display + '</div></div>';

    c.innerHTML = html;

    function bindSlider(inputId, valueId, settingKey) {
        const input = document.getElementById(inputId);
        const value = document.getElementById(valueId);
        if (!input || !value) return;
        input.addEventListener('input', () => {
            value.textContent = input.value;
        });
        input.addEventListener('change', () => saveSetting(settingKey, input.value));
    }

    function bindSelect(id, settingKey) {
        const select = document.getElementById(id);
        if (!select) return;
        select.addEventListener('change', () => saveSetting(settingKey, select.value));
    }

    bindSlider('setVolume', 'volVal', 'volume');
    bindSlider('setSquelch', 'sqlVal', 'squelch');
    bindSlider('setContrast', 'cntVal', 'contrast');
    bindSelect('setBacklight', 'backlight');
    bindSelect('setPriority', 'priority');
    bindSelect('setWxAlert', 'wxalert');
    bindSelect('setKeyBeep', 'keybeep');
    bindSelect('setKeyLock', 'keylock');
    bindSelect('setBandPlan', 'bandplan');
    bindSelect('setBatteryTimer', 'battery');
}

async function saveSetting(key, value) {
    const result = await api('settings/set', { method: 'POST', body: { setting: key, value: value } });
    if (result && !result.error) {
        const labels = {
            volume: 'Volume',
            squelch: 'Squelch',
            contrast: 'Contrast',
            backlight: 'Backlight',
            priority: 'Priority',
            wxalert: 'Weather alert',
            keybeep: 'Key beep',
            keylock: 'Key lock',
            bandplan: 'Band plan',
            battery: 'Battery timer',
        };
        toast((labels[key] || key) + ' updated');
        loadDashboard();
        loadSettings();
    }
}

// --- Export ---
async function doExport(format) {
    toast('Exporting... this reads all 500 channels', 'success');
    const resp = await fetch('/api/export/' + format);
    if (resp.ok) {
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const fallbackExt = format === 'csv' ? 'csv' : (format === 'bc125at_ss' ? 'bc125at_ss' : 'json');
        a.download = resp.headers.get('Content-Disposition')?.split('filename=')[1] || ('bc125at_export.' + fallbackExt);
        a.click();
        URL.revokeObjectURL(url);
        toast('Export complete!');
    } else {
        toast('Export failed', 'error');
    }
}

// --- Import ---
async function previewFileImport(input) {
    const file = input.files[0];
    if (!file) return;
    if (!/(?:[.]json|[.]csv|[.]bc125at_ss)$/i.test(file.name)) {
        document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">Only CSV, JSON, and BC125AT season files are supported</span>';
        input.value = '';
        return;
    }
    const formData = new FormData();
    formData.append('file', file);
    const options = currentImportOptions();
    formData.append('bank_target', options.bank_target);
    formData.append('clear_bank_first', options.clear_bank_first ? '1' : '0');
    document.getElementById('importStatus').innerHTML = '<div class="spinner"></div> Building preview...';
    try {
        const resp = await fetch('/api/import/preview', { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.error) {
            document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">' + data.error + '</span>';
        } else {
            document.getElementById('importStatus').innerHTML = '<span style="color:var(--green)">Preview ready. Confirm to write channels.</span>';
            renderImportPreview({ ...data, source: 'file' });
        }
    } catch(e) {
        document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">Preview failed</span>';
    }
}

async function previewPasteImport() {
    const text = document.getElementById('pasteImportText').value;
    if (!text.trim()) {
        document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">Paste some import text first</span>';
        return;
    }
    document.getElementById('importStatus').innerHTML = '<div class="spinner"></div> Building preview...';
    try {
        const resp = await fetch('/api/import/text/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                ...currentImportOptions()
            })
        });
        const data = await resp.json();
        if (data.error) {
            document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">' + data.error + '</span>';
        } else {
            document.getElementById('importStatus').innerHTML = '<span style="color:var(--green)">Preview ready. Confirm to write channels.</span>';
            renderImportPreview({ ...data, source: 'text' });
        }
    } catch (e) {
        document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">Preview failed</span>';
    }
}

async function confirmImportPreview() {
    if (!pendingImportPreview) return;
    const confirmBtn = document.getElementById('importPreviewConfirmBtn');
    confirmBtn.disabled = true;
    document.getElementById('importStatus').innerHTML = '<div class="spinner"></div> Importing...';
    try {
        let resp;
        if (pendingImportPreview.source === 'file') {
            const file = document.getElementById('importFile').files[0];
            if (!file) throw new Error('Select a file again before importing');
            const formData = new FormData();
            formData.append('file', file);
            const options = currentImportOptions();
            formData.append('bank_target', options.bank_target);
            formData.append('clear_bank_first', options.clear_bank_first ? '1' : '0');
            resp = await fetch('/api/import', { method: 'POST', body: formData });
        } else {
            resp = await fetch('/api/import/text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: document.getElementById('pasteImportText').value,
                    ...currentImportOptions()
                })
            });
        }
        const data = await resp.json();
        if (data.error) {
            document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">' + data.error + '</span>';
        } else {
            closeModal('importPreviewModal');
            document.getElementById('importFile').value = '';
            importRefreshViews(data.message);
        }
    } catch (e) {
        document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">Import failed</span>';
    } finally {
        confirmBtn.disabled = false;
    }
}

// --- Init ---
function initToneSelect() {
    const sel = document.getElementById('chTone');
    sel.innerHTML = '<option value="0">None</option><option value="127">Search</option><option value="240">No Tone</option>';
    sel.innerHTML += '<optgroup label="CTCSS">';
    const ctcss = ''' + json.dumps({str(k): v for k, v in CTCSS_TONES.items()}) + ''';
    Object.entries(ctcss).forEach(([code, freq]) => {
        sel.innerHTML += '<option value="' + code + '">' + freq + ' Hz</option>';
    });
    sel.innerHTML += '</optgroup><optgroup label="DCS">';
    const dcs = ''' + json.dumps({str(k): v for k, v in DCS_CODES.items()}) + ''';
    Object.entries(dcs).forEach(([code, dcsCode]) => {
        sel.innerHTML += '<option value="' + code + '">DCS ' + String(dcsCode).padStart(3, '0') + '</option>';
    });
    sel.innerHTML += '</optgroup>';
}

try {
    initToneSelect();
    initBankTabs();
    refreshSessionState();
    console.log('BC125AT GUI initialized');
} catch(e) {
    console.error('Init error:', e);
    document.getElementById('connStatus').textContent = 'JS Error: ' + e.message;
}
</script>
</body>
</html>'''


# =============================================================================
# API Routes
# =============================================================================

@app.route('/')
def index():
    response = app.make_response(render_template_string(HTML_TEMPLATE))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.route('/api/session')
def api_session():
    try:
        if not _session_active():
            return jsonify({"active": False})
        conn = get_conn()
        model_resp = conn.get_model() or ""
        model = model_resp.split(",")[1] if "," in model_resp else model_resp
        return jsonify({"active": True, "model": model})
    except Exception:
        safe_disconnect()
        return jsonify({"active": False})


@app.route('/api/session/start', methods=['POST'])
def api_session_start():
    try:
        conn = get_conn()
        model_resp = conn.get_model() or ""
        model = model_resp.split(",")[1] if "," in model_resp else model_resp
        return jsonify({"active": True, "model": model})
    except Exception as e:
        safe_disconnect()
        return jsonify({"error": _friendly_connection_error(e)})


@app.route('/api/session/stop', methods=['POST'])
def api_session_stop():
    safe_disconnect()
    return jsonify({"active": False})


@app.route('/api/info')
def api_info():
    try:
        conn = _require_programming_session()
        model_resp = conn.get_model() or ""
        ver_resp = conn.get_version() or ""
        model = model_resp.split(",")[1] if "," in model_resp else model_resp
        firmware = ver_resp.split(",")[1] if "," in ver_resp else ver_resp
        firmware = firmware.replace("Version ", "")

        sm = SettingsManager(conn)
        s = sm.read_all()

        cm = ChannelManager(conn)
        banks = cm.get_bank_status()

        srch = SearchManager(conn)
        cc = srch.read_close_call()

        enabled_banks = sum(1 for enabled in banks.values() if enabled)

        return jsonify({
            "model": model,
            "firmware": firmware,
            "settings": {
                "volume": s.volume,
                "squelch": s.squelch,
                "backlight": s.backlight,
                "backlight_display": s.backlight_display,
                "contrast": s.contrast,
                "priority_mode": s.priority_mode,
                "priority_display": s.priority_display,
                "key_beep_display": s.key_beep_display,
                "key_lock": s.key_lock,
                "band_plan": s.band_plan,
                "band_plan_display": s.band_plan_display,
                "weather_alert": s.weather_alert,
                "battery_charge_time": s.battery_charge_time,
            },
            "banks": banks,
            "close_call_mode": cc.mode_display,
            "enabled_banks": f"{enabled_banks}/10",
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/channels/bank/<int:bank>')
def api_channels_bank(bank):
    try:
        conn = _require_programming_session()
        cm = ChannelManager(conn)
        channels = cm.read_bank(bank)
        return jsonify({
            "bank": bank,
            "channels": [ch.to_dict() for ch in channels],
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/channels/set', methods=['POST'])
def api_set_channel():
    try:
        data = _require_json_dict()
        ch = Channel(
            index=data['channel'],
            name=data.get('name', ''),
            frequency=data['frequency'],
            modulation=data.get('modulation', 'AUTO'),
            tone_code=data.get('tone_code', 0),
            delay=data.get('delay', 2),
            lockout=data.get('lockout', False),
            priority=data.get('priority', False),
        )
        conn = _require_programming_session()
        cm = ChannelManager(conn)
        cm.write_channel(ch)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/channels/delete/<int:index>', methods=['POST'])
def api_delete_channel(index):
    try:
        conn = _require_programming_session()
        cm = ChannelManager(conn)
        cm.delete_channel(index)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/banks/set', methods=['POST'])
def api_set_bank():
    try:
        data = _require_json_dict()
        bank = int(data['bank'])
        enabled = bool(data['enabled'])
        if bank not in range(10):
            return jsonify({"error": "Bank must be 0-9"})
        conn = _require_programming_session()
        cm = ChannelManager(conn)
        banks = cm.get_bank_status()
        banks[bank] = enabled
        cm.set_bank_status(banks)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/banks/clear', methods=['POST'])
def api_clear_bank():
    try:
        data = _require_json_dict()
        bank = int(data['bank'])
        if bank not in range(10):
            return jsonify({"error": "Bank must be 0-9"})
        conn = _require_programming_session()
        cm = ChannelManager(conn)
        cm.clear_bank(bank)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/presets')
def api_presets():
    return jsonify(list_presets())


@app.route('/api/presets/<key>')
def api_preset_detail(key):
    if key not in PRESET_CATALOG:
        return jsonify({"error": f"Unknown preset: {key}"})
    return jsonify({
        "name": PRESET_CATALOG[key]["name"],
        "description": PRESET_CATALOG[key]["description"],
        "frequencies": PRESET_CATALOG[key]["frequencies"],
    })


@app.route('/api/presets/load', methods=['POST'])
def api_load_preset():
    try:
        data = _require_json_dict()
        channels = get_preset_channels(data['preset'], bank=data.get('bank'))
        conn = _require_programming_session()
        cm = ChannelManager(conn)
        cm.write_channels(channels)
        return jsonify({"ok": True, "message": f"Loaded {len(channels)} channels"})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/search')
def api_search():
    try:
        conn = _require_programming_session()
        srch = SearchManager(conn)
        ss = srch.read_search_settings()
        cc = srch.read_close_call()
        sg = srch.read_service_groups()
        csg = srch.read_custom_search_groups()
        ranges = srch.read_all_custom_search_ranges()
        lockout_freqs = srch.read_lockout_frequencies()
        return jsonify({
            "delay": ss.delay,
            "delay_options": DELAY_VALUES,
            "code_search": ss.code_search,
            "close_call": {
                "mode": cc.mode,
                "mode_options": CC_MODE_OPTIONS,
                "mode_display": cc.mode_display,
                "alert_beep": cc.alert_beep,
                "alert_light": cc.alert_light,
                "bands": cc.bands,
                "band_labels": CC_BANDS,
                "lockout": cc.lockout,
            },
            "service_groups": sg,
            "custom_groups": csg,
            "search_ranges": [
                {"index": r.index, "lower": r.lower_freq, "upper": r.upper_freq}
                for r in ranges
            ],
            "lockout_frequencies": lockout_freqs,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/live')
def api_live():
    try:
        conn = _require_programming_session()
        status_resp = conn.get_status() or ""
        live_resp = conn.get_live_info() or ""
        parsed_status = _parse_status_response(status_resp)

        freq = "-"
        modulation = "-"
        name = "-"
        channel = "-"
        squelch_open = False
        status = parsed_status["status"]

        if live_resp.startswith("GLG"):
            parts = live_resp.split(",")
            freq_raw = parts[1] if len(parts) > 1 else ""
            modulation = _clean_display_text(parts[2]) if len(parts) > 2 and parts[2] else "-"
            name = _clean_display_text(parts[7]) if len(parts) > 7 else ""
            squelch_open = (parts[8] == "1") if len(parts) > 8 else False
            channel_val = _clean_display_text(parts[11]) if len(parts) > 11 else ""
            if channel_val.isdigit() and 1 <= int(channel_val) <= 500:
                channel = f"CH {channel_val}"
            try:
                if freq_raw and int(freq_raw) > 0:
                    freq = f"{int(freq_raw) / 10000.0:.4f} MHz"
            except ValueError:
                freq = freq_raw or "-"

            if not name or name in ("-", "0"):
                name = "-"

        if name == "-" and parsed_status["display_lines"]:
            # Prefer meaningful front-panel text like "Close Call Hits" over blank names.
            name = parsed_status["display_lines"][0]
        if modulation in ("", "-") and parsed_status["display_lines"]:
            for line in parsed_status["display_lines"]:
                if line in ("AM", "FM", "NFM", "AUTO"):
                    modulation = line
                    break
        if channel == "-" and parsed_status["display_lines"]:
            for line in parsed_status["display_lines"]:
                compact = line.replace(" ", "")
                if compact.startswith("CH") and compact[2:].isdigit():
                    ch_num = int(compact[2:])
                    if 1 <= ch_num <= 500:
                        channel = f"CH {ch_num}"
                        break

        return jsonify({
            "status": status,
            "frequency": freq,
            "modulation": modulation,
            "name": name,
            "channel": channel,
            "squelch_open": squelch_open,
            "raw_live": live_resp,
            "raw_status": status_resp,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/search/set', methods=['POST'])
def api_set_search():
    try:
        data = _require_json_dict()
        setting = data['setting']
        value = data['value']
        conn = _require_programming_session()
        srch = SearchManager(conn)

        if setting == 'delay':
            srch.set_search_delay(int(value))
        elif setting == 'code_search':
            srch.set_code_search(str(value) in ('1', 'true', 'on'))
        elif setting == 'cc_mode':
            srch.set_close_call_mode(int(value))
        elif setting == 'cc_alert_beep':
            srch.set_close_call_alert_beep(str(value) in ('1', 'true', 'on'))
        elif setting == 'cc_alert_light':
            srch.set_close_call_alert_light(str(value) in ('1', 'true', 'on'))
        elif setting == 'cc_lockout':
            srch.set_close_call_lockout(str(value) in ('1', 'true', 'on'))
        else:
            return jsonify({"error": f"Unknown search setting: {setting}"})

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/search/closecall-band', methods=['POST'])
def api_set_close_call_band():
    try:
        data = _require_json_dict()
        index = int(data['index'])
        enabled = bool(data['enabled'])
        conn = _require_programming_session()
        srch = SearchManager(conn)
        srch.set_close_call_band(index, enabled)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/search/service-group', methods=['POST'])
def api_set_service_group():
    try:
        data = _require_json_dict()
        name = data['name']
        enabled = bool(data['enabled'])
        if name not in SERVICE_GROUPS:
            return jsonify({"error": f"Unknown service group: {name}"})
        conn = _require_programming_session()
        srch = SearchManager(conn)
        groups = srch.read_service_groups()
        groups[name] = enabled
        srch.write_service_groups(groups)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/search/custom-group', methods=['POST'])
def api_set_custom_group():
    try:
        data = _require_json_dict()
        group = int(data['group'])
        enabled = bool(data['enabled'])
        if group not in range(1, 11):
            return jsonify({"error": "Custom search group must be 1-10"})
        conn = _require_programming_session()
        srch = SearchManager(conn)
        groups = srch.read_custom_search_groups()
        groups[group] = enabled
        srch.write_custom_search_groups(groups)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/search/range', methods=['POST'])
def api_set_search_range():
    try:
        data = _require_json_dict()
        sr = CustomSearchRange(
            index=int(data['index']),
            lower_freq=float(data['lower']),
            upper_freq=float(data['upper']),
        )
        conn = _require_programming_session()
        srch = SearchManager(conn)
        srch.write_custom_search_range(sr)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/search/lockout', methods=['POST'])
def api_add_lockout():
    try:
        data = _require_json_dict()
        freq = float(data['frequency'])
        conn = _require_programming_session()
        srch = SearchManager(conn)
        srch.lock_frequency(freq)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/search/lockout', methods=['DELETE'])
def api_remove_lockout():
    try:
        data = _require_json_dict()
        freq = float(data['frequency'])
        conn = _require_programming_session()
        srch = SearchManager(conn)
        srch.unlock_frequency(freq)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/settings')
def api_settings():
    try:
        conn = _require_programming_session()
        sm = SettingsManager(conn)
        s = sm.read_all()
        return jsonify({
            "volume": s.volume,
            "squelch": s.squelch,
            "contrast": s.contrast,
            "backlight": s.backlight,
            "backlight_display": s.backlight_display,
            "priority_mode": s.priority_mode,
            "priority_display": s.priority_display,
            "key_beep_level": s.key_beep_level,
            "key_beep_display": s.key_beep_display,
            "key_lock": s.key_lock,
            "band_plan": s.band_plan,
            "band_plan_display": s.band_plan_display,
            "weather_alert": s.weather_alert,
            "battery_charge_time": s.battery_charge_time,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/settings/set', methods=['POST'])
def api_set_setting():
    try:
        data = _require_json_dict()
        setting = data['setting']
        value = data['value']
        conn = _require_programming_session()
        sm = SettingsManager(conn)

        if setting == 'volume':
            sm.set_volume(int(value))
        elif setting == 'squelch':
            sm.set_squelch(int(value))
        elif setting == 'contrast':
            sm.set_contrast(int(value))
        elif setting == 'backlight':
            sm.set_backlight(str(value).upper())
        elif setting == 'priority':
            sm.set_priority(int(value))
        elif setting == 'wxalert':
            sm.set_weather_alert(str(value) in ('1', 'true', 'on'))
        elif setting == 'keybeep':
            sm.set_key_beep(int(value))
        elif setting == 'keylock':
            sm.set_key_lock(str(value) in ('1', 'true', 'on'))
        elif setting == 'bandplan':
            sm.set_band_plan(int(value))
        elif setting == 'battery':
            sm.set_battery_charge_time(int(value))
        else:
            return jsonify({"error": f"Unknown setting: {setting}"})

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/export/<format>')
def api_export(format):
    try:
        conn = _require_programming_session()
        cm = ChannelManager(conn)
        channels = cm.read_all_channels()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if format == 'backup':
            sm = SettingsManager(conn)
            s = sm.read_all()
            bank_status = cm.get_bank_status()
            settings_dict = {
                "backlight": s.backlight, "battery_charge_time": s.battery_charge_time,
                "band_plan": s.band_plan, "key_beep_level": s.key_beep_level,
                "key_lock": s.key_lock, "priority_mode": s.priority_mode,
                "contrast": s.contrast, "volume": s.volume,
                "squelch": s.squelch, "weather_alert": s.weather_alert,
            }
            srch = SearchManager(conn)
            ss = srch.read_search_settings()
            cc = srch.read_close_call()
            search_dict = {
                "delay": ss.delay,
                "code_search": ss.code_search,
                "close_call": {
                    "mode": cc.mode,
                    "alert_beep": cc.alert_beep,
                    "alert_light": cc.alert_light,
                    "bands": cc.bands,
                    "lockout": cc.lockout,
                },
                "service_groups": srch.read_service_groups(),
                "custom_groups": srch.read_custom_search_groups(),
                "search_ranges": [
                    {
                        "index": r.index,
                        "lower_freq": r.lower_freq,
                        "upper_freq": r.upper_freq,
                    }
                    for r in srch.read_all_custom_search_ranges()
                ],
                "lockout_frequencies": srch.read_lockout_frequencies(),
            }
            fd, filepath = tempfile.mkstemp(suffix='.json')
            os.close(fd)
            export_full_backup(channels, settings_dict, search_dict, bank_status, filepath)
            @after_this_request
            def _cleanup_backup(response):
                try:
                    os.unlink(filepath)
                except Exception:
                    pass
                return response
            return send_file(filepath, as_attachment=True,
                           download_name=f'bc125at_backup_{timestamp}.json')
        elif format == 'bc125at_ss':
            sm = SettingsManager(conn)
            s = sm.read_all()
            bank_status = cm.get_bank_status()
            settings_dict = {
                "backlight": s.backlight, "battery_charge_time": s.battery_charge_time,
                "band_plan": s.band_plan, "key_beep_level": s.key_beep_level,
                "key_lock": s.key_lock, "priority_mode": s.priority_mode,
                "contrast": s.contrast, "volume": s.volume,
                "squelch": s.squelch, "weather_alert": s.weather_alert,
            }
            srch = SearchManager(conn)
            ss = srch.read_search_settings()
            cc = srch.read_close_call()
            search_dict = {
                "delay": ss.delay,
                "code_search": ss.code_search,
                "close_call": {
                    "mode": cc.mode,
                    "alert_beep": cc.alert_beep,
                    "alert_light": cc.alert_light,
                    "bands": cc.bands,
                    "lockout": cc.lockout,
                },
                "service_groups": srch.read_service_groups(),
                "custom_groups": srch.read_custom_search_groups(),
                "search_ranges": [
                    {
                        "index": r.index,
                        "lower_freq": r.lower_freq,
                        "upper_freq": r.upper_freq,
                    }
                    for r in srch.read_all_custom_search_ranges()
                ],
                "lockout_frequencies": srch.read_lockout_frequencies(),
            }
            fd, filepath = tempfile.mkstemp(suffix='.bc125at_ss')
            os.close(fd)
            export_bc125at_ss(channels, settings_dict, search_dict, bank_status, filepath)
            @after_this_request
            def _cleanup_bc125at(response):
                try:
                    os.unlink(filepath)
                except Exception:
                    pass
                return response
            return send_file(filepath, as_attachment=True,
                           download_name=f'bc125at_profile_{timestamp}.bc125at_ss')
        elif format == 'csv':
            active = [ch for ch in channels if not ch.is_empty]
            fd, filepath = tempfile.mkstemp(suffix='.csv')
            os.close(fd)
            export_channels_csv(active, filepath)
            @after_this_request
            def _cleanup_csv(response):
                try:
                    os.unlink(filepath)
                except Exception:
                    pass
                return response
            return send_file(filepath, as_attachment=True,
                           download_name=f'bc125at_channels_{timestamp}.csv')
        else:  # json
            active = [ch for ch in channels if not ch.is_empty]
            fd, filepath = tempfile.mkstemp(suffix='.json')
            os.close(fd)
            export_channels_json(active, filepath)
            @after_this_request
            def _cleanup_json(response):
                try:
                    os.unlink(filepath)
                except Exception:
                    pass
                return response
            return send_file(filepath, as_attachment=True,
                           download_name=f'bc125at_channels_{timestamp}.json')
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/import/preview', methods=['POST'])
def api_import_preview():
    filepath = None
    try:
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({"error": "No file selected"})
        content = file.read().decode('utf-8')
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ('.json', '.csv', '.bc125at_ss'):
            return jsonify({"error": "Only CSV, JSON, and BC125AT season files are supported"})

        fd, filepath = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        with open(filepath, 'w') as f:
            f.write(content)

        from bc125at.io import import_auto, import_full_backup, import_bc125at_ss

        target_bank = _parse_import_bank(request.form.get('bank_target'))
        clear_bank_first = request.form.get('clear_bank_first') in ('1', 'true', 'True', 'yes', 'on')

        if ext == '.bc125at_ss':
            if target_bank is not None or clear_bank_first:
                return jsonify({"error": "BC125AT season files use their own bank layout and do not support destination remapping"})
            channels, settings_dict, search_dict, bank_status = import_bc125at_ss(filepath)
            preview = _build_import_preview(channels, kind="season channels")
            preview["season_file"] = {
                "settings": True,
                "search": True,
                "banks": True,
            }
            return jsonify(preview)

        if ext == '.json':
            data = json.loads(content)
            if isinstance(data, dict) and data.get('format') == 'bc125at-tool-backup':
                if target_bank is not None or clear_bank_first:
                    return jsonify({"error": "Full backup restore does not support destination bank remapping"})
                channels, settings_dict, search_dict, bank_status = import_full_backup(filepath)
                preview = _build_import_preview(channels, kind="backup channels")
                preview["backup"] = {
                    "settings": bool(settings_dict),
                    "search": bool(search_dict),
                    "banks": bool(bank_status),
                }
                return jsonify(preview)

        channels = import_auto(filepath)
        channels, truncated = _apply_import_options(
            channels,
            target_bank=target_bank,
            clear_bank_first=clear_bank_first,
        )
        return jsonify(_build_import_preview(
            channels,
            target_bank=target_bank,
            clear_bank_first=clear_bank_first,
            truncated=truncated,
        ))
    except Exception as e:
        return jsonify({"error": str(e)})
    finally:
        if filepath and os.path.exists(filepath):
            os.unlink(filepath)


@app.route('/api/import', methods=['POST'])
def api_import():
    filepath = None
    try:
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({"error": "No file selected"})
        content = file.read().decode('utf-8')
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ('.json', '.csv', '.bc125at_ss'):
            return jsonify({"error": "Only CSV, JSON, and BC125AT season files are supported"})

        # Save to temp file
        fd, filepath = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        with open(filepath, 'w') as f:
            f.write(content)

        from bc125at.io import import_auto, import_full_backup, import_bc125at_ss

        target_bank = _parse_import_bank(request.form.get('bank_target'))
        clear_bank_first = request.form.get('clear_bank_first') in ('1', 'true', 'True', 'yes', 'on')

        if ext == '.bc125at_ss':
            if target_bank is not None or clear_bank_first:
                return jsonify({"error": "BC125AT season files use their own bank layout and do not support destination remapping"})
            channels, settings_dict, search_dict, bank_status = import_bc125at_ss(filepath)
            conn = _require_programming_session()
            cm = ChannelManager(conn)
            cm.write_channels(channels)
            cm.set_bank_status(bank_status)

            sm = SettingsManager(conn)
            sm.write_all(ScannerSettings(**settings_dict))

            srch = SearchManager(conn)
            ss = SearchSettings(
                delay=search_dict.get("delay", 2),
                code_search=search_dict.get("code_search", False),
            )
            srch.write_search_settings(ss)
            cc_data = search_dict.get("close_call", {})
            cc = CloseCallSettings(
                mode=cc_data.get("mode", 0),
                alert_beep=cc_data.get("alert_beep", False),
                alert_light=cc_data.get("alert_light", False),
                bands=cc_data.get("bands", [True] * 5),
                lockout=cc_data.get("lockout", False),
            )
            srch.write_close_call(cc)
            srch.write_service_groups(search_dict.get("service_groups", {}))
            srch.write_custom_search_groups(search_dict.get("custom_groups", {}))
            for range_data in search_dict.get("search_ranges", []):
                srch.write_custom_search_range(CustomSearchRange(
                    index=int(range_data["index"]),
                    lower_freq=float(range_data["lower_freq"]),
                    upper_freq=float(range_data["upper_freq"]),
                ))
            return jsonify({"ok": True, "message": f"Restored BC125AT season file: {len(channels)} channels + settings + search + banks"})

        if ext == '.json':
            data = json.loads(content)
            if isinstance(data, dict) and data.get('format') == 'bc125at-tool-backup':
                if target_bank is not None or clear_bank_first:
                    return jsonify({"error": "Full backup restore does not support destination bank remapping"})
                channels, settings_dict, search_dict, bank_status = import_full_backup(filepath)
                conn = _require_programming_session()
                cm = ChannelManager(conn)
                cm.write_channels(channels)
                if bank_status:
                    cm.set_bank_status(bank_status)
                if settings_dict:
                    sm = SettingsManager(conn)
                    s = ScannerSettings(**settings_dict)
                    sm.write_all(s)
                if search_dict:
                    srch = SearchManager(conn)
                    if "delay" in search_dict:
                        ss = SearchSettings(
                            delay=search_dict["delay"],
                            code_search=search_dict.get("code_search", False),
                        )
                        srch.write_search_settings(ss)
                    if "close_call" in search_dict:
                        cc_data = search_dict["close_call"]
                        cc = CloseCallSettings(
                            mode=cc_data.get("mode", 0),
                            alert_beep=cc_data.get("alert_beep", False),
                            alert_light=cc_data.get("alert_light", False),
                            bands=cc_data.get("bands", [True] * 5),
                            lockout=cc_data.get("lockout", False),
                        )
                        srch.write_close_call(cc)
                    if "service_groups" in search_dict:
                        srch.write_service_groups(search_dict["service_groups"])
                    if "custom_groups" in search_dict:
                        srch.write_custom_search_groups({
                            int(k): v for k, v in search_dict["custom_groups"].items()
                        })
                    if "search_ranges" in search_dict:
                        for range_data in search_dict["search_ranges"]:
                            srch.write_custom_search_range(CustomSearchRange(
                                index=int(range_data["index"]),
                                lower_freq=float(range_data["lower_freq"]),
                                upper_freq=float(range_data["upper_freq"]),
                            ))
                    if "lockout_frequencies" in search_dict:
                        for freq in srch.read_lockout_frequencies():
                            srch.unlock_frequency(freq)
                        for freq in search_dict["lockout_frequencies"]:
                            srch.lock_frequency(float(freq))
                return jsonify({"ok": True, "message": f"Restored full backup: {len(channels)} channels + settings + search"})

        channels = import_auto(filepath)
        channels, truncated = _apply_import_options(
            channels,
            target_bank=target_bank,
            clear_bank_first=clear_bank_first,
        )
        conn = _require_programming_session()
        cm = ChannelManager(conn)
        if clear_bank_first and target_bank is not None:
            cm.clear_bank(target_bank)
        cm.write_channels(channels)
        message = f"Imported {len(channels)} channels"
        if target_bank is not None:
            message += f" into bank {target_bank}"
        if truncated:
            message += f" ({truncated} skipped because a bank only holds 50 channels)"
        return jsonify({"ok": True, "message": message})
    except Exception as e:
        return jsonify({"error": str(e)})
    finally:
        if filepath and os.path.exists(filepath):
            os.unlink(filepath)


@app.route('/api/import/text/preview', methods=['POST'])
def api_import_text_preview():
    try:
        data = _require_json_dict()
        text = str(data.get('text', ''))
        target_bank = _parse_import_bank(data.get('bank_target'))
        clear_bank_first = bool(data.get('clear_bank_first', False))

        from bc125at.io import import_channels_text

        channels = import_channels_text(text)
        channels, truncated = _apply_import_options(
            channels,
            target_bank=target_bank,
            clear_bank_first=clear_bank_first,
        )

        return jsonify(_build_import_preview(
            channels,
            target_bank=target_bank,
            clear_bank_first=clear_bank_first,
            truncated=truncated,
            kind="pasted channels",
        ))
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/import/text', methods=['POST'])
def api_import_text():
    try:
        data = _require_json_dict()
        text = str(data.get('text', ''))
        target_bank = _parse_import_bank(data.get('bank_target'))
        clear_bank_first = bool(data.get('clear_bank_first', False))

        from bc125at.io import import_channels_text

        channels = import_channels_text(text)
        channels, truncated = _apply_import_options(
            channels,
            target_bank=target_bank,
            clear_bank_first=clear_bank_first,
        )

        conn = _require_programming_session()
        cm = ChannelManager(conn)
        if clear_bank_first and target_bank is not None:
            cm.clear_bank(target_bank)
        cm.write_channels(channels)

        message = f"Imported {len(channels)} pasted channels"
        if target_bank is not None:
            message += f" into bank {target_bank}"
        if truncated:
            message += f" ({truncated} skipped because a bank only holds 50 channels)"
        return jsonify({"ok": True, "message": message})
    except Exception as e:
        return jsonify({"error": str(e)})


def main():
    port = 5125
    print(f"\n  BC125AT Scanner Tool")
    print(f"  ====================")
    print(f"  Opening http://localhost:{port}")
    print(f"  Press Ctrl+C to quit\n")

    # Open browser after short delay
    threading.Timer(1.0, lambda: webbrowser.open(f'http://localhost:{port}')).start()

    app.run(host='127.0.0.1', port=port, debug=False)


if __name__ == '__main__':
    main()
