"""
BC125AT Import/Export

Export channels and settings to CSV/JSON for backup.
Import from CSV/JSON to restore or load new programming.
"""

import csv
import json
import os
import re
from datetime import datetime
from io import StringIO
from .channels import Channel, NUM_CHANNELS
from .settings import ScannerSettings
from .search import SERVICE_GROUPS


class ImportParseError(ValueError):
    """Raised when import data cannot be normalized into scanner channels."""


def _first_present(mapping, *keys):
    """Return the first non-None value found in mapping for the given keys."""
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _bank_to_start_index(bank):
    """Convert a bank number (1-9, 0 for bank 10) to its starting channel index."""
    try:
        bank = int(bank)
    except (TypeError, ValueError):
        return None
    if bank == 0:
        return 451
    if 1 <= bank <= 9:
        return (bank - 1) * 50 + 1
    return None


def _normalize_import_channel(row, sequence_index=None, metadata=None, source_label="entry", source_number=None):
    """Normalize flexible import keys into the app's canonical channel schema."""
    metadata = metadata or {}

    channel = _first_present(row, "channel", "channel_index", "index", "slot", "number")
    if channel is None:
        bank_start = _bank_to_start_index(_first_present(metadata, "bank_target", "bank"))
        if bank_start is not None and sequence_index is not None:
            channel = bank_start + sequence_index
        elif sequence_index is not None:
            channel = sequence_index + 1

    if channel is None:
        raise ValueError(
            "Each imported channel needs a channel number/index, or metadata.bank_target "
            "so channels can be placed sequentially."
        )

    normalized = {
        "channel": channel,
        "name": _first_present(row, "name", "alpha_tag", "alpha", "tag", "label") or "",
        "frequency": _first_present(row, "frequency", "freq", "mhz"),
        "modulation": _first_present(row, "modulation", "mode", "mod") or "AUTO",
        "tone_code": _first_present(row, "tone_code", "ctcss_dcs_code"),
        "tone": _first_present(row, "tone", "ctcss_dcs", "ctcss", "dcs"),
        "delay": _first_present(row, "delay", "delay_sec", "delay_seconds", "delay_time"),
        "lockout": _first_present(row, "lockout", "lout", "locked_out"),
        "priority": _first_present(row, "priority", "pri", "priority_channel"),
    }

    location = f"{source_label} {source_number}: " if source_number is not None else ""
    try:
        return Channel.from_dict(normalized)
    except Exception as e:
        raise ImportParseError(f"{location}{e}") from e


def _normalize_import_rows(rows, metadata=None, source_label="entry", start_number=1):
    """Normalize a sequence of imported channel mappings."""
    return [
        _normalize_import_channel(
            row,
            sequence_index=i,
            metadata=metadata,
            source_label=source_label,
            source_number=start_number + i,
        )
        for i, row in enumerate(rows)
    ]


def _parse_csv_text(text):
    """Parse CSV/TSV text with a header row into channels."""
    sample = text.strip()
    if not sample:
        raise ValueError("No import data provided")

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    raw_rows = list(csv.reader(StringIO(text), dialect=dialect))
    if not raw_rows:
        raise ValueError("CSV text must include a header row")

    headers = raw_rows[0]
    if not headers:
        raise ValueError("CSV text must include a header row")

    lowered = {field.strip().lower() for field in headers if field}
    recognized = {
        "channel", "channel_index", "index", "slot", "number",
        "name", "alpha_tag", "alpha", "tag", "label",
        "frequency", "freq", "mhz",
    }
    if {"car", "driver", "primary"}.issubset(lowered):
        return _parse_race_csv_table(headers, raw_rows[1:])
    if not lowered.intersection(recognized):
        raise ValueError("CSV text is missing recognizable channel headers")

    reader = csv.DictReader(StringIO(text), dialect=dialect)
    rows = [row for row in reader if row]
    return _normalize_import_rows(rows, source_label="CSV row", start_number=2)


