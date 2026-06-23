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
# NORDBAYERN / NORTHERN BAVARIA (Germany)
# Sources: DFS AIP, OurAirports, DARC, BNetzA
# NOTE: Not for navigation. Verify against current DFS AIP before flight ops.
# =============================================================================

NORDBAYERN_AVIATION_NUERNBERG = [
    ("NUE Tower",     118.3050),
    ("NUE Director",  119.4750),
    ("NUE Ground",    121.7600),
    ("NUE ATIS",      123.0800),
    ("MUC Radar NUE", 129.5250),
    ("Langen Info",   125.8000),
    ("Langen Info 2", 120.6500),
    ("Berlin VOLMET", 128.4050),
    ("Emergency",     121.5000),
    ("Air-Air",       123.4500),
]

NORDBAYERN_AVIATION_OBERFRANKEN = [
    ("Hof Tower",      124.3550),
    ("MUC Radar Hof",  118.9750),
    ("Langen Hof",     125.8000),
    ("Bayreuth Info",  127.5300),
    ("Bayreuth ATIS",  119.5600),
    ("Bayreuth Radar", 118.9750),
    ("Bamberg Info",   123.4400),
    ("Bamberg ATIS",   124.1300),
    ("Bamberg Langen", 125.8000),
    ("Reserve OFR",    120.6500),
]

NORDBAYERN_AVIATION_WESTFRANKEN = [
    ("Wuerzburg Radio", 132.9900),
    ("Schenkenturm",    122.1750),
    ("Langen WUE",      119.1500),
    ("SchwHall Info",   129.2300),
    ("SchwHall ATIS",   133.8800),
    ("Langen SH",       128.9500),
    ("Langen Radar SH", 125.0500),
    ("Reserve West",    123.4500),
    ("Emergency",       121.5000),
    ("VOLMET",          128.4050),
]

NORDBAYERN_AVIATION_GENERAL = [
    ("Emergency",       121.5000),
    ("Search&Rescue",   123.1000),
    ("Air-Air",         123.4500),
    ("Berlin VOLMET",   128.4050),
    ("Shannon VOLMET",  127.6000),
    ("Shannon VLMT2",   135.5000),
    ("MUC Radar",       125.0500),
    ("MUC Radar NUE",   129.5250),
    ("Langen Info",     125.8000),
    ("Langen Info 2",   120.6500),
    ("Langen Info 3",   119.1500),
    ("Prag Info",       126.1000),
    ("Praha Radar",     118.3750),
    ("Wien Info",       124.4000),
    ("Guard Backup",    121.5000),
    ("Air-Air Glider",  123.5000),
    ("Glider DE",       122.1800),
    ("Ballonfunk",      122.6500),
    ("Reserve L-L",     122.7500),
    ("Reserve L-L 2",   123.4750),
]

NORDBAYERN_AVIATION_EXTENDED = [
    ("MUC Radar Sekt",  118.5330),
    ("MUC Radar HOF",   118.9750),
    ("Air-Air Sonder",  122.6250),
    ("Hof Tower",       124.3580),
    ("Bayreuth Info",   127.5330),
    ("Bayreuth ATIS",   119.5670),
    ("NUE Tower",       118.3080),
    ("NUE ATIS",        123.0830),
    ("MUC Radar NUE",   129.5250),
    ("MUC Radar High",  135.1330),
    ("ACARS",           131.5500),
    ("ACARS VDL",       136.9750),
]

NORDBAYERN_AMATEUR_2M = [
    ("2m Relais 1",    145.6000),
    ("2m Relais 2",    145.6250),
    ("2m Relais 3",    145.6500),
    ("2m Relais 4",    145.6750),
    ("2m Relais 5",    145.7000),
    ("2m Relais 6",    145.7250),
    ("2m Relais 7",    145.7500),
    ("2m Relais 8",    145.7750),
    ("APRS",           144.8000),
    ("Anruffrequenz",  145.5000),
]

