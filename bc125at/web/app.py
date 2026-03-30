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
from flask import Flask, render_template_string, jsonify, request, send_file
from datetime import datetime
from io import StringIO
import tempfile

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bc125at.connection import ScannerConnection
from bc125at.channels import Channel, ChannelManager, NUM_CHANNELS, CHANNELS_PER_BANK
from bc125at.channels import CTCSS_TONES, DCS_CODES, MODULATION_MODES, DELAY_VALUES
from bc125at.channels import tone_code_to_string, is_valid_frequency, FREQ_RANGES
from bc125at.settings import SettingsManager, ScannerSettings, BACKLIGHT_OPTIONS, PRIORITY_OPTIONS
from bc125at.search import SearchManager, CloseCallSettings, CC_MODE_OPTIONS, CC_BANDS, SERVICE_GROUPS
from bc125at.presets import list_presets, get_preset_channels, PRESET_CATALOG
from bc125at.io import export_channels_csv, export_channels_json, export_full_backup

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

# Register cleanup handlers
atexit.register(safe_disconnect)

def _signal_handler(signum, frame):
    safe_disconnect()
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BC125AT Scanner Tool</title>
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
.form-group input:focus, .form-group select:focus { outline: none; border-color: var(--accent); }
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
        <div class="connection-badge">
            <div class="connection-dot" id="connDot"></div>
            <span id="connStatus">Connecting...</span>
        </div>
    </div>

    <nav class="nav">
        <button class="active" onclick="showPanel('dashboard')">Dashboard</button>
        <button onclick="showPanel('channels')">Channels</button>
        <button onclick="showPanel('presets')">Presets</button>
        <button onclick="showPanel('search')">Search & Close Call</button>
        <button onclick="showPanel('settings')">Settings</button>
        <button onclick="showPanel('backup')">Backup & Import</button>
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
                <div class="info-item"><div class="label">Programmed Channels</div><div class="value" id="statChannels">-</div></div>
                <div class="info-item"><div class="label">Close Call Mode</div><div class="value" id="statCC">-</div></div>
                <div class="info-item"><div class="label">Weather Alert</div><div class="value" id="statWX">-</div></div>
                <div class="info-item"><div class="label">Band Plan</div><div class="value" id="statBand">-</div></div>
            </div>
        </div>
    </div>

    <!-- CHANNELS -->
    <div class="panel" id="panel-channels">
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h2 style="margin-bottom:0">Channel Editor</h2>
                <div style="display:flex;gap:8px;">
                    <button class="btn btn-primary btn-sm" onclick="showAddChannel()">+ Add Channel</button>
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
                Save your scanner programming to a file for safekeeping or transfer.
            </p>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <button class="btn btn-primary" onclick="doExport('json')">Export Channels (JSON)</button>
                <button class="btn btn-secondary" onclick="doExport('csv')">Export Channels (CSV)</button>
                <button class="btn btn-success" onclick="doExport('backup')">Full Backup (Channels + Settings)</button>
            </div>
        </div>
        <div class="card">
            <h2>Import & Restore</h2>
            <p style="color:var(--text2);margin-bottom:16px;font-size:14px;">
                Load channels from a previously exported file.
            </p>
            <input type="file" id="importFile" accept=".json,.csv" style="display:none;" onchange="doImport(this)">
            <button class="btn btn-secondary" onclick="document.getElementById('importFile').click()">Import File...</button>
            <div id="importStatus" style="margin-top:12px;"></div>
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

// --- Navigation ---
function showPanel(name) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav button').forEach(b => b.classList.remove('active'));
    document.getElementById('panel-' + name).classList.add('active');
    event.target.classList.add('active');

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
    setTimeout(() => t.className = 'toast', 3000);
}

