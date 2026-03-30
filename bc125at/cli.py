#!/usr/bin/env python3
"""
BC125AT Scanner Programming Tool for macOS

Full-featured CLI for programming the Uniden BC125AT scanner via USB.
No Windows required. No kernel serial driver required.
"""

import argparse
import sys
import os
import time
from datetime import datetime

from .connection import ScannerConnection
from .channels import Channel, ChannelManager, NUM_CHANNELS, CHANNELS_PER_BANK
from .channels import CTCSS_TONES, DCS_CODES, MODULATION_MODES, DELAY_VALUES
from .channels import tone_code_to_string, is_valid_frequency, FREQ_RANGES
from .settings import SettingsManager, ScannerSettings, BACKLIGHT_OPTIONS, PRIORITY_OPTIONS
from .search import SearchManager, CloseCallSettings, SearchSettings, CustomSearchRange
from .search import CC_MODE_OPTIONS, CC_BANDS, SERVICE_GROUPS
from .presets import list_presets, get_preset_channels, PRESET_CATALOG
from .io import (
    export_channels_csv, export_channels_json, import_channels_csv,
    import_channels_json, export_full_backup, import_full_backup, import_auto,
)


def progress_bar(current, total, prefix="", width=40):
    """Print a progress bar."""
    pct = current / total
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    sys.stdout.write(f"\r{prefix} [{bar}] {current}/{total} ({pct:.0%})")
    sys.stdout.flush()
    if current == total:
        print()


