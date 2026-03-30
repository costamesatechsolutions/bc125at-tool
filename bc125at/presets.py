"""
BC125AT Preset Frequency Databases

Built-in frequency sets for racing, marine, weather, FRS/GMRS, MURS, railroad, etc.
One-click loading into scanner banks.

NOTE: Motorsport team frequencies change per event. The racing presets here include
race operations/safety channels (which are stable) and example team frequencies.
Always check racingelectronics.com or radioreference.com for current race-weekend lists.
"""

from .channels import Channel


def _make_channels(freq_list, start_index=1, modulation="AUTO", delay=2):
    """Create Channel objects from a list of (name, freq_mhz) tuples."""
    channels = []
    for i, (name, freq) in enumerate(freq_list):
        mod = modulation
        # Auto-detect modulation by band
        if mod == "AUTO":
            if 108.0 <= freq <= 137.0:
                mod = "AM"  # Aviation band
            elif 225.0 <= freq <= 380.0:
                mod = "AM"  # Military air
            else:
                mod = "NFM"  # Default narrowband FM for UHF/VHF
        channels.append(Channel(
            index=start_index + i,
            name=name[:16],  # Max 16 chars
            frequency=freq,
            modulation=mod,
            delay=delay,
        ))
    return channels


# =============================================================================
# MOTORSPORT PRESETS
# =============================================================================

NASCAR_OPERATIONS = [
    ("NASCAR Control", 464.0000),
    ("NASCAR Director", 464.0500),
    ("NASCAR Official", 463.6500),
    ("NASCAR Caution", 460.1125),
    ("NASCAR Timing", 461.6375),
    ("NASCAR Security", 462.6375),
    ("NASCAR Pit Road", 454.6400),
]

NASCAR_TEAMS_EXAMPLE = [
    ("Hendrick MS", 460.6625),
    ("Joe Gibbs Rcng", 466.8125),
    ("Team Penske", 462.1375),
    ("Trackhouse", 451.3750),
]

IMSA_OPERATIONS = [
    ("IMSA Control", 454.0000),
    ("IMSA Ctrl Alt", 469.5000),
    ("IMSA Officials", 451.8000),
    ("IMSA Timing", 464.5000),
    ("IMSA Safety", 453.0000),
    ("IMSA Medical", 452.9500),
    ("IMSA Pit Lane", 461.0000),
]

INDYCAR_OPERATIONS = [
    ("IndyCar Control", 464.0000),
    ("IndyCar Offcls", 463.8500),
    ("IndyCar Safety", 460.5500),
    ("IndyCar Medical", 453.3500),
    ("IndyCar Timing", 461.0250),
]

INDYCAR_TEAMS_EXAMPLE = [
    ("Penske IndyCar", 467.2125),
    ("Ganassi Racing", 460.1625),
    ("Andretti Global", 466.0875),
    ("Arrow McLaren", 462.5375),
]


# =============================================================================
# MARINE VHF
# =============================================================================

MARINE_VHF = [
    ("Distress CH16", 156.8000),
    ("Calling CH9", 156.4500),
    ("Safety CH6", 156.3000),
    ("Bridge CH13", 156.6500),
    ("USCG Liaison", 157.1000),
    ("Marine CH68", 156.4250),
    ("Marine CH69", 156.4750),
    ("Marine CH71", 156.5750),
    ("Marine CH72", 156.6250),
    ("Marine CH78A", 156.9250),
    ("Marine CH79A", 156.9750),
    ("Marine CH80A", 157.0250),
    ("Port Ops CH1A", 156.0500),
    ("Port Ops CH12", 156.6000),
    ("Port Ops CH14", 156.7000),
]


# =============================================================================
# NOAA WEATHER RADIO
# =============================================================================

WEATHER_NOAA = [
    ("NOAA WX1", 162.5500),
    ("NOAA WX2", 162.4000),
    ("NOAA WX3", 162.4750),
    ("NOAA WX4", 162.4250),
    ("NOAA WX5", 162.4500),
    ("NOAA WX6", 162.5000),
    ("NOAA WX7", 162.5250),
]