def _clean_frequency(value):
    """Normalize a possible frequency cell from imported text."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("MHz", "").replace("mhz", "").strip()
    try:
        return f"{float(text):.4f}"
    except ValueError:
        return None


def _short_channel_name(car, driver, label):
    """Build a scanner-friendly alpha tag from race CSV data."""
    surname = (driver or "").strip().split()[-1] if driver else "Driver"
    base = f"{str(car).strip()} {surname} {label}".strip()
    return base[:16]


def _parse_race_csv_table(headers, rows):
    """Expand race-style CSV rows into one scanner channel per listed frequency."""
    channels = []
    lower_headers = [str(h).strip().lower() for h in headers]
    try:
        car_idx = lower_headers.index("car")
        driver_idx = lower_headers.index("driver")
    except ValueError as e:
        raise ValueError("Race CSV must include Car and Driver columns") from e

    freq_specs = []
    for idx, header in enumerate(headers):
        label = str(header).strip().lower()
        if label == "primary":
            freq_specs.append((idx, "PRI", idx + 1))
        elif label == "secondary":
            freq_specs.append((idx, "SEC", idx + 1))
        elif label.startswith("other"):
            suffix = label.replace("other", "").strip()
            short = "ALT" if not suffix else f"ALT{suffix}"
            freq_specs.append((idx, short[:4], idx + 1))

    for row_number, row in enumerate(rows, start=2):
        if not row:
            continue
        car = row[car_idx].strip() if car_idx < len(row) else ""
        driver = row[driver_idx].strip() if driver_idx < len(row) else ""
        if not car and not driver:
            continue

        row_channels = 0
        for freq_idx, label, tone_idx in freq_specs:
            cell = row[freq_idx] if freq_idx < len(row) else ""
            freq = _clean_frequency(cell)
            if not freq:
                continue
            tone = row[tone_idx].strip() if tone_idx < len(row) else ""
            channels.append({
                "name": _short_channel_name(car, driver, label),
                "frequency": freq,
                "modulation": "NFM",
                "tone": tone or "None",
            })
            row_channels += 1

        if row_channels == 0:
            raise ImportParseError(
                f"CSV row {row_number}: no usable race frequencies found in Primary/Secondary/Other columns"
            )

    if not channels:
        raise ValueError("Race CSV did not contain any usable frequencies")

    return _normalize_import_rows(channels, source_label="Race CSV row", start_number=2)


def _parse_frequency_lines(text):
    """Parse simple pasted line lists into channels."""
    rows = []
    for line_number, line in enumerate(text.splitlines(), 1):
        raw = line.strip()
        if not raw:
            continue
        match = re.search(r"(?<!\d)(\d{2,3}\.\d{3,4})(?!\d)", raw)
        if not match:
            continue

        frequency = match.group(1)
        before = raw[:match.start()].strip(" \t,-|:")
        after = raw[match.end():].strip(" \t,-|:")
        name = after or before or ""
        rows.append((line_number, {"frequency": frequency, "name": name}))

    if not rows:
        raise ValueError(
            "Paste JSON, CSV with a header row, or one channel per line with a frequency "
            "such as '146.520 Simplex'."
        )

    channels = []
    for sequence_index, (line_number, row) in enumerate(rows):
        channels.append(
            _normalize_import_channel(
                row,
                sequence_index=sequence_index,
                source_label="Line",
                source_number=line_number,
            )
        )
    return channels


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
        for i, row in enumerate(reader):
            if not any((value or "").strip() for value in row.values() if isinstance(value, str)):
                continue
            # Handle boolean fields that may be strings
            for bool_field in ("lockout", "priority"):
                if bool_field in row:
                    val = row[bool_field]
                    if isinstance(val, str):
                        row[bool_field] = val.lower() in ("true", "1", "yes")
            channels.append(_normalize_import_channel(row, sequence_index=i))
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
        return _normalize_import_rows(data, source_label="JSON entry", start_number=1)
    elif isinstance(data, dict) and "channels" in data:
        metadata = data.get("metadata", {})
        return _normalize_import_rows(
            data["channels"],
            metadata=metadata,
            source_label="JSON channel",
            start_number=1,
        )
    else:
        raise ValueError(
            "Unrecognized JSON format. Expected a list of channels or an object with "
            "'channels'. Recommended keys are channel/name/frequency/modulation/tone."
        )


def import_channels_text(text):
    """Import channels from pasted JSON, CSV/TSV, or simple line-based text."""
    if not text or not text.strip():
        raise ValueError("No import data provided")

    stripped = text.strip()

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, list):
        return _normalize_import_rows(data, source_label="JSON entry", start_number=1)
    if isinstance(data, dict):
        if data.get("format") == "bc125at-tool-backup":
            raise ValueError("Full backup restore requires a file upload")
        if "channels" in data:
            return _normalize_import_rows(
                data["channels"],
                metadata=data.get("metadata", {}),
                source_label="JSON channel",
                start_number=1,
            )

    try:
        return _parse_csv_text(text)
    except ImportParseError:
        raise
    except ValueError:
        return _parse_frequency_lines(text)


def _parse_on_off(value):
    return str(value).strip().lower() == "on"


def _hz_to_mhz(value):
    try:
        freq = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if freq <= 0:
        return None
    return freq / 1000000.0


def _parse_bc125at_ss_tone(value):
    text = str(value).strip()
    if not text or text.lower() == "off":
        return "None"
    return text


def import_bc125at_ss(filepath):
    """Import a Uniden BC125AT_SS season/profile file."""
    settings = ScannerSettings()
    search = {
        "delay": 2,
        "code_search": False,
        "close_call": {
            "mode": 0,
            "alert_beep": False,
            "alert_light": False,
            "bands": [True] * 5,
            "lockout": False,
        },
        "service_groups": {name: False for name in SERVICE_GROUPS},
        "custom_groups": {i: False for i in range(1, 11)},
        "search_ranges": [],
    }
    bank_status = {bank: False for bank in range(10)}
    channels = []

    priority_map = {
        "off": 0,
        "on": 1,
        "plus on": 2,
        "plus": 2,
        "dnd": 3,
        "do not disturb": 3,
    }
    close_call_mode_map = {
        "off": 0,
        "priority": 1,
        "dnd": 2,
        "cc only": 3,
        "only": 3,
    }
    backlight_map = {
        "key": "KY",
        "off": "AF",
        "on": "AO",
        "squelch": "SQ",
        "key+squelch": "KS",
        "key+squelch ": "KS",
    }

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line_number, line in enumerate(f, start=1):
            raw = line.rstrip("\r\n")
            if not raw.strip():
                continue
            parts = raw.split("\t")
            record = parts[0]

            if record == "Misc" and len(parts) >= 9:
                settings.backlight = backlight_map.get(parts[1].strip().lower(), settings.backlight)
                settings.key_beep_level = 99 if parts[2].strip().lower() == "off" else 0
                settings.key_lock = _parse_on_off(parts[3])
                try:
                    settings.contrast = int(parts[4])
                    settings.squelch = int(parts[5])
                    settings.volume = int(parts[6])
                    settings.battery_charge_time = int(parts[7])
                except ValueError as e:
                    raise ImportParseError(f"Line {line_number}: invalid Misc numeric values") from e
                settings.band_plan = 0 if parts[8].strip().upper() == "USA" else 1
            elif record == "Priority" and len(parts) >= 2:
                settings.priority_mode = priority_map.get(parts[1].strip().lower(), settings.priority_mode)
            elif record == "WxPri" and len(parts) >= 2:
                settings.weather_alert = _parse_on_off(parts[1])
            elif record == "Service" and len(parts) >= 4:
                name = parts[2].strip()
                if name in search["service_groups"]:
                    search["service_groups"][name] = _parse_on_off(parts[3])
            elif record == "Custom" and len(parts) >= 6:
                try:
                    index = int(parts[1])
                except ValueError as e:
                    raise ImportParseError(f"Line {line_number}: invalid custom search index") from e
                lower = _hz_to_mhz(parts[3])
                upper = _hz_to_mhz(parts[4])
                if lower is not None and upper is not None:
                    search["search_ranges"].append({
                        "index": index,
                        "lower_freq": lower,
                        "upper_freq": upper,
                    })
                search["custom_groups"][index] = _parse_on_off(parts[5])
            elif record == "CloseCall" and len(parts) >= 5:
                search["close_call"]["mode"] = close_call_mode_map.get(parts[1].strip().lower(), 0)
                search["close_call"]["alert_beep"] = _parse_on_off(parts[2])
                search["close_call"]["alert_light"] = _parse_on_off(parts[3])
                search["close_call"]["lockout"] = _parse_on_off(parts[4])
            elif record == "CloseCallBands" and len(parts) >= 6:
                search["close_call"]["bands"] = [_parse_on_off(value) for value in parts[1:6]]
            elif record == "GeneralSearch" and len(parts) >= 3:
                try:
                    search["delay"] = int(parts[1])
                except ValueError as e:
                    raise ImportParseError(f"Line {line_number}: invalid search delay") from e
                search["code_search"] = _parse_on_off(parts[2])
            elif record == "Conventional" and len(parts) >= 4:
                try:
                    bank_index = int(parts[1]) % 10
                except ValueError as e:
                    raise ImportParseError(f"Line {line_number}: invalid bank number") from e
                bank_status[bank_index] = _parse_on_off(parts[3])
            elif record == "C-Freq" and len(parts) >= 9:
                try:
                    channel_index = int(parts[1])
                except ValueError as e:
                    raise ImportParseError(f"Line {line_number}: invalid channel number") from e
                freq = _hz_to_mhz(parts[3])
                if freq is None:
                    continue
                channels.append(Channel.from_dict({
                    "channel": channel_index,
                    "name": parts[2].strip(),
                    "frequency": freq,
                    "modulation": str(parts[4]).strip().upper(),
                    "tone": _parse_bc125at_ss_tone(parts[5]),
                    "lockout": _parse_on_off(parts[6]),
                    "delay": parts[7],
                    "priority": _parse_on_off(parts[8]),
                }))

    if not channels:
        raise ValueError("No usable channels found in BC125AT_SS file")

    search["search_ranges"] = sorted(search["search_ranges"], key=lambda item: item["index"])
    return channels, settings.__dict__, search, bank_status


def export_bc125at_ss(channels, settings_dict, search_dict, bank_status, filepath):
    """Export a Uniden BC125AT_SS-style season/profile file."""
    settings = ScannerSettings(**settings_dict)

    backlight_label = {
        "KY": "Key",
        "KS": "K+S",
        "SQ": "Squelch",
        "AF": "Off",
        "AO": "On",
    }.get(settings.backlight, settings.backlight)

    priority_label = {
        0: "Off",
        1: "On",
        2: "Plus On",
        3: "DND",
    }.get(int(settings.priority_mode), "Off")

    close_call_mode = {
        0: "Off",
        1: "Priority",
        2: "DND",
        3: "CC Only",
    }.get(int(search_dict.get("close_call", {}).get("mode", 0)), "Off")

    custom_ranges_by_index = {
        int(item["index"]): item for item in search_dict.get("search_ranges", [])
    }
    custom_groups = search_dict.get("custom_groups", {})
    service_groups = search_dict.get("service_groups", {})
    cc = search_dict.get("close_call", {})

    channel_map = {int(ch.index): ch for ch in channels}

    lines = []
    lines.append("\t".join([
        "Misc",
        backlight_label,
        "Off" if settings.key_beep_level == 99 else "Auto",
        "On" if settings.key_lock else "Off",
        str(int(settings.contrast)),
        str(int(settings.squelch)),
        str(int(settings.volume)),
        str(int(settings.battery_charge_time)),
        "USA" if int(settings.band_plan) == 0 else "Canada",
    ]))
    lines.append(f"Priority\t{priority_label}")
    lines.append(f"WxPri\t{'On' if settings.weather_alert else 'Off'}")

    for idx, name in enumerate(SERVICE_GROUPS, start=1):
        lines.append(f"Service\t{idx}\t{name}\t{'On' if service_groups.get(name, False) else 'Off'}")

    for index in range(1, 11):
        item = custom_ranges_by_index.get(index, {})
        lower = int(round(float(item.get("lower_freq", 25.0)) * 1000000))
        upper = int(round(float(item.get("upper_freq", 25.0)) * 1000000))
        lines.append(
            f"Custom\t{index}\tSearch Bnak{index}\t{lower}\t{upper}\t"
            f"{'On' if custom_groups.get(index, False) else 'Off'}"
        )

    lines.append(
        "CloseCall\t{mode}\t{beep}\t{light}\t{lockout}".format(
            mode=close_call_mode,
            beep="On" if cc.get("alert_beep", False) else "Off",
            light="On" if cc.get("alert_light", False) else "Off",
            lockout="On" if cc.get("lockout", False) else "Off",
        )
    )
    bands = cc.get("bands", [True] * 5)
    lines.append("CloseCallBands\t" + "\t".join("On" if enabled else "Off" for enabled in bands[:5]))
    lines.append(
        f"GeneralSearch\t{int(search_dict.get('delay', 2))}\t"
        f"{'On' if search_dict.get('code_search', False) else 'Off'}"
    )

    for bank in [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]:
        display_bank = 10 if bank == 0 else bank
        lines.append(
            f"Conventional\t{display_bank}\tBank {display_bank}\t"
            f"{'On' if bank_status.get(bank, False) else 'Off'}"
        )
        start = 451 if bank == 0 else (bank - 1) * 50 + 1
        for index in range(start, start + 50):
            ch = channel_map.get(index)
            if ch and not ch.is_empty:
                freq = int(round(float(ch.frequency) * 1000000))
                lines.append("\t".join([
                    "C-Freq",
                    str(index),
                    ch.name,
                    str(freq),
                    ch.modulation,
                    ch.tone_string if ch.tone_string != "None" else "Off",
                    "On" if ch.lockout else "Off",
                    str(int(ch.delay)),
                    "On" if ch.priority else "Off",
                ]))
            else:
                lines.append(f"C-Freq\t{index}\t\t0\tAuto\tOff\tOff\t2\tOff")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return filepath


def export_full_backup(channels, settings_dict, search_dict, bank_status, filepath):
    """Export a complete scanner backup (all channels + settings + search config)."""
    data = {
        "format": "bc125at-tool-backup",
        "version": 1,
        "exported": datetime.now().isoformat(),
        "channels": [ch.to_dict() for ch in channels],
        "settings": settings_dict,
        "search": search_dict,
        "banks": bank_status,
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return filepath


def import_full_backup(filepath):
    """Import a complete scanner backup. Returns (channels, settings_dict, search_dict, bank_status)."""
    with open(filepath, "r") as f:
        data = json.load(f)

    if data.get("format") != "bc125at-tool-backup":
        raise ValueError("Not a bc125at-tool backup file")

    channels = [Channel.from_dict(d) for d in data.get("channels", [])]
    settings = data.get("settings", {})
    search = data.get("search", {})
    bank_status = {int(k): v for k, v in data.get("banks", {}).items()}
    return channels, settings, search, bank_status


def import_auto(filepath):
    """Auto-detect file format and import channels."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".csv":
        return import_channels_csv(filepath)
    elif ext == ".json":
        return import_channels_json(filepath)
    elif ext == ".bc125at_ss":
        channels, _, _, _ = import_bc125at_ss(filepath)
        return channels
    else:
        # Try JSON first, then CSV
        try:
            return import_channels_json(filepath)
        except (json.JSONDecodeError, ValueError):
            return import_channels_csv(filepath)