NORDBAYERN_AMATEUR_70CM = [
    ("70cm Relais 1",  438.6500),
    ("70cm Relais 2",  438.6750),
    ("70cm Relais 3",  438.7000),
    ("70cm Relais 4",  438.7250),
    ("70cm Relais 5",  438.7500),
    ("70cm Relais 6",  438.7750),
    ("70cm Relais 7",  439.0000),
    ("Grosser Arber",  439.2000),
    ("Arber DMR",      439.2250),
    ("Reserve 70cm",   439.2500),
]

NORDBAYERN_ISS_SAT = [
    ("ISS Voice",      145.8000),
    ("ISS APRS",       145.8250),
    ("Amateur Sat 1",  145.9350),
    ("Amateur Sat 2",  437.5500),
    ("ISS Repeater",   437.8000),
    ("Amateur Sat 3",  435.2500),
    ("Amateur Sat 4",  436.5000),
    ("Amateur Sat 5",  437.0250),
    ("Amateur Sat 6",  437.1000),
    ("Reserve Sat",    437.3000),
]

NORDBAYERN_FREENET = [
    ("Freenet 1",      149.0250),
    ("Freenet 2",      149.0375),
    ("Freenet 3",      149.0500),
    ("Freenet 4",      149.0875),
    ("Freenet 5",      149.1000),
    ("Freenet 6",      149.1125),
]

NORDBAYERN_PMR446 = [
    ("PMR 1",  446.00625),
    ("PMR 2",  446.01875),
    ("PMR 3",  446.03125),
    ("PMR 4",  446.04375),
    ("PMR 5",  446.05625),
    ("PMR 6",  446.06875),
    ("PMR 7",  446.08125),
    ("PMR 8",  446.09375),
    ("PMR 9",  446.10625),
    ("PMR 10", 446.11875),
    ("PMR 11", 446.13125),
    ("PMR 12", 446.14375),
    ("PMR 13", 446.15625),
    ("PMR 14", 446.16875),
    ("PMR 15", 446.18125),
    ("PMR 16", 446.19375),
]

NORDBAYERN_DX_SPECIAL = [
    ("Luftnotruf",      121.5000),
    ("Air-Air",         123.4500),
    ("Berlin VOLMET",   128.4050),
    ("Shannon VOLMET",  127.6000),
    ("Shannon VLMT2",   135.5000),
    ("Segelflug 1",     122.1800),
    ("Segelflug 2",     123.5000),
    ("Wettersonde 1",   400.5000),
    ("Wettersonde 2",   403.0000),
    ("Wettersonde 3",   405.5000),
]