# =============================================================================
# FRS / GMRS
# =============================================================================

FRS_GMRS = [
    ("FRS/GMRS CH1", 462.5625),
    ("FRS/GMRS CH2", 462.5875),
    ("FRS/GMRS CH3", 462.6125),
    ("FRS/GMRS CH4", 462.6375),
    ("FRS/GMRS CH5", 462.6625),
    ("FRS/GMRS CH6", 462.6875),
    ("FRS/GMRS CH7", 462.7125),
    ("FRS CH8", 467.5625),
    ("FRS CH9", 467.5875),
    ("FRS CH10", 467.6125),
    ("FRS CH11", 467.6375),
    ("FRS CH12", 467.6625),
    ("FRS CH13", 467.6875),
    ("FRS CH14", 467.7125),
    ("FRS/GMRS CH15", 462.5500),
    ("FRS/GMRS CH16", 462.5750),
    ("FRS/GMRS CH17", 462.6000),
    ("FRS/GMRS CH18", 462.6250),
    ("FRS/GMRS CH19", 462.6500),
    ("FRS/GMRS CH20", 462.6750),
    ("FRS/GMRS CH21", 462.7000),
    ("FRS/GMRS CH22", 462.7250),
]


# =============================================================================
# MURS
# =============================================================================

MURS = [
    ("MURS CH1", 151.8200),
    ("MURS CH2", 151.8800),
    ("MURS CH3", 151.9400),
    ("MURS CH4", 154.5700),
    ("MURS CH5", 154.6000),
]


# =============================================================================
# RAILROAD
# =============================================================================

RAILROAD = [
    ("RR AAR1 Road", 160.2150),
    ("RR AAR2 Road", 160.8000),
    ("RR AAR3 Road", 161.1000),
    ("RR AAR4 Road", 161.3700),
    ("RR AAR5 Road", 160.2450),
    ("RR AAR6 Road", 160.2300),
    ("RR AAR7 Yard", 160.3200),
    ("RR AAR8 Yard", 160.3500),
    ("RR EOT Telmtry", 161.5500),
    ("RR AAR17 Road", 160.8350),
    ("RR AAR18 Road", 161.0100),
    ("RR AAR19 Road", 160.5650),
    ("RR AAR20 Road", 160.5950),
    ("RR Police", 161.5200),
    ("RR Police Natl", 161.5050),
    ("RR Maint of Way", 160.3050),
    ("RR Yard AAR64", 160.5500),
    ("RR AAR66 Road", 161.2500),
    ("RR Defect Det", 161.5700),
]


# =============================================================================
# CIVIL AVIATION
# =============================================================================

AVIATION = [
    ("Air Emerg 121.5", 121.5000),
    ("Air ATIS Common", 127.8500),
    ("UNICOM", 122.9500),
    ("MULTICOM", 122.9000),
    ("Air-Air", 122.7500),
    ("Flight Watch", 122.0000),
    ("Flight Svc", 122.2000),
    ("Appr Common", 119.1000),
    ("Ground Common", 121.9000),
    ("Tower Common", 118.3000),
    ("Center Common", 132.4500),
    ("CTAF Common", 123.0000),
]


# =============================================================================
# PRESET CATALOG
# =============================================================================