def print_table(headers, rows, min_widths=None):
    """Print a formatted table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))
    if min_widths:
        for i, mw in enumerate(min_widths):
            if i < len(widths):
                widths[i] = max(widths[i], mw)

    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("  ".join("─" * w for w in widths))
    for row in rows:
        cells = [str(c).ljust(widths[i]) if i < len(widths) else str(c) for i, c in enumerate(row)]
        print("  ".join(cells))


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

def cmd_info(args):
    """Show scanner info and status."""
    with ScannerConnection() as conn:
        model = conn.get_model() or ""
        version = conn.get_version() or ""
        status = conn.get_status() or ""

        # Strip command prefix for display (e.g. "MDL,BC125AT" -> "BC125AT")
        model_val = model.split(",", 1)[1] if "," in model else model
        ver_val = version.split(",", 1)[1] if "," in version else version

        print(f"Model:    {model_val}")
        print(f"Firmware: {ver_val}")
        print(f"Status:   {status}")
        print()

        # Read settings summary
        sm = SettingsManager(conn)
        s = sm.read_all()
        print("Settings:")
        print(f"  Volume:      {s.volume}/15")
        print(f"  Squelch:     {s.squelch}/15")
        print(f"  Backlight:   {s.backlight_display}")
        print(f"  Contrast:    {s.contrast}/15")
        print(f"  Priority:    {s.priority_display}")
        print(f"  Key Beep:    {s.key_beep_display}")
        print(f"  Key Lock:    {'On' if s.key_lock else 'Off'}")
        print(f"  Band Plan:   {s.band_plan_display}")
        print(f"  WX Alert:    {'On' if s.weather_alert else 'Off'}")
        print(f"  Battery Tmr: {s.battery_charge_time}h")

        # Bank status
        cm = ChannelManager(conn)
        banks = cm.get_bank_status()
        bank_str = " ".join(
            f"[{'✓' if banks.get(i, True) else '✗'} B{i}]"
            for i in ([1, 2, 3, 4, 5, 6, 7, 8, 9, 0])
        )
        print(f"\nBanks:     {bank_str}")


def cmd_monitor(args):
    """Live monitor — show what the scanner is currently receiving."""
    with ScannerConnection() as conn:
        print("Live Monitor (Ctrl+C to stop)\n")
        try:
            while True:
                resp = conn.get_live_info()
                if resp:
                    parts = resp.split(",")
                    # GLG response fields
                    freq_raw = parts[1] if len(parts) > 1 else ""
                    mod = parts[2] if len(parts) > 2 else ""
                    try:
                        freq = int(freq_raw) / 10000.0 if freq_raw else 0
                        freq_str = f"{freq:.4f} MHz" if freq > 0 else "---"
                    except ValueError:
                        freq_str = freq_raw
                    name = parts[7].strip() if len(parts) > 7 else ""
                    sql = parts[8] if len(parts) > 8 else ""
                    ch = parts[11] if len(parts) > 11 else ""

                    status = "OPEN" if sql == "1" else "    "
                    line = f"  {status}  {freq_str:>16s}  {mod:>4s}  CH{ch:>3s}  {name}"
                    sys.stdout.write(f"\r{line:<70s}")
                    sys.stdout.flush()
                time.sleep(0.3)
        except KeyboardInterrupt:
            print("\n\nMonitor stopped.")


def cmd_channels(args):
    """Read and display channels."""
    with ScannerConnection() as conn:
        cm = ChannelManager(conn)

        if args.channel:
            # Show single channel
            ch = cm.read_channel(args.channel)
            print(f"Channel {ch.index} (Bank {ch.bank}, Position {ch.bank_position}):")
            print(f"  Name:       {ch.name or '(empty)'}")
            print(f"  Frequency:  {ch.freq_display}")
            print(f"  Modulation: {ch.modulation}")
            print(f"  Tone:       {ch.tone_string}")
            print(f"  Delay:      {ch.delay}s")
            print(f"  Lockout:    {'Yes' if ch.lockout else 'No'}")
            print(f"  Priority:   {'Yes' if ch.priority else 'No'}")
            return

        # Show range of channels
        if args.bank is not None:
            channels = cm.read_bank(args.bank)
            label = f"Bank {args.bank}"
        else:
            start = args.start or 1
            end = args.end or NUM_CHANNELS
            channels = []
            total = end - start + 1
            for i in range(start, end + 1):
                ch = cm.read_channel(i)
                channels.append(ch)
                progress_bar(i - start + 1, total, "Reading")
            label = f"Channels {start}-{end}"

        # Filter empty if requested
        if not args.show_empty:
            channels = [ch for ch in channels if not ch.is_empty]

        if not channels:
            print(f"{label}: No programmed channels found.")
            return

        print(f"\n{label} ({len(channels)} channels):\n")
        headers = ["CH", "Name", "Frequency", "Mod", "Tone", "Dly", "L/O", "Pri"]
        rows = []
        for ch in channels:
            rows.append([
                str(ch.index),
                ch.name or "",
                ch.freq_display if not ch.is_empty else "",
                ch.modulation if not ch.is_empty else "",
                ch.tone_string if not ch.is_empty else "",
                str(ch.delay) if not ch.is_empty else "",
                "L/O" if ch.lockout else "",
                "PRI" if ch.priority else "",
            ])
        print_table(headers, rows)


def cmd_set_channel(args):
    """Program a single channel."""
    if not is_valid_frequency(args.frequency):
        print(f"Error: {args.frequency} MHz is outside valid ranges:")
        for lo, hi in FREQ_RANGES:
            print(f"  {lo:.4f} - {hi:.4f} MHz")
        sys.exit(1)

    tone_code = 0
    if args.tone:
        from .channels import string_to_tone_code
        try:
            tone_code = string_to_tone_code(args.tone)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    ch = Channel(
        index=args.channel,
        name=args.name or "",
        frequency=args.frequency,
        modulation=args.modulation or "AUTO",
        tone_code=tone_code,
        delay=args.delay if args.delay is not None else 2,
        lockout=args.lockout or False,
        priority=args.priority or False,
    )

    with ScannerConnection() as conn:
        cm = ChannelManager(conn)
        cm.write_channel(ch)
        print(f"Channel {ch.index} programmed: {ch.name} {ch.freq_display} {ch.modulation}")


def cmd_delete_channel(args):
    """Delete one or more channels."""
    with ScannerConnection() as conn:
        cm = ChannelManager(conn)
        for idx in args.channels:
            cm.delete_channel(idx)
            print(f"Channel {idx} deleted.")


def cmd_settings(args):
    """Read or modify scanner settings."""
    with ScannerConnection() as conn:
        sm = SettingsManager(conn)

        if args.setting == "show":
            s = sm.read_all()
            print("Scanner Settings:")
            print(f"  backlight:   {s.backlight} ({s.backlight_display})")
            print(f"  volume:      {s.volume}")
            print(f"  squelch:     {s.squelch}")
            print(f"  contrast:    {s.contrast}")
            print(f"  priority:    {s.priority_mode} ({s.priority_display})")
            print(f"  keybeep:     {s.key_beep_level} ({s.key_beep_display})")
            print(f"  keylock:     {1 if s.key_lock else 0} ({'On' if s.key_lock else 'Off'})")
            print(f"  bandplan:    {s.band_plan} ({s.band_plan_display})")
            print(f"  wxalert:     {1 if s.weather_alert else 0} ({'On' if s.weather_alert else 'Off'})")
            print(f"  battery:     {s.battery_charge_time}")
            return

        # Set a specific setting
        setting = args.setting
        value = args.value

        if setting == "volume":
            sm.set_volume(int(value))
        elif setting == "squelch":
            sm.set_squelch(int(value))
        elif setting == "contrast":
            sm.set_contrast(int(value))
        elif setting == "backlight":
            sm.set_backlight(value.upper())
        elif setting == "priority":
            sm.set_priority(int(value))
        elif setting == "wxalert":
            sm.set_weather_alert(value.lower() in ("1", "on", "true", "yes"))
        else:
            print(f"Unknown setting: {setting}")
            print("Available: volume, squelch, contrast, backlight, priority, wxalert")
            sys.exit(1)

        print(f"Set {setting} = {value}")


def cmd_search(args):
    """Read or modify search/Close Call settings."""
    with ScannerConnection() as conn:
        srch = SearchManager(conn)

        if args.search_cmd == "show":
            # Show all search settings
            ss = srch.read_search_settings()
            cc = srch.read_close_call()
            sg = srch.read_service_groups()
            csg = srch.read_custom_search_groups()

            print("Search Settings:")
            print(f"  Delay:       {ss.delay}s")
            print(f"  Code Search: {'On' if ss.code_search else 'Off'}")

            print(f"\nClose Call:")
            print(f"  Mode:        {cc.mode_display}")
            print(f"  Alert Beep:  {'On' if cc.alert_beep else 'Off'}")
            print(f"  Alert Light: {'On' if cc.alert_light else 'Off'}")
            print(f"  Lockout:     {'On' if cc.lockout else 'Off'}")
            print(f"  Bands:")
            for i, name in enumerate(CC_BANDS):
                status = "On" if cc.bands[i] else "Off"
                print(f"    {name}: {status}")

            print(f"\nService Search Groups:")
            for name, enabled in sg.items():
                print(f"  {name}: {'On' if enabled else 'Off'}")

            print(f"\nCustom Search Groups:")
            for num, enabled in sorted(csg.items()):
                print(f"  Group {num}: {'On' if enabled else 'Off'}")

            print(f"\nCustom Search Ranges:")
            ranges = srch.read_all_custom_search_ranges()
            for r in ranges:
                print(f"  Range {r.index}: {r.lower_freq:.4f} - {r.upper_freq:.4f} MHz")

        elif args.search_cmd == "range":
            if args.range_index and args.lower and args.upper:
                sr = CustomSearchRange(
                    index=int(args.range_index),
                    lower_freq=float(args.lower),
                    upper_freq=float(args.upper),
                )
                srch.write_custom_search_range(sr)
                print(f"Search range {sr.index} set: {sr.lower_freq:.4f} - {sr.upper_freq:.4f} MHz")
            else:
                ranges = srch.read_all_custom_search_ranges()
                for r in ranges:
                    print(f"Range {r.index}: {r.lower_freq:.4f} - {r.upper_freq:.4f} MHz")

        elif args.search_cmd == "lockouts":
            freqs = srch.read_lockout_frequencies()
            if freqs:
                print(f"Locked out frequencies ({len(freqs)}):")
                for f in freqs:
                    print(f"  {f:.4f} MHz")
            else:
                print("No locked out frequencies.")

        elif args.search_cmd == "closecall":
            cc = srch.read_close_call()
            if args.mode is not None:
                cc.mode = int(args.mode)
            srch.write_close_call(cc)
            print(f"Close Call mode set: {cc.mode_display}")


def cmd_presets(args):
    """List or load frequency presets."""
    if args.preset_cmd == "list":
        presets = list_presets()
        print("Available Presets:\n")
        for key, info in presets.items():
            print(f"  {key:<15s} {info['name']}")
            print(f"  {'':<15s} {info['description']}")
            print(f"  {'':<15s} Channels: {info['channel_count']}, Suggested bank: {info['bank_suggestion']}")
            print()
        return

    if args.preset_cmd == "show":
        if not args.preset_name:
            print("Error: specify preset name. Use 'presets list' to see options.")
            sys.exit(1)
        if args.preset_name not in PRESET_CATALOG:
            print(f"Unknown preset: {args.preset_name}")
            sys.exit(1)
        preset = PRESET_CATALOG[args.preset_name]
        print(f"{preset['name']}:\n{preset['description']}\n")
        headers = ["#", "Name", "Frequency"]
        rows = [(str(i + 1), name, f"{freq:.4f} MHz")
                for i, (name, freq) in enumerate(preset["frequencies"])]
        print_table(headers, rows)
        return

    if args.preset_cmd == "load":
        if not args.preset_name:
            print("Error: specify preset name. Use 'presets list' to see options.")
            sys.exit(1)

        bank = args.bank
        start = args.start

        try:
            channels = get_preset_channels(args.preset_name, start_channel=start, bank=bank)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

        print(f"Loading preset '{args.preset_name}' ({len(channels)} channels) "
              f"into channels {channels[0].index}-{channels[-1].index}...")

        with ScannerConnection() as conn:
            cm = ChannelManager(conn)
            for i, ch in enumerate(channels):
                cm.write_channel(ch)
                progress_bar(i + 1, len(channels), "Writing")

        print(f"Loaded {len(channels)} channels successfully.")


def cmd_export(args):
    """Export channels to file."""
    with ScannerConnection() as conn:
        cm = ChannelManager(conn)

        if args.full_backup:
            # Full backup including settings and search
            print("Reading all channels...")
            channels = cm.read_all_channels(
                callback=lambda i, ch: progress_bar(i, NUM_CHANNELS, "Reading")
            )

            sm = SettingsManager(conn)
            s = sm.read_all()
            settings_dict = {
                "backlight": s.backlight,
                "battery_charge_time": s.battery_charge_time,
                "band_plan": s.band_plan,
                "key_beep_level": s.key_beep_level,
                "key_lock": s.key_lock,
                "priority_mode": s.priority_mode,
                "contrast": s.contrast,
                "volume": s.volume,
                "squelch": s.squelch,
                "weather_alert": s.weather_alert,
            }

            srch = SearchManager(conn)
            ss = srch.read_search_settings()
            cc = srch.read_close_call()
            sg = srch.read_service_groups()
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
                "service_groups": sg,
            }

            filepath = args.file or f"bc125at_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            export_full_backup(channels, settings_dict, search_dict, filepath)
            print(f"\nFull backup saved to: {filepath}")
        else:
            # Channels only
            print("Reading all channels...")
            channels = cm.read_all_channels(
                callback=lambda i, ch: progress_bar(i, NUM_CHANNELS, "Reading")
            )

            # Filter empty channels unless --include-empty
            if not args.include_empty:
                channels = [ch for ch in channels if not ch.is_empty]

            filepath = args.file
            if not filepath:
                ext = "csv" if args.format == "csv" else "json"
                filepath = f"bc125at_channels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"

            if args.format == "csv":
                export_channels_csv(channels, filepath)
            else:
                export_channels_json(channels, filepath)

            print(f"\nExported {len(channels)} channels to: {filepath}")


def cmd_import(args):
    """Import channels from file."""
    if not os.path.exists(args.file):
        print(f"Error: file not found: {args.file}")
        sys.exit(1)

    filepath = args.file

    if filepath.endswith(".json"):
        # Check if it's a full backup
        import json
        with open(filepath) as f:
            data = json.load(f)
        if data.get("format") == "bc125at-tool-backup":
            channels, settings_dict, search_dict = import_full_backup(filepath)
            print(f"Full backup detected: {len(channels)} channels + settings")

            with ScannerConnection() as conn:
                cm = ChannelManager(conn)
                print("Writing channels...")
                cm.write_channels(
                    channels,
                    callback=lambda i, ch: progress_bar(i, len(channels), "Writing")
                )

                if settings_dict:
                    print("Restoring settings...")
                    sm = SettingsManager(conn)
                    s = ScannerSettings(**settings_dict)
                    sm.write_all(s)

                # Search settings restoration
                if search_dict:
                    print("Restoring search settings...")
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

            print(f"\nFull backup restored successfully.")
            return

    # Regular channel import
    channels = import_auto(filepath)
    print(f"Loaded {len(channels)} channels from {filepath}")

    if args.bank is not None:
        # Remap to specific bank
        if args.bank == 0:
            start = 451
        else:
            start = (args.bank - 1) * 50 + 1
        for i, ch in enumerate(channels):
            ch.index = start + i
        print(f"Remapped to bank {args.bank} (channels {start}-{start + len(channels) - 1})")

    with ScannerConnection() as conn:
        cm = ChannelManager(conn)
        cm.write_channels(
            channels,
            callback=lambda i, ch: progress_bar(i, len(channels), "Writing")
        )

    print(f"\nImported {len(channels)} channels successfully.")


def cmd_tones(args):
    """List all CTCSS/DCS tone codes."""
    print("CTCSS Tones:\n")
    headers = ["Code", "Frequency"]
    rows = [(str(code), f"{freq} Hz") for code, freq in sorted(CTCSS_TONES.items())]
    print_table(headers, rows)

    print("\nDCS Codes:\n")
    headers = ["Code", "DCS"]
    rows = [(str(code), f"{dcs:03d}") for code, dcs in sorted(DCS_CODES.items())]
    print_table(headers, rows)

    print(f"\nSpecial: 0=None, 127=Search, 240=No Tone")


def cmd_banks(args):
    """Show or modify bank status."""
    with ScannerConnection() as conn:
        cm = ChannelManager(conn)

        if args.enable is not None or args.disable is not None:
            banks = cm.get_bank_status()
            if args.enable is not None:
                for b in args.enable:
                    banks[b] = True
            if args.disable is not None:
                for b in args.disable:
                    banks[b] = False
            cm.set_bank_status(banks)
            print("Bank status updated.")

        banks = cm.get_bank_status()
        print("Bank Status:\n")
        for i in [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]:
            status = "Enabled" if banks.get(i, True) else "Disabled"
            ch_start = (i - 1) * 50 + 1 if i > 0 else 451
            ch_end = ch_start + 49
            print(f"  Bank {i}: {status:>8s}  (CH {ch_start}-{ch_end})")


# =============================================================================
# MAIN CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="bc125at",
        description="BC125AT Scanner Programming Tool for macOS",
        epilog="No firmware update capability — channel/settings programming only.",
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # --- info ---
    sub.add_parser("info", help="Show scanner info, settings, and status")

    # --- monitor ---
    sub.add_parser("monitor", help="Live monitor — show current scanner reception")

    # --- channels ---
    p_ch = sub.add_parser("channels", help="Read and display channels")
    p_ch.add_argument("channel", type=int, nargs="?", help="Specific channel number (1-500)")
    p_ch.add_argument("--bank", "-b", type=int, help="Show specific bank (0-9)")
    p_ch.add_argument("--start", "-s", type=int, help="Start channel")
    p_ch.add_argument("--end", "-e", type=int, help="End channel")
    p_ch.add_argument("--show-empty", action="store_true", help="Include empty channels")

    # --- set ---
    p_set = sub.add_parser("set", help="Program a channel")
    p_set.add_argument("channel", type=int, help="Channel number (1-500)")
    p_set.add_argument("frequency", type=float, help="Frequency in MHz (e.g. 155.0000)")
    p_set.add_argument("--name", "-n", help="Channel name (max 16 chars)")
    p_set.add_argument("--modulation", "-m", choices=MODULATION_MODES, help="Modulation mode")
    p_set.add_argument("--tone", "-t", help="CTCSS/DCS tone (e.g. '100.0', 'DCS 023', 'none')")
    p_set.add_argument("--delay", "-d", type=int, choices=DELAY_VALUES, help="Delay in seconds")
    p_set.add_argument("--lockout", "-l", action="store_true", help="Lock out channel")
    p_set.add_argument("--priority", "-p", action="store_true", help="Set as priority channel")

    # --- delete ---
    p_del = sub.add_parser("delete", help="Delete (clear) channels")
    p_del.add_argument("channels", type=int, nargs="+", help="Channel numbers to delete")

    # --- settings ---
    p_stg = sub.add_parser("settings", help="Read or modify scanner settings")
    p_stg.add_argument("setting", nargs="?", default="show",
                        help="Setting name (volume/squelch/contrast/backlight/priority/wxalert) or 'show'")
    p_stg.add_argument("value", nargs="?", help="New value to set")

    # --- search ---
    p_srch = sub.add_parser("search", help="Search and Close Call settings")
    p_srch.add_argument("search_cmd", nargs="?", default="show",
                         choices=["show", "range", "lockouts", "closecall"],
                         help="Search subcommand")
    p_srch.add_argument("--range-index", type=int, help="Search range index (1-10)")
    p_srch.add_argument("--lower", type=float, help="Lower frequency (MHz)")
    p_srch.add_argument("--upper", type=float, help="Upper frequency (MHz)")
    p_srch.add_argument("--mode", type=int, choices=[0, 1, 2, 3], help="Close Call mode")

    # --- presets ---
    p_pre = sub.add_parser("presets", help="List or load frequency presets")
    p_pre.add_argument("preset_cmd", choices=["list", "show", "load"],
                        help="list/show/load presets")
    p_pre.add_argument("preset_name", nargs="?", help="Preset name")
    p_pre.add_argument("--bank", "-b", type=int, help="Bank to load into (0-9)")
    p_pre.add_argument("--start", "-s", type=int, help="Starting channel number")

    # --- export ---
    p_exp = sub.add_parser("export", help="Export channels to CSV or JSON")
    p_exp.add_argument("file", nargs="?", help="Output file path")
    p_exp.add_argument("--format", "-f", choices=["csv", "json"], default="csv",
                        help="Export format (default: csv)")
    p_exp.add_argument("--full-backup", action="store_true",
                        help="Full backup including settings and search config")
    p_exp.add_argument("--include-empty", action="store_true",
                        help="Include empty channels in export")

    # --- import ---
    p_imp = sub.add_parser("import", help="Import channels from CSV or JSON")
    p_imp.add_argument("file", help="Input file path")
    p_imp.add_argument("--bank", "-b", type=int, help="Remap channels to this bank (0-9)")

    # --- banks ---
    p_bank = sub.add_parser("banks", help="Show or modify bank enable/disable")
    p_bank.add_argument("--enable", type=int, nargs="+", help="Banks to enable")
    p_bank.add_argument("--disable", type=int, nargs="+", help="Banks to disable")

    # --- tones ---
    sub.add_parser("tones", help="List all CTCSS/DCS tone codes")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Route to command handler
    commands = {
        "info": cmd_info,
        "monitor": cmd_monitor,
        "channels": cmd_channels,
        "set": cmd_set_channel,
        "delete": cmd_delete_channel,
        "settings": cmd_settings,
        "search": cmd_search,
        "presets": cmd_presets,
        "export": cmd_export,
        "import": cmd_import,
        "banks": cmd_banks,
        "tones": cmd_tones,
    }

    try:
        commands[args.command](args)
    except ConnectionError as e:
        print(f"\nConnection error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