NORDBAYERN_WETTERSONDEN = [
    ("Radiosonde 401",  401.0000),
    ("Radiosonde 402",  402.0000),
    ("Radiosonde 403",  403.0000),
    ("Radiosonde 404",  404.0000),
    ("Radiosonde 405",  405.0000),
    ("Radiosonde 406",  406.0000),
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
        "group": "Standard",
    },
    "imsa": {
        "name": "IMSA Racing",
        "description": "IMSA race control, officials, safety, timing, and pit lane. "
                       "Team radios may be digital/encrypted at some events.",
        "frequencies": IMSA_OPERATIONS,
        "bank_suggestion": 2,
        "group": "Standard",
    },
    "indycar": {
        "name": "IndyCar Racing",
        "description": "IndyCar race operations and example team frequencies. "
                       "Team freqs change per event - check racingelectronics.com",
        "frequencies": INDYCAR_OPERATIONS + INDYCAR_TEAMS_EXAMPLE,
        "bank_suggestion": 2,
        "group": "Standard",
    },
    "racing-all": {
        "name": "All Racing (NASCAR + IMSA + IndyCar)",
        "description": "Combined motorsport preset with all racing operations. "
                       "Fills ~30 channels.",
        "frequencies": NASCAR_OPERATIONS + NASCAR_TEAMS_EXAMPLE +
                       IMSA_OPERATIONS + INDYCAR_OPERATIONS + INDYCAR_TEAMS_EXAMPLE,
        "bank_suggestion": 1,
        "group": "Standard",
    },
    "marine": {
        "name": "Marine VHF",
        "description": "Standard marine VHF channels including distress, calling, "
                       "bridge-to-bridge, USCG, and common working channels.",
        "frequencies": MARINE_VHF,
        "bank_suggestion": 3,
        "group": "Standard",
    },
    "weather": {
        "name": "NOAA Weather Radio",
        "description": "All 7 NOAA weather radio frequencies. "
                       "Note: BC125AT also has a dedicated WX button.",
        "frequencies": WEATHER_NOAA,
        "bank_suggestion": 4,
        "group": "Standard",
    },
    "frs-gmrs": {
        "name": "FRS / GMRS",
        "description": "All 22 FRS/GMRS channels. Popular for family/group comms, "
                       "events, and general two-way radio.",
        "frequencies": FRS_GMRS,
        "bank_suggestion": 5,
        "group": "Standard",
    },
    "murs": {
        "name": "MURS",
        "description": "All 5 MURS channels. Used by retail stores (Walmart), "
                       "farms, and businesses. License-free.",
        "frequencies": MURS,
        "bank_suggestion": 6,
        "group": "Standard",
    },
    "railroad": {
        "name": "Railroad",
        "description": "Common AAR railroad channels including road, yard, "
                       "police, maintenance, and defect detectors.",
        "frequencies": RAILROAD,
        "bank_suggestion": 7,
        "group": "Standard",
    },
    "aviation": {
        "name": "Civil Aviation",
        "description": "Common aviation frequencies including emergency, UNICOM, "
                       "ATIS, tower, ground, approach, and center.",
        "frequencies": AVIATION,
        "bank_suggestion": 8,
        "group": "Standard",
    },
    # -------------------------------------------------------------------------
    # NORDBAYERN / NORTHERN BAVARIA
    # -------------------------------------------------------------------------
    "nordbayern-nuernberg": {
        "name": "Nürnberg (EDDN)",
        "description": "Tower, Director, Ground, ATIS, München Radar, Langen Info, "
                       "VOLMET, Emergency. NOT for navigation – verify against DFS AIP.",
        "frequencies": NORDBAYERN_AVIATION_NUERNBERG,
        "bank_suggestion": 1,
        "group": "Nordbayern",
    },
    "nordbayern-oberfranken": {
        "name": "Oberfranken – Hof / Bayreuth / Bamberg",
        "description": "Hof-Plauen (EDQM), Bayreuth (EDQD), Bamberg (EDQA): "
                       "Tower, Info, ATIS, München Radar, Langen Info. "
                       "NOT for navigation – verify against DFS AIP.",
        "frequencies": NORDBAYERN_AVIATION_OBERFRANKEN,
        "bank_suggestion": 2,
        "group": "Nordbayern",
    },
    "nordbayern-westfranken": {
        "name": "West-/Südfranken – Würzburg / Schwäbisch Hall",
        "description": "Würzburg (EDFW), Schwäbisch Hall (EDTY): "
                       "Info, ATIS, Langen Info, Radar, Emergency, VOLMET. "
                       "NOT for navigation – verify against DFS AIP.",
        "frequencies": NORDBAYERN_AVIATION_WESTFRANKEN,
        "bank_suggestion": 3,
        "group": "Nordbayern",
    },
    "nordbayern-general": {
        "name": "Allgemein / Not / Wetter",
        "description": "Emergency 121.5, SAR, Air-Air, VOLMET Berlin/Shannon, "
                       "München Radar, Langen Info, Praha/Wien DX, Segelflug, Ballon.",
        "frequencies": NORDBAYERN_AVIATION_GENERAL,
        "bank_suggestion": 4,
        "group": "Nordbayern",
    },
    "nordbayern-aviation-extended": {
        "name": "Erweiterter Flugfunk (8.33 kHz / ACARS)",
        "description": "Nürnberg, Hof, Bayreuth mit 8.33-kHz-Raster, High-Sector Radar, "
                       "ACARS 131.550, VDL 136.975. NOT for navigation – verify against DFS AIP.",
        "frequencies": NORDBAYERN_AVIATION_EXTENDED,
        "bank_suggestion": 3,
        "group": "Nordbayern",
    },
    "nordbayern-amateur-2m": {
        "name": "Amateurfunk 2m",
        "description": "Relais 145.600–145.775, APRS 144.800, Anruffrequenz 145.500. NFM.",
        "frequencies": NORDBAYERN_AMATEUR_2M,
        "bank_suggestion": 5,
        "group": "Nordbayern",
    },
    "nordbayern-amateur-70cm": {
        "name": "Amateurfunk 70cm",
        "description": "Relais 438.650–439.000, Großer Arber FM 439.200, Arber DMR 439.225. "
                       "NFM. DMR-Kanäle zeigen Datenburst, kein Sprachempfang.",
        "frequencies": NORDBAYERN_AMATEUR_70CM,
        "bank_suggestion": 6,
        "group": "Nordbayern",
    },
    "nordbayern-iss-sat": {
        "name": "ISS & Amateursatelliten",
        "description": "ISS Voice 145.800, ISS APRS 145.825, Satelliten-Downlinks "
                       "145.935 / 435–437 MHz. Bester Empfang während ISS-Überflügen.",
        "frequencies": NORDBAYERN_ISS_SAT,
        "bank_suggestion": 7,
        "group": "Nordbayern",
    },
    "nordbayern-freenet": {
        "name": "Freenet (149 MHz)",
        "description": "Alle 6 Freenet-Kanäle 149.025–149.113 MHz. "
                       "Lizenzfrei, NFM, verbreitet in Deutschland.",
        "frequencies": NORDBAYERN_FREENET,
        "bank_suggestion": 8,
        "group": "Nordbayern",
    },
    "nordbayern-pmr446": {
        "name": "PMR446",
        "description": "Alle 16 analogen PMR446-Kanäle 446.006–446.194 MHz. "
                       "Lizenzfreie Handfunkgeräte, NFM.",
        "frequencies": NORDBAYERN_PMR446,
        "bank_suggestion": 9,
        "group": "Nordbayern",
    },
    "nordbayern-dx": {
        "name": "DX / Spezial / Wettersonden",
        "description": "Notfrequenzen, VOLMET, Segelflug (AM), "
                       "Wettersonden 400–406 MHz (FM).",
        "frequencies": NORDBAYERN_DX_SPECIAL,
        "bank_suggestion": 1,
        "group": "Nordbayern",
    },
    "nordbayern-wettersonden": {
        "name": "Wettersonden / Radiosondes",
        "description": "Radiosonden-Frequenzen 401–406 MHz (FM). "
                       "Täglich von DWD-Stationen gestartet, hörbar beim Aufstieg.",
        "frequencies": NORDBAYERN_WETTERSONDEN,
        "bank_suggestion": 1,
        "group": "Nordbayern",
    },
    "nordbayern-all": {
        "name": "Nordbayern – Komplett",
        "description": "Komplettes Setup: Nürnberg + Oberfranken + Westfranken Flugfunk, "
                       "Not/Wetter, 2m/70cm Amateur, ISS, Freenet, PMR446, DX. "
                       "130 Kanäle ab Kanal 1 (Bank 1–3). NOT for navigation – verify against DFS AIP.",
        "frequencies": (
            NORDBAYERN_AVIATION_NUERNBERG +
            NORDBAYERN_AVIATION_OBERFRANKEN +
            NORDBAYERN_AVIATION_WESTFRANKEN +
            NORDBAYERN_AVIATION_GENERAL +
            NORDBAYERN_AVIATION_EXTENDED +
            NORDBAYERN_AMATEUR_2M +
            NORDBAYERN_AMATEUR_70CM +
            NORDBAYERN_ISS_SAT +
            NORDBAYERN_FREENET +
            NORDBAYERN_PMR446 +
            NORDBAYERN_DX_SPECIAL +
            NORDBAYERN_WETTERSONDEN
        ),
        "bank_suggestion": 1,
        "group": "Nordbayern",
    },
}


def list_presets():
    """List all available presets with descriptions, grouped by category."""
    return {
        key: {
            "name": p["name"],
            "description": p["description"],
            "channel_count": len(p["frequencies"]),
            "bank_suggestion": p["bank_suggestion"],
            "group": p.get("group", "Standard"),
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