// --- Modal ---
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

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
    document.getElementById('connStatus').textContent = 'Loading...';
    const data = await api('info');
    if (!data) {
        document.getElementById('connDot').classList.add('disconnected');
        document.getElementById('connStatus').textContent = 'Disconnected — check USB';
        // Auto-retry after 3 seconds
        setTimeout(loadDashboard, 3000);
        return;
    }
    document.getElementById('connDot').classList.remove('disconnected');
    document.getElementById('connStatus').textContent = data.model + ' v' + data.firmware;

    document.getElementById('infoModel').textContent = data.model;
    document.getElementById('infoFirmware').textContent = data.firmware;
    document.getElementById('infoVolume').textContent = data.settings.volume + '/15';
    document.getElementById('infoSquelch').textContent = data.settings.squelch + '/15';
    document.getElementById('infoBacklight').textContent = data.settings.backlight_display;
    document.getElementById('infoPriority').textContent = data.settings.priority_display;

    document.getElementById('statCC').textContent = data.close_call_mode || '-';
    document.getElementById('statWX').textContent = data.settings.weather_alert ? 'On' : 'Off';
    document.getElementById('statBand').textContent = data.settings.band_plan_display;
    document.getElementById('statChannels').textContent = data.programmed_channels;

    // Banks
    const bg = document.getElementById('bankGrid');
    bg.innerHTML = '';
    for (const [bank, enabled] of Object.entries(data.banks)) {
        const div = document.createElement('div');
        div.className = 'info-item';
        div.innerHTML = '<div class="label">Bank ' + bank + '</div><div class="value" style="color:' +
            (enabled ? 'var(--green)' : 'var(--red)') + '">' + (enabled ? 'Enabled' : 'Disabled') + '</div>';
        bg.appendChild(div);
    }
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
    const data = {
        channel: parseInt(document.getElementById('chIndex').value),
        frequency: parseFloat(document.getElementById('chFreq').value),
        name: document.getElementById('chName').value,
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
    let html = '<div class="setting-row"><div class="setting-label">Search Delay</div><div class="setting-value">' + data.delay + 's</div></div>';
    html += '<div class="setting-row"><div class="setting-label">CTCSS/DCS Code Search</div><div class="setting-value">' + (data.code_search ? 'On' : 'Off') + '</div></div>';
    html += '<h3>Close Call</h3>';
    html += '<div class="setting-row"><div class="setting-label">Mode</div><div class="setting-value">' + data.close_call.mode_display + '</div></div>';
    html += '<div class="setting-row"><div class="setting-label">Alert Beep</div><div class="setting-value">' + (data.close_call.alert_beep ? 'On' : 'Off') + '</div></div>';
    html += '<div class="setting-row"><div class="setting-label">Alert Light</div><div class="setting-value">' + (data.close_call.alert_light ? 'On' : 'Off') + '</div></div>';
    html += '<h3>Close Call Bands</h3>';
    data.close_call.bands.forEach((enabled, i) => {
        const names = ['VHF Low', 'Civil Air', 'VHF High', 'Military Air', 'UHF'];
        html += '<div class="setting-row"><div class="setting-label">' + names[i] + '</div><div class="setting-value" style="color:' + (enabled ? 'var(--green)' : 'var(--red)') + '">' + (enabled ? 'On' : 'Off') + '</div></div>';
    });
    html += '<h3>Service Search Groups</h3>';
    Object.entries(data.service_groups).forEach(([name, enabled]) => {
        html += '<div class="setting-row"><div class="setting-label">' + name + '</div><div class="setting-value" style="color:' + (enabled ? 'var(--green)' : 'var(--red)') + '">' + (enabled ? 'On' : 'Off') + '</div></div>';
    });
    html += '<h3>Custom Search Ranges</h3>';
    data.search_ranges.forEach(r => {
        html += '<div class="setting-row"><div class="setting-label">Range ' + r.index + '</div><div class="setting-value">' + r.lower.toFixed(4) + ' - ' + r.upper.toFixed(4) + ' MHz</div></div>';
    });
    c.innerHTML = html;
}

