"""
BC125AT Search & Close Call Programming

Custom search ranges, service search groups, Close Call settings,
search/CC delay, and global frequency lockout management.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional

# Close Call band names (bit positions left to right)
CC_BANDS = ["VHF Low", "Civil Air", "VHF High", "Military Air", "UHF"]

CC_MODE_OPTIONS = {
    0: "Off",
    1: "CC Priority",
    2: "CC Do Not Disturb",
    3: "CC Only",
}

# Service search group names (bit positions left to right)
SERVICE_GROUPS = [
    "Police", "Fire/Emergency", "Ham Radio", "Marine", "Railroad",
    "Civil Air", "Military Air", "CB Radio", "FRS/GMRS/MURS", "Racing",
]

DELAY_VALUES = [-10, -5, 0, 1, 2, 3, 4, 5]


@dataclass
class CloseCallSettings:
    """Close Call configuration."""
    mode: int = 0  # 0=Off, 1=Priority, 2=DND, 3=CC Only
    alert_beep: bool = False
    alert_light: bool = False
    bands: List[bool] = field(default_factory=lambda: [True] * 5)
    lockout: bool = False  # True means lockout is enabled; protocol uses 0=locked, 1=unlocked

    @property
    def mode_display(self):
        return CC_MODE_OPTIONS.get(self.mode, str(self.mode))

    @property
    def bands_display(self):
        return [CC_BANDS[i] for i, enabled in enumerate(self.bands) if enabled]


@dataclass
class SearchSettings:
    """Search and Close Call delay/CTCSS settings."""
    delay: int = 2
    code_search: bool = False


@dataclass
class CustomSearchRange:
    """A custom search range (1-10)."""
    index: int
    lower_freq: float  # MHz
    upper_freq: float  # MHz


class SearchManager:
    """Manage search, Close Call, and lockout settings."""

    def __init__(self, conn):
        self.conn = conn

    def _read_command(self, command, expected_prefix, attempts=2):
        """Read a scanner command with a small retry for transient NG/ERR responses."""
        self.conn.enter_program_mode()
        last_resp = None
        for _ in range(attempts):
            resp = self.conn.send_command(command)
            last_resp = resp
            if resp in ("ERR", f"{expected_prefix},NG"):
                continue
            if resp and resp.startswith(expected_prefix + ","):
                return resp
        raise ConnectionError(f"Failed to read {command}: {last_resp}")

    @staticmethod
    def _protocol_range_index(index):
        """Scanner protocol uses 0 for the 10th custom search range."""
        return 0 if int(index) == 10 else int(index)

    # --- Close Call ---

    def read_close_call(self):
        """Read Close Call settings."""
        resp = self._read_command("CLC", "CLC")
        parts = resp.split(",")
        try:
            bands_str = parts[4] if len(parts) > 4 else "11111"
            bands = [c == "1" for c in bands_str]
            while len(bands) < 5:
                bands.append(True)
            return CloseCallSettings(
                mode=int(parts[1]),
                alert_beep=parts[2] == "1",
                alert_light=parts[3] == "1",
                bands=bands,
                lockout=parts[5] == "0" if len(parts) > 5 else False,
            )
        except (IndexError, ValueError) as exc:
            raise ConnectionError(f"Invalid Close Call response: {resp}") from exc

    def write_close_call(self, cc):
        """Write Close Call settings."""
        if cc.mode not in CC_MODE_OPTIONS:
            raise ValueError(f"Invalid Close Call mode. Options: {list(CC_MODE_OPTIONS.keys())}")
        if len(cc.bands) != len(CC_BANDS):
            raise ValueError(f"Close Call bands must have {len(CC_BANDS)} entries")
        self.conn.enter_program_mode()
        bands_str = "".join("1" if b else "0" for b in cc.bands)
        cmd = (
            f"CLC,{cc.mode},{1 if cc.alert_beep else 0},"
            f"{1 if cc.alert_light else 0},{bands_str},"
            f"{0 if cc.lockout else 1}"
        )
        resp = self.conn.send_command(cmd)
        if resp != "CLC,OK":
            raise ConnectionError(f"Failed to write Close Call settings: {resp}")
        return True

    # --- Search/CC Delay ---

    def read_search_settings(self):
        """Read search/CC delay and code search settings."""
        resp = self._read_command("SCO", "SCO")
        parts = resp.split(",")
        try:
            return SearchSettings(
                delay=int(parts[1]),
                code_search=parts[2] == "1",
            )
        except (IndexError, ValueError) as exc:
            raise ConnectionError(f"Invalid search settings response: {resp}") from exc

    def write_search_settings(self, ss):
        """Write search/CC delay and code search settings."""
        if ss.delay not in DELAY_VALUES:
            raise ValueError(f"Invalid search delay. Options: {DELAY_VALUES}")
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"SCO,{ss.delay},{1 if ss.code_search else 0}")
        if resp != "SCO,OK":
            raise ConnectionError(f"Failed to write search settings: {resp}")
        return True

    # --- Service Search Groups ---

    def read_service_groups(self):
        """Read service search group enable/disable. Returns dict of {name: enabled}."""
        resp = self._read_command("SSG", "SSG")
        parts = resp.split(",")
        try:
            bits = parts[1]
            return {
                SERVICE_GROUPS[i]: bits[i] == "0"  # 0=enabled, 1=disabled
                for i in range(min(len(bits), len(SERVICE_GROUPS)))
            }
        except (IndexError, ValueError) as exc:
            raise ConnectionError(f"Invalid service group response: {resp}") from exc

    def write_service_groups(self, groups):
        """Write service search groups. groups: dict of {name: enabled}."""
        bits = []
        for name in SERVICE_GROUPS:
            enabled = groups.get(name, True)
            bits.append("0" if enabled else "1")
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"SSG,{''.join(bits)}")
        if resp != "SSG,OK":
            raise ConnectionError(f"Failed to write service groups: {resp}")
        return True

    # --- Custom Search Groups ---

    def read_custom_search_groups(self):
        """Read custom search group enable/disable. Returns dict of {1-10: enabled}."""
        resp = self._read_command("CSG", "CSG")
        parts = resp.split(",")
        try:
            bits = parts[1]
            groups = {}
            for i in range(min(len(bits), 10)):
                group_num = (i + 1) % 10 or 10
                groups[group_num] = bits[i] == "0"
            return groups
        except (IndexError, ValueError) as exc:
            raise ConnectionError(f"Invalid custom search group response: {resp}") from exc

    def write_custom_search_groups(self, groups):
        """Write custom search groups. groups: dict of {1-10: enabled}."""
        bits = []
        for i in range(10):
            group_num = (i + 1) % 10 or 10
            enabled = groups.get(group_num, True)
            bits.append("0" if enabled else "1")
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"CSG,{''.join(bits)}")
        if resp != "CSG,OK":
            raise ConnectionError(f"Failed to write custom search groups: {resp}")
        return True

    # --- Custom Search Ranges ---

    def read_custom_search_range(self, index):
        """Read a custom search range (1-10)."""
        if not 1 <= index <= 10:
            raise ValueError("Search range index must be 1-10")
        protocol_index = self._protocol_range_index(index)
        resp = self._read_command(f"CSP,{protocol_index}", "CSP")
        parts = resp.split(",")
        try:
            return CustomSearchRange(
                index=(int(parts[1]) or 10),
                lower_freq=int(parts[2]) / 10000.0,
                upper_freq=int(parts[3]) / 10000.0,
            )
        except (IndexError, ValueError) as exc:
            raise ConnectionError(f"Invalid search range response for {index}: {resp}") from exc

    def read_all_custom_search_ranges(self):
        """Read all 10 custom search ranges."""
        self.conn.enter_program_mode()
        ranges = []
        for i in range(1, 11):
            ranges.append(self.read_custom_search_range(i))
        return ranges

    def write_custom_search_range(self, sr):
        """Write a custom search range."""
        if not 1 <= sr.index <= 10:
            raise ValueError("Search range index must be 1-10")
        if sr.lower_freq <= 0 or sr.upper_freq <= 0:
            raise ValueError("Search range frequencies must be positive")
        if sr.lower_freq >= sr.upper_freq:
            raise ValueError("Search range lower frequency must be less than upper frequency")
        self.conn.enter_program_mode()
        lo = f"{int(round(sr.lower_freq * 10000)):08d}"
        hi = f"{int(round(sr.upper_freq * 10000)):08d}"
        protocol_index = self._protocol_range_index(sr.index)
        resp = self.conn.send_command(f"CSP,{protocol_index},{lo},{hi}")
        if resp != "CSP,OK":
            raise ConnectionError(f"Failed to write search range {sr.index}: {resp}")
        return True

    def set_close_call_mode(self, mode):
        cc = self.read_close_call()
        cc.mode = int(mode)
        return self.write_close_call(cc)

    def set_close_call_alert_beep(self, enabled):
        cc = self.read_close_call()
        cc.alert_beep = bool(enabled)
        return self.write_close_call(cc)

    def set_close_call_alert_light(self, enabled):
        cc = self.read_close_call()
        cc.alert_light = bool(enabled)
        return self.write_close_call(cc)

    def set_close_call_band(self, index, enabled):
        if not 0 <= index < len(CC_BANDS):
            raise ValueError(f"Close Call band index must be 0-{len(CC_BANDS) - 1}")
        cc = self.read_close_call()
        cc.bands[index] = bool(enabled)
        return self.write_close_call(cc)

    def set_close_call_lockout(self, enabled):
        cc = self.read_close_call()
        cc.lockout = bool(enabled)
        return self.write_close_call(cc)

    def set_search_delay(self, delay):
        ss = self.read_search_settings()
        ss.delay = int(delay)
        return self.write_search_settings(ss)

    def set_code_search(self, enabled):
        ss = self.read_search_settings()
        ss.code_search = bool(enabled)
        return self.write_search_settings(ss)

    # --- Global Lockout Frequencies ---

    def read_lockout_frequencies(self):
        """Read all globally locked out frequencies. Returns list of MHz floats."""
        self.conn.enter_program_mode()
        freqs = []
        max_iterations = 500  # Safety limit to prevent infinite loop
        for _ in range(max_iterations):
            resp = self.conn.send_command("GLF")
            if not resp or not resp.startswith("GLF,"):
                break
            val = resp.split(",")[1].strip()
            if val == "-1":
                break
            try:
                freq = int(val) / 10000.0
                freqs.append(freq)
            except ValueError:
                break
        return freqs

    def lock_frequency(self, freq_mhz):
        """Add a frequency to global lockout."""
        self.conn.enter_program_mode()
        scanner_freq = f"{int(round(freq_mhz * 10000)):08d}"
        resp = self.conn.send_command(f"LOF,{scanner_freq}")
        if resp != "LOF,OK":
            raise ConnectionError(f"Failed to lock frequency {freq_mhz}: {resp}")
        return True

    def unlock_frequency(self, freq_mhz):
        """Remove a frequency from global lockout."""
        self.conn.enter_program_mode()
        scanner_freq = f"{int(round(freq_mhz * 10000)):08d}"
        resp = self.conn.send_command(f"ULF,{scanner_freq}")
        if resp != "ULF,OK":
            raise ConnectionError(f"Failed to unlock frequency {freq_mhz}: {resp}")
        return True