PRESET_CATALOG = {
    "nascar": {
        "name": "NASCAR Racing",
        "description": "NASCAR race operations, officials, and example team frequencies. "
                       "Team freqs change per event - check racingelectronics.com",
        "frequencies": NASCAR_OPERATIONS + NASCAR_TEAMS_EXAMPLE,
        "bank_suggestion": 1,
    },
    "imsa": {
        "name": "IMSA Racing",
        "description": "IMSA race control, officials, safety, timing, and pit lane. "
                       "Team radios may be digital/encrypted at some events.",
        "frequencies": IMSA_OPERATIONS,
        "bank_suggestion": 2,
    },
    "indycar": {
        "name": "IndyCar Racing",
        "description": "IndyCar race operations and example team frequencies. "
                       "Team freqs change per event - check racingelectronics.com",
        "frequencies": INDYCAR_OPERATIONS + INDYCAR_TEAMS_EXAMPLE,
        "bank_suggestion": 2,
    },
    "racing-all": {
        "name": "All Racing (NASCAR + IMSA + IndyCar)",
        "description": "Combined motorsport preset with all racing operations. "
                       "Fills ~30 channels.",
        "frequencies": NASCAR_OPERATIONS + NASCAR_TEAMS_EXAMPLE +
                       IMSA_OPERATIONS + INDYCAR_OPERATIONS + INDYCAR_TEAMS_EXAMPLE,
        "bank_suggestion": 1,
    },
    "marine": {
        "name": "Marine VHF",
        "description": "Standard marine VHF channels including distress, calling, "
                       "bridge-to-bridge, USCG, and common working channels.",
        "frequencies": MARINE_VHF,
        "bank_suggestion": 3,
    },
    "weather": {
        "name": "NOAA Weather Radio",
        "description": "All 7 NOAA weather radio frequencies. "
                       "Note: BC125AT also has a dedicated WX button.",
        "frequencies": WEATHER_NOAA,
        "bank_suggestion": 4,
    },
    "frs-gmrs": {
        "name": "FRS / GMRS",
        "description": "All 22 FRS/GMRS channels. Popular for family/group comms, "
                       "events, and general two-way radio.",
        "frequencies": FRS_GMRS,
        "bank_suggestion": 5,
    },
    "murs": {
        "name": "MURS",
        "description": "All 5 MURS channels. Used by retail stores (Walmart), "
                       "farms, and businesses. License-free.",
        "frequencies": MURS,
        "bank_suggestion": 6,
    },
    "railroad": {
        "name": "Railroad",
        "description": "Common AAR railroad channels including road, yard, "
                       "police, maintenance, and defect detectors.",
        "frequencies": RAILROAD,
        "bank_suggestion": 7,
    },
    "aviation": {
        "name": "Civil Aviation",
        "description": "Common aviation frequencies including emergency, UNICOM, "
                       "ATIS, tower, ground, approach, and center.",
        "frequencies": AVIATION,
        "bank_suggestion": 8,
    },
}


def list_presets():
    """List all available presets with descriptions."""
    return {
        key: {
            "name": p["name"],
            "description": p["description"],
            "channel_count": len(p["frequencies"]),
            "bank_suggestion": p["bank_suggestion"],
        }
        for key, p in PRESET_CATALOG.items()
    }


def get_preset_channels(preset_key, start_channel=None, bank=None):
    """Get Channel objects for a preset.

    Args:
        preset_key: Key from PRESET_CATALOG
        start_channel: Starting channel number (1-500). If None, uses bank_suggestion.
        bank: Bank number to load into (1-9, 0). Overrides start_channel.
    """
    if preset_key not in PRESET_CATALOG:
        raise ValueError(
            f"Unknown preset: {preset_key}. Available: {list(PRESET_CATALOG.keys())}"
        )

    preset = PRESET_CATALOG[preset_key]
    freqs = preset["frequencies"]

    if bank is not None:
        if bank == 0:
            start_channel = 451
        else:
            start_channel = (bank - 1) * 50 + 1
    elif start_channel is None:
        bank = preset["bank_suggestion"]
        if bank == 0:
            start_channel = 451
        else:
            start_channel = (bank - 1) * 50 + 1

    if start_channel + len(freqs) - 1 > 500:
        raise ValueError(
            f"Preset has {len(freqs)} channels but only "
            f"{500 - start_channel + 1} slots available from channel {start_channel}"
        )

    return _make_channels(freqs, start_index=start_channel)