// --- Settings ---
async function loadSettings() {
    const data = await api('settings');
    if (!data) return;
    const c = document.getElementById('settingsContent');
    let html = '';

    // Volume slider
    html += '<div class="setting-row"><div class="setting-label">Volume</div><div class="setting-value">' +
        '<input type="range" min="0" max="15" value="' + data.volume + '" id="setVolume" ' +
        'oninput="document.getElementById(\'volVal\').textContent=this.value" ' +
        'onchange="saveSetting(\'volume\',this.value)">' +
        ' <span id="volVal">' + data.volume + '</span>/15</div></div>';

    // Squelch slider
    html += '<div class="setting-row"><div class="setting-label">Squelch</div><div class="setting-value">' +
        '<input type="range" min="0" max="15" value="' + data.squelch + '" id="setSquelch" ' +
        'oninput="document.getElementById(\'sqlVal\').textContent=this.value" ' +
        'onchange="saveSetting(\'squelch\',this.value)">' +
        ' <span id="sqlVal">' + data.squelch + '</span>/15</div></div>';

    // Contrast slider
    html += '<div class="setting-row"><div class="setting-label">Contrast</div><div class="setting-value">' +
        '<input type="range" min="1" max="15" value="' + data.contrast + '" id="setContrast" ' +
        'oninput="document.getElementById(\'cntVal\').textContent=this.value" ' +
        'onchange="saveSetting(\'contrast\',this.value)">' +
        ' <span id="cntVal">' + data.contrast + '</span>/15</div></div>';

    // Backlight dropdown
    html += '<div class="setting-row"><div class="setting-label">Backlight</div><div class="setting-value">' +
        '<select onchange="saveSetting(\'backlight\',this.value)" class="inline-edit">' +
        ['AF','KY','SQ','KS','AO'].map(v => {
            const labels = {AF:'Always Off',KY:'Keypress',SQ:'Squelch',KS:'Key+Squelch',AO:'Always On'};
            return '<option value="'+v+'"'+(data.backlight===v?' selected':'')+'>'+labels[v]+'</option>';
        }).join('') + '</select></div></div>';

    // Priority dropdown
    html += '<div class="setting-row"><div class="setting-label">Priority Mode</div><div class="setting-value">' +
        '<select onchange="saveSetting(\'priority\',this.value)" class="inline-edit">' +
        [{v:0,l:'Off'},{v:1,l:'On'},{v:2,l:'Plus On'},{v:3,l:'Do Not Disturb'}].map(o =>
            '<option value="'+o.v+'"'+(data.priority_mode===o.v?' selected':'')+'>'+o.l+'</option>'
        ).join('') + '</select></div></div>';

    // Weather Alert toggle
    html += '<div class="setting-row"><div class="setting-label">Weather Alert</div><div class="setting-value">' +
        '<select onchange="saveSetting(\'wxalert\',this.value)" class="inline-edit">' +
        '<option value="0"'+(data.weather_alert?'':' selected')+'>Off</option>' +
        '<option value="1"'+(data.weather_alert?' selected':'')+'>On</option>' +
        '</select></div></div>';

    // Key Beep toggle
    html += '<div class="setting-row"><div class="setting-label">Key Beep</div><div class="setting-value">' +
        '<select onchange="saveSetting(\'keybeep\',this.value)" class="inline-edit">' +
        '<option value="0"'+(data.key_beep_level===0?' selected':'')+'>Auto</option>' +
        '<option value="99"'+(data.key_beep_level===99?' selected':'')+'>Off</option>' +
        '</select></div></div>';

    // Read-only info
    html += '<div class="setting-row"><div class="setting-label">Band Plan</div><div class="setting-value">' + data.band_plan_display + '</div></div>';
    html += '<div class="setting-row"><div class="setting-label">Battery Timer</div><div class="setting-value">' + data.battery_charge_time + 'h</div></div>';

    c.innerHTML = html;
}

async function saveSetting(key, value) {
    const result = await api('settings/set', { method: 'POST', body: { setting: key, value: value } });
    if (result && !result.error) {
        toast(key.charAt(0).toUpperCase() + key.slice(1) + ' updated');
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
        a.download = resp.headers.get('Content-Disposition')?.split('filename=')[1] || ('bc125at_export.' + (format === 'csv' ? 'csv' : 'json'));
        a.click();
        URL.revokeObjectURL(url);
        toast('Export complete!');
    } else {
        toast('Export failed', 'error');
    }
}

