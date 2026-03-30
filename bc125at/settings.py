"""
BC125AT Scanner Settings

All global settings: backlight, battery, band plan, key beep,
priority mode, contrast, volume, squelch, weather alert.
"""

from dataclasses import dataclass

BACKLIGHT_OPTIONS = {
    "AO": "Always On",
    "AF": "Always Off",
    "KY": "Keypress",
    "SQ": "Squelch",
    "KS": "Key + Squelch",
}

PRIORITY_OPTIONS = {
    0: "Off",
    1: "On",
    2: "Plus On",
    3: "Do Not Disturb",
}

BAND_PLAN_OPTIONS = {
    0: "USA",
    1: "Canada",
}


@dataclass
class ScannerSettings:
    """All scanner global settings."""
    backlight: str = "KY"
    battery_charge_time: int = 13
    band_plan: int = 0
    key_beep_level: int = 0  # 0=Auto, 99=Off
    key_lock: bool = False
    priority_mode: int = 0
    contrast: int = 8
    volume: int = 8
    squelch: int = 4
    weather_alert: bool = False

    @property
    def backlight_display(self):
        return BACKLIGHT_OPTIONS.get(self.backlight, self.backlight)

    @property
    def priority_display(self):
        return PRIORITY_OPTIONS.get(self.priority_mode, str(self.priority_mode))

    @property
    def band_plan_display(self):
        return BAND_PLAN_OPTIONS.get(self.band_plan, str(self.band_plan))

    @property
    def key_beep_display(self):
        return "Off" if self.key_beep_level == 99 else "Auto"


class SettingsManager:
    """Read and write scanner global settings."""

    def __init__(self, conn):
        self.conn = conn

    def read_all(self):
        """Read all settings from the scanner."""
        self.conn.enter_program_mode()
        s = ScannerSettings()

        resp = self.conn.send_command("BLT")
        if resp and resp.startswith("BLT,"):
            s.backlight = resp.split(",")[1]

        resp = self.conn.send_command("BSV")
        if resp and resp.startswith("BSV,"):
            s.battery_charge_time = int(resp.split(",")[1])

        resp = self.conn.send_command("BPL")
        if resp and resp.startswith("BPL,"):
            s.band_plan = int(resp.split(",")[1])

        resp = self.conn.send_command("KBP")
        if resp and resp.startswith("KBP,"):
            parts = resp.split(",")
            s.key_beep_level = int(parts[1])
            s.key_lock = parts[2] == "1"

        resp = self.conn.send_command("PRI")
        if resp and resp.startswith("PRI,"):
            s.priority_mode = int(resp.split(",")[1])

        resp = self.conn.send_command("CNT")
        if resp and resp.startswith("CNT,"):
            s.contrast = int(resp.split(",")[1])

        resp = self.conn.send_command("WXS")
        if resp and resp.startswith("WXS,"):
            s.weather_alert = resp.split(",")[1] == "1"

        # VOL and SQL don't require program mode but work in it too
        resp = self.conn.send_command("VOL")
        if resp and resp.startswith("VOL,"):
            s.volume = int(resp.split(",")[1])

        resp = self.conn.send_command("SQL")
        if resp and resp.startswith("SQL,"):
            s.squelch = int(resp.split(",")[1])

        return s

    def write_all(self, settings):
        """Write all settings to the scanner."""
        self.conn.enter_program_mode()

        cmds = [
            (f"BLT,{settings.backlight}", "BLT,OK"),
            (f"BSV,{settings.battery_charge_time}", "BSV,OK"),
            (f"BPL,{settings.band_plan}", "BPL,OK"),
            (f"KBP,{settings.key_beep_level},{1 if settings.key_lock else 0}", "KBP,OK"),
            (f"PRI,{settings.priority_mode}", "PRI,OK"),
            (f"CNT,{settings.contrast}", "CNT,OK"),
            (f"WXS,{1 if settings.weather_alert else 0}", "WXS,OK"),
            (f"VOL,{settings.volume}", "VOL,OK"),
            (f"SQL,{settings.squelch}", "SQL,OK"),
        ]

        for cmd, expected in cmds:
            resp = self.conn.send_command(cmd)
            if resp != expected:
                raise ConnectionError(f"Failed to set {cmd}: {resp}")

        return True

    def set_backlight(self, mode):
        if mode not in BACKLIGHT_OPTIONS:
            raise ValueError(f"Invalid backlight mode. Options: {list(BACKLIGHT_OPTIONS.keys())}")
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"BLT,{mode}")
        if resp != "BLT,OK":
            raise ConnectionError(f"Failed to set backlight: {resp}")

    def set_volume(self, level):
        if not 0 <= level <= 15:
            raise ValueError("Volume must be 0-15")
        resp = self.conn.send_command(f"VOL,{level}")
        if resp != "VOL,OK":
            raise ConnectionError(f"Failed to set volume: {resp}")

    def set_squelch(self, level):
        if not 0 <= level <= 15:
            raise ValueError("Squelch must be 0-15")
        resp = self.conn.send_command(f"SQL,{level}")
        if resp != "SQL,OK":
            raise ConnectionError(f"Failed to set squelch: {resp}")

    def set_contrast(self, level):
        if not 1 <= level <= 15:
            raise ValueError("Contrast must be 1-15")
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"CNT,{level}")
        if resp != "CNT,OK":
            raise ConnectionError(f"Failed to set contrast: {resp}")

    def set_priority(self, mode):
        if mode not in PRIORITY_OPTIONS:
            raise ValueError(f"Invalid priority mode. Options: {list(PRIORITY_OPTIONS.keys())}")
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"PRI,{mode}")
        if resp != "PRI,OK":
            raise ConnectionError(f"Failed to set priority: {resp}")

    def set_weather_alert(self, enabled):
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"WXS,{1 if enabled else 0}")
        if resp != "WXS,OK":
            raise ConnectionError(f"Failed to set weather alert: {resp}")
