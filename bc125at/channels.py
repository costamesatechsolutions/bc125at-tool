"""
BC125AT Channel Programming

Read, write, and manage all 500 channels across 10 banks.
Full CTCSS/DCS tone code support.
"""

from dataclasses import dataclass, field
from typing import Optional, List

# CTCSS tone frequencies indexed by protocol code (64-113)
CTCSS_TONES = {
    64: 67.0, 65: 69.3, 66: 71.9, 67: 74.4, 68: 77.0,
    69: 79.7, 70: 82.5, 71: 85.4, 72: 88.5, 73: 91.5,
    74: 94.8, 75: 97.4, 76: 100.0, 77: 103.5, 78: 107.2,
    79: 110.9, 80: 114.8, 81: 118.8, 82: 123.0, 83: 127.3,
    84: 131.8, 85: 136.5, 86: 141.3, 87: 146.2, 88: 151.4,
    89: 156.7, 90: 159.8, 91: 162.2, 92: 165.5, 93: 167.9,
    94: 171.3, 95: 173.8, 96: 177.3, 97: 179.9, 98: 183.5,
    99: 186.2, 100: 189.9, 101: 192.8, 102: 196.6, 103: 199.5,
    104: 203.5, 105: 206.5, 106: 210.7, 107: 218.1, 108: 225.7,
    109: 229.1, 110: 233.6, 111: 241.8, 112: 250.3, 113: 254.1,
}

# DCS codes indexed by protocol code (128-231)
DCS_CODES = {
    128: 23, 129: 25, 130: 26, 131: 31, 132: 32, 133: 36,
    134: 43, 135: 47, 136: 51, 137: 53, 138: 54, 139: 65,
    140: 71, 141: 72, 142: 73, 143: 74, 144: 114, 145: 115,
    146: 116, 147: 122, 148: 125, 149: 131, 150: 132, 151: 134,
    152: 143, 153: 145, 154: 152, 155: 155, 156: 156, 157: 162,
    158: 165, 159: 172, 160: 174, 161: 205, 162: 212, 163: 223,
    164: 225, 165: 226, 166: 243, 167: 244, 168: 245, 169: 246,
    170: 251, 171: 252, 172: 255, 173: 261, 174: 263, 175: 265,
    176: 266, 177: 271, 178: 274, 179: 306, 180: 311, 181: 315,
    182: 325, 183: 331, 184: 332, 185: 343, 186: 346, 187: 351,
    188: 356, 189: 364, 190: 365, 191: 371, 192: 411, 193: 412,
    194: 413, 195: 423, 196: 431, 197: 432, 198: 445, 199: 446,
    200: 452, 201: 454, 202: 455, 203: 462, 204: 464, 205: 465,
    206: 466, 207: 503, 208: 506, 209: 516, 210: 523, 211: 526,
    212: 532, 213: 546, 214: 565, 215: 606, 216: 612, 217: 624,
    218: 627, 219: 631, 220: 632, 221: 654, 222: 662, 223: 664,
    224: 703, 225: 712, 226: 723, 227: 731, 228: 732, 229: 734,
    230: 743, 231: 754,
}

# Reverse lookups
CTCSS_TO_CODE = {v: k for k, v in CTCSS_TONES.items()}
DCS_TO_CODE = {v: k for k, v in DCS_CODES.items()}

# Special tone codes
TONE_NONE = 0
TONE_SEARCH = 127
TONE_NO_TONE = 240

MODULATION_MODES = ["AUTO", "AM", "FM", "NFM"]
DELAY_VALUES = [-10, -5, 0, 1, 2, 3, 4, 5]

# Bank mapping: Bank 1 = CH 1-50, Bank 2 = CH 51-100, ..., Bank 0 = CH 451-500
CHANNELS_PER_BANK = 50
NUM_BANKS = 10
NUM_CHANNELS = 500

# Valid frequency ranges (in MHz)
FREQ_RANGES = [
    (25.0, 54.0),
    (108.0, 174.0),
    (225.0, 380.0),
    (400.0, 512.0),
]


def freq_to_scanner(freq_mhz):
    """Convert MHz frequency to scanner format (freq * 10000, 8 digits)."""
    return f"{int(round(freq_mhz * 10000)):08d}"


