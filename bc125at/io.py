"""
BC125AT Import/Export

Export channels and settings to CSV/JSON for backup.
Import from CSV/JSON to restore or load new programming.
"""

import csv
import json
import os
from datetime import datetime
from .channels import Channel, NUM_CHANNELS
from .settings import ScannerSettings


def export_channels_csv(channels, filepath):
    """Export channels to CSV file."""
    fieldnames = [
        "channel", "name", "frequency", "modulation",
        "tone", "tone_code", "delay", "lockout", "priority", "bank",
    ]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ch in channels:
            writer.writerow(ch.to_dict())
    return filepath


def import_channels_csv(filepath):
    """Import channels from CSV file."""
    channels = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle boolean fields that may be strings
            for bool_field in ("lockout", "priority"):
                if bool_field in row:
                    val = row[bool_field]
                    if isinstance(val, str):
                        row[bool_field] = val.lower() in ("true", "1", "yes")
            channels.append(Channel.from_dict(row))
    return channels


def export_channels_json(channels, filepath):
    """Export channels to JSON file."""
    data = {
        "format": "bc125at-tool",
        "version": 1,
        "exported": datetime.now().isoformat(),
        "channel_count": len(channels),
        "channels": [ch.to_dict() for ch in channels],
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return filepath


def import_channels_json(filepath):
    """Import channels from JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)

    if isinstance(data, list):
        # Simple list of channel dicts
        return [Channel.from_dict(d) for d in data]
    elif isinstance(data, dict) and "channels" in data:
        return [Channel.from_dict(d) for d in data["channels"]]
    else:
        raise ValueError("Unrecognized JSON format. Expected list or {channels: [...]}")


def export_full_backup(channels, settings_dict, search_dict, filepath):
    """Export a complete scanner backup (all channels + settings + search config)."""
    data = {
        "format": "bc125at-tool-backup",
        "version": 1,
        "exported": datetime.now().isoformat(),
        "channels": [ch.to_dict() for ch in channels],
        "settings": settings_dict,
        "search": search_dict,
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return filepath


def import_full_backup(filepath):
    """Import a complete scanner backup. Returns (channels, settings_dict, search_dict)."""
    with open(filepath, "r") as f:
        data = json.load(f)

    if data.get("format") != "bc125at-tool-backup":
        raise ValueError("Not a bc125at-tool backup file")

    channels = [Channel.from_dict(d) for d in data.get("channels", [])]
    settings = data.get("settings", {})
    search = data.get("search", {})
    return channels, settings, search


def import_auto(filepath):
    """Auto-detect file format and import channels."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".csv":
        return import_channels_csv(filepath)
    elif ext == ".json":
        return import_channels_json(filepath)
    else:
        # Try JSON first, then CSV
        try:
            return import_channels_json(filepath)
        except (json.JSONDecodeError, ValueError):
            return import_channels_csv(filepath)