// --- Import ---
async function doImport(input) {
    const file = input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    document.getElementById('importStatus').innerHTML = '<div class="spinner"></div> Importing...';
    try {
        const resp = await fetch('/api/import', { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.error) {
            document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">' + data.error + '</span>';
        } else {
            document.getElementById('importStatus').innerHTML = '<span style="color:var(--green)">' + data.message + '</span>';
            toast(data.message);
        }
    } catch(e) {
        document.getElementById('importStatus').innerHTML = '<span style="color:var(--red)">Import failed</span>';
    }
    input.value = '';
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

initToneSelect();
initBankTabs();
loadDashboard();
</script>
</body>
</html>'''


# =============================================================================
# API Routes
# =============================================================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/info')
def api_info():
    try:
        conn = get_conn()
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

        # Quick count: just check first channel of each bank (10 reads instead of 50)
        programmed_banks = 0
        for bank_start in [1, 51, 101, 151, 201, 251, 301, 351, 401, 451]:
            try:
                ch = cm.read_channel(bank_start)
                if not ch.is_empty:
                    programmed_banks += 1
            except Exception:
                pass
        programmed_est = f"{programmed_banks}/10 banks active"

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
            "programmed_channels": programmed_est,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/channels/bank/<int:bank>')
def api_channels_bank(bank):
    try:
        conn = get_conn()
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
        data = request.json
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
        conn = get_conn()
        cm = ChannelManager(conn)
        cm.write_channel(ch)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/channels/delete/<int:index>', methods=['POST'])
def api_delete_channel(index):
    try:
        conn = get_conn()
        cm = ChannelManager(conn)
        cm.delete_channel(index)
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
        data = request.json
        channels = get_preset_channels(data['preset'], bank=data.get('bank'))
        conn = get_conn()
        cm = ChannelManager(conn)
        cm.write_channels(channels)
        return jsonify({"ok": True, "message": f"Loaded {len(channels)} channels"})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/search')
def api_search():
    try:
        conn = get_conn()
        srch = SearchManager(conn)
        ss = srch.read_search_settings()
        cc = srch.read_close_call()
        sg = srch.read_service_groups()
        ranges = srch.read_all_custom_search_ranges()
        return jsonify({
            "delay": ss.delay,
            "code_search": ss.code_search,
            "close_call": {
                "mode": cc.mode,
                "mode_display": cc.mode_display,
                "alert_beep": cc.alert_beep,
                "alert_light": cc.alert_light,
                "bands": cc.bands,
                "lockout": cc.lockout,
            },
            "service_groups": sg,
            "search_ranges": [
                {"index": r.index, "lower": r.lower_freq, "upper": r.upper_freq}
                for r in ranges
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/settings')
def api_settings():
    try:
        conn = get_conn()
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
        data = request.json
        setting = data['setting']
        value = data['value']
        conn = get_conn()
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
            conn.enter_program_mode()
            # Read current lock state to preserve it
            resp = conn.send_command("KBP")
            lock = "0"
            if resp and "," in resp:
                parts = resp.split(",")
                lock = parts[2] if len(parts) > 2 else "0"
            resp = conn.send_command(f"KBP,{value},{lock}")
            if resp != "KBP,OK":
                return jsonify({"error": f"Failed to set key beep: {resp}"})
        else:
            return jsonify({"error": f"Unknown setting: {setting}"})

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/export/<format>')
def api_export(format):
    try:
        conn = get_conn()
        cm = ChannelManager(conn)
        channels = cm.read_all_channels()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if format == 'backup':
            sm = SettingsManager(conn)
            s = sm.read_all()
            settings_dict = {
                "backlight": s.backlight, "battery_charge_time": s.battery_charge_time,
                "band_plan": s.band_plan, "key_beep_level": s.key_beep_level,
                "key_lock": s.key_lock, "priority_mode": s.priority_mode,
                "contrast": s.contrast, "volume": s.volume,
                "squelch": s.squelch, "weather_alert": s.weather_alert,
            }
            filepath = tempfile.mktemp(suffix='.json')
            export_full_backup(channels, settings_dict, {}, filepath)
            return send_file(filepath, as_attachment=True,
                           download_name=f'bc125at_backup_{timestamp}.json')
        elif format == 'csv':
            active = [ch for ch in channels if not ch.is_empty]
            filepath = tempfile.mktemp(suffix='.csv')
            export_channels_csv(active, filepath)
            return send_file(filepath, as_attachment=True,
                           download_name=f'bc125at_channels_{timestamp}.csv')
        else:  # json
            active = [ch for ch in channels if not ch.is_empty]
            filepath = tempfile.mktemp(suffix='.json')
            export_channels_json(active, filepath)
            return send_file(filepath, as_attachment=True,
                           download_name=f'bc125at_channels_{timestamp}.json')
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/import', methods=['POST'])
def api_import():
    try:
        file = request.files['file']
        content = file.read().decode('utf-8')
        ext = os.path.splitext(file.filename)[1].lower()

        # Save to temp file
        filepath = tempfile.mktemp(suffix=ext)
        with open(filepath, 'w') as f:
            f.write(content)

        from bc125at.io import import_auto, import_full_backup

        if ext == '.json':
            data = json.loads(content)
            if data.get('format') == 'bc125at-tool-backup':
                channels, settings_dict, search_dict = import_full_backup(filepath)
                conn = get_conn()
                cm = ChannelManager(conn)
                cm.write_channels(channels)
                if settings_dict:
                    sm = SettingsManager(conn)
                    s = ScannerSettings(**settings_dict)
                    sm.write_all(s)
                os.unlink(filepath)
                return jsonify({"ok": True, "message": f"Restored full backup: {len(channels)} channels + settings"})

        channels = import_auto(filepath)
        conn = get_conn()
        cm = ChannelManager(conn)
        cm.write_channels(channels)
        os.unlink(filepath)
        return jsonify({"ok": True, "message": f"Imported {len(channels)} channels"})
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