def scanner_to_freq(scanner_str):
    """Convert scanner format to MHz frequency."""
    try:
        val = int(scanner_str)
        if val == 0:
            return None
        return val / 10000.0
    except (ValueError, TypeError):
        return None


def is_valid_frequency(freq_mhz):
    """Check if a frequency is within the scanner's valid ranges."""
    return any(lo <= freq_mhz <= hi for lo, hi in FREQ_RANGES)


def tone_code_to_string(code):
    """Convert a tone code number to a human-readable string."""
    code = int(code)
    if code == TONE_NONE:
        return "None"
    if code == TONE_SEARCH:
        return "Search"
    if code == TONE_NO_TONE:
        return "No Tone"
    if code in CTCSS_TONES:
        return f"CTCSS {CTCSS_TONES[code]} Hz"
    if code in DCS_CODES:
        return f"DCS {DCS_CODES[code]:03d}"
    return f"Unknown ({code})"


def string_to_tone_code(tone_str):
    """Convert a human-readable tone string to a code number.

    Accepts: 'none', 'search', 'no tone', 'CTCSS 100.0', 'DCS 023', '100.0', '023', etc.
    """
    tone_str = tone_str.strip()
    lower = tone_str.lower()

    if lower in ("none", "off", "0"):
        return TONE_NONE
    if lower == "search":
        return TONE_SEARCH
    if lower in ("no tone", "notone"):
        return TONE_NO_TONE

    # Try CTCSS frequency
    cleaned = lower.replace("ctcss", "").replace("hz", "").strip()
    try:
        freq = float(cleaned)
        if freq in CTCSS_TO_CODE:
            return CTCSS_TO_CODE[freq]
    except ValueError:
        pass

    # Try DCS code
    cleaned = lower.replace("dcs", "").strip()
    try:
        dcs = int(cleaned)
        if dcs in DCS_TO_CODE:
            return DCS_TO_CODE[dcs]
    except ValueError:
        pass

    raise ValueError(f"Unknown tone: {tone_str}")


def _coerce_bool(value):
    """Coerce common boolean-like values safely."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on", "y")
    return False


@dataclass
class Channel:
    """Represents a single scanner channel."""
    index: int  # 1-500
    name: str = ""
    frequency: Optional[float] = None  # MHz
    modulation: str = "AUTO"
    tone_code: int = 0
    delay: int = 2
    lockout: bool = False
    priority: bool = False

    @property
    def bank(self):
        """Get bank number (1-9, 0 for 10th bank)."""
        return ((self.index - 1) // CHANNELS_PER_BANK + 1) % NUM_BANKS

    @property
    def bank_position(self):
        """Get position within the bank (1-50)."""
        return (self.index - 1) % CHANNELS_PER_BANK + 1

    @property
    def is_empty(self):
        return self.frequency is None or self.frequency == 0

    @property
    def tone_string(self):
        return tone_code_to_string(self.tone_code)

    @property
    def freq_display(self):
        if self.frequency is None:
            return "Empty"
        return f"{self.frequency:.4f} MHz"

    def to_scanner_command(self):
        """Generate CIN set command string."""
        freq_str = freq_to_scanner(self.frequency) if self.frequency else "00000000"
        return (
            f"CIN,{self.index},{self.name},{freq_str},{self.modulation},"
            f"{self.tone_code},{self.delay},{1 if self.lockout else 0},"
            f"{1 if self.priority else 0}"
        )

    @classmethod
    def from_scanner_response(cls, response):
        """Parse a CIN response into a Channel object.

        The scanner may return variable-length responses. Minimum is:
        CIN,<INDEX>,<NAME>,<FRQ> with optional MOD, CTCSS, DLY, LOUT, PRI
        """
        parts = response.split(",")
        if len(parts) < 3 or parts[0] != "CIN":
            raise ValueError(f"Invalid CIN response: {response}")

        def get(idx, default=""):
            return parts[idx].strip() if idx < len(parts) and parts[idx].strip() else default

        index = int(parts[1])
        name = get(2)
        freq = scanner_to_freq(get(3, "0"))
        mod = get(4, "AUTO")
        if mod not in MODULATION_MODES:
            mod = "AUTO"
        try:
            tone = int(get(5, "0"))
        except ValueError:
            tone = 0
        try:
            delay = int(get(6, "2"))
        except ValueError:
            delay = 2
        lockout = get(7) == "1"
        priority = get(8) == "1"

        return cls(
            index=index, name=name, frequency=freq, modulation=mod,
            tone_code=tone, delay=delay, lockout=lockout, priority=priority,
        )

    def to_dict(self):
        """Convert to dictionary for JSON/CSV export."""
        return {
            "channel": self.index,
            "name": self.name,
            "frequency": self.frequency,
            "modulation": self.modulation,
            "tone": self.tone_string,
            "tone_code": self.tone_code,
            "delay": self.delay,
            "lockout": self.lockout,
            "priority": self.priority,
            "bank": self.bank,
        }

    @classmethod
    def from_dict(cls, d):
        """Create from dictionary (JSON/CSV import)."""
        tone_code = d.get("tone_code")
        if tone_code is None and "tone" in d:
            try:
                tone_code = string_to_tone_code(str(d["tone"]))
            except ValueError:
                tone_code = 0

        freq = d.get("frequency")
        if isinstance(freq, str):
            if freq and freq.lower() not in ("none", "null", ""):
                try:
                    freq = float(freq)
                except ValueError:
                    freq = None
            else:
                freq = None

        modulation = str(d.get("modulation", "AUTO")).upper()
        if modulation not in MODULATION_MODES:
            modulation = "AUTO"

        try:
            delay = int(d.get("delay", 2))
        except (TypeError, ValueError):
            delay = 2
        if delay not in DELAY_VALUES:
            delay = 2

        return cls(
            index=int(d["channel"]),
            name=str(d.get("name", "")),
            frequency=float(freq) if freq else None,
            modulation=modulation,
            tone_code=int(tone_code or 0),
            delay=delay,
            lockout=_coerce_bool(d.get("lockout", False)),
            priority=_coerce_bool(d.get("priority", False)),
        )


class ChannelManager:
    """Manages reading/writing channels on the scanner."""

    def __init__(self, conn):
        self.conn = conn

    def read_channel(self, index):
        """Read a single channel from the scanner."""
        if not 1 <= index <= NUM_CHANNELS:
            raise ValueError(f"Channel index must be 1-{NUM_CHANNELS}")
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"CIN,{index}")
        if resp and resp.startswith("CIN,"):
            return Channel.from_scanner_response(resp)
        raise ConnectionError(f"Failed to read channel {index}: {resp}")

    def write_channel(self, channel):
        """Write a single channel to the scanner."""
        if not 1 <= channel.index <= NUM_CHANNELS:
            raise ValueError(f"Channel index must be 1-{NUM_CHANNELS}, got {channel.index}")
        if channel.frequency and not is_valid_frequency(channel.frequency):
            raise ValueError(
                f"Frequency {channel.frequency} MHz is outside valid ranges"
            )
        if channel.tone_code not in (TONE_NONE, TONE_SEARCH, TONE_NO_TONE) and \
           channel.tone_code not in CTCSS_TONES and channel.tone_code not in DCS_CODES:
            raise ValueError(f"Invalid tone code: {channel.tone_code}")
        if channel.delay not in DELAY_VALUES:
            raise ValueError(f"Invalid delay: {channel.delay}. Must be one of {DELAY_VALUES}")
        if channel.modulation not in MODULATION_MODES:
            raise ValueError(f"Invalid modulation: {channel.modulation}. Must be one of {MODULATION_MODES}")
        if len(channel.name) > 16:
            channel.name = channel.name[:16]
        self.conn.enter_program_mode()
        cmd = channel.to_scanner_command()
        resp = self.conn.send_command(cmd)
        if resp != "CIN,OK":
            raise ConnectionError(f"Failed to write channel {channel.index}: {resp}")
        return True

    def delete_channel(self, index):
        """Delete (clear) a channel."""
        if not 1 <= index <= NUM_CHANNELS:
            raise ValueError(f"Channel index must be 1-{NUM_CHANNELS}")
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"DCH,{index}")
        if resp != "DCH,OK":
            raise ConnectionError(f"Failed to delete channel {index}: {resp}")
        return True

    def clear_bank(self, bank_num, callback=None):
        """Delete all 50 channels in a bank (0-9)."""
        if bank_num not in range(NUM_BANKS):
            raise ValueError("Bank must be 0-9")
        start = 451 if bank_num == 0 else (bank_num - 1) * CHANNELS_PER_BANK + 1
        end = start + CHANNELS_PER_BANK
        self.conn.enter_program_mode()
        for i, channel_index in enumerate(range(start, end), 1):
            resp = self.conn.send_command(f"DCH,{channel_index}")
            if resp != "DCH,OK":
                raise ConnectionError(f"Failed to clear channel {channel_index}: {resp}")
            if callback:
                callback(i, channel_index)
        return True

    def read_all_channels(self, callback=None):
        """Read all 500 channels. Optional callback(index, channel) for progress."""
        self.conn.enter_program_mode()
        channels = []
        for i in range(1, NUM_CHANNELS + 1):
            resp = self.conn.send_command(f"CIN,{i}")
            if resp and resp.startswith("CIN,"):
                ch = Channel.from_scanner_response(resp)
                channels.append(ch)
                if callback:
                    callback(i, ch)
            else:
                raise ConnectionError(f"Failed to read channel {i}: {resp}")
        return channels

    def get_channel_summary(self):
        """Return exact programmed channel and per-bank counts."""
        channels = self.read_all_channels()
        programmed = [ch for ch in channels if not ch.is_empty]
        bank_counts = {bank: 0 for bank in range(NUM_BANKS)}
        for ch in programmed:
            bank_counts[ch.bank] += 1
        return {
            "programmed_channels": len(programmed),
            "programmed_banks": sum(1 for count in bank_counts.values() if count > 0),
            "bank_counts": bank_counts,
        }

    def write_channels(self, channels, callback=None):
        """Write multiple channels. Optional callback(count, channel) for progress."""
        self.conn.enter_program_mode()
        for i, ch in enumerate(channels, 1):
            if ch.frequency and not is_valid_frequency(ch.frequency):
                raise ValueError(
                    f"Channel {ch.index}: frequency {ch.frequency} MHz is outside valid ranges"
                )
            cmd = ch.to_scanner_command()
            resp = self.conn.send_command(cmd)
            if resp != "CIN,OK":
                raise ConnectionError(f"Failed to write channel {ch.index}: {resp}")
            if callback:
                callback(i, ch)
        return True

    def read_bank(self, bank_num):
        """Read all channels in a bank (0-9)."""
        if bank_num == 0:
            start = 451
        else:
            start = (bank_num - 1) * CHANNELS_PER_BANK + 1
        end = start + CHANNELS_PER_BANK
        self.conn.enter_program_mode()
        channels = []
        for i in range(start, end):
            resp = self.conn.send_command(f"CIN,{i}")
            if resp and resp.startswith("CIN,"):
                channels.append(Channel.from_scanner_response(resp))
        return channels

    def get_bank_status(self):
        """Get which banks are enabled/disabled."""
        self.conn.enter_program_mode()
        resp = self.conn.send_command("SCG")
        if resp and resp.startswith("SCG,"):
            bits = resp.split(",")[1]
            # 0 = enabled, 1 = disabled (inverted from what you'd expect)
            status = {}
            for i, bit in enumerate(bits):
                bank = (i + 1) % NUM_BANKS  # positions map to banks 1-9, 0
                status[bank] = bit == "0"
            return status
        raise ConnectionError(f"Failed to read bank status: {resp}")

    def set_bank_status(self, bank_status):
        """Set bank enable/disable. bank_status: dict of {bank_num: enabled_bool}."""
        bits = []
        for i in range(NUM_BANKS):
            bank = (i + 1) % NUM_BANKS
            enabled = bank_status.get(bank, True)
            bits.append("0" if enabled else "1")
        self.conn.enter_program_mode()
        resp = self.conn.send_command(f"SCG,{''.join(bits)}")
        if resp != "SCG,OK":
            raise ConnectionError(f"Failed to set bank status: {resp}")
        return True
