# BC125AT Scanner Tool for macOS

**A macOS-compatible tool for programming the Uniden BC125AT scanner without Windows.** No virtual machines. No Parallels. Just plug in your scanner and go.

Built for Apple Silicon and Intel Macs.

## Why This Exists

Most well-known BC125AT programming tools (including Uniden's official software, FreeSCAN, and BuTel ARC) are Windows-only. This project focuses on making BC125AT programming work directly on macOS.

This tool communicates directly with the scanner over USB, bypassing the macOS serial driver that doesn't work properly on Apple Silicon. It uses `libusb` for direct USB access, so no kernel extensions or special drivers are needed.

## Features

- **Full Channel Programming** — Read, write, and manage all 500 channels across 10 banks
- **Bank Management** — View bank enable/disable state, clear banks, and manage banks from the web UI or CLI
- **Built-in Frequency Presets** — One-click loading for:
  - IMSA Racing (race control, safety, timing, pit lane)
  - NASCAR (race ops, officials, example team frequencies)
  - IndyCar (race ops, example teams)
  - Marine VHF (distress, USCG, working channels)
  - NOAA Weather Radio (all 7 frequencies)
  - Civil Aviation (emergency, UNICOM, tower, approach)
  - FRS/GMRS (all 22 channels)
  - MURS (all 5 channels)
  - Railroad (AAR road, yard, police, defect detectors)
- **Safe Global Settings Editing** — Volume, squelch, contrast, backlight, priority mode, weather alert, key beep, key lock, band plan, and battery charge timer
- **Search & Close Call** — Custom search ranges, service search groups, Close Call configuration, global frequency lockout
- **CTCSS/DCS Tones** — Full support for all 50 CTCSS tones and 104 DCS codes
- **Import/Export** — CSV, JSON, BC125AT season files, and full backup restore/export
- **Web GUI** — Clean, modern browser-based interface
- **CLI** — Full command-line interface for power users and scripting
- **Programming Session Workflow** — Explicitly start/release scanner control so the app does not interfere with normal scanning by default

## Safety

This tool **cannot brick your scanner**. There is no firmware update functionality, bootloader access, or low-level flash writing. It only uses documented channel, bank, search, and settings commands that are reversible from the app, CLI, or the scanner itself.

Safe editable settings currently exposed are:
- Volume
- Squelch
- Contrast
- Backlight
- Priority mode
- Weather alert
- Key beep
- Key lock
- Band plan
- Battery charge timer

Worst case scenario: you write a bad channel or pick a setting you don't like, then change it back or factory-reset from the scanner's own buttons.

## Disclaimer

This project is provided **as-is**, without warranties of any kind. You are responsible for reviewing changes before writing them to your scanner and for using the software in a lawful and safe manner. Pine Heights Ventures LLC, and Costa Mesa Tech Solutions as a brand of Pine Heights Ventures LLC, are not liable for data loss, missed communications, configuration mistakes, hardware issues, regulatory misuse, or any indirect or consequential damages arising from use of this project.

## Installation

### Prerequisites

1. **Homebrew** (if you don't have it):
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **libusb**:
   ```bash
   brew install libusb
   ```

3. **Python**:
    ```bash
   brew install python
   ```

### Install the tool

```bash
git clone https://github.com/costamesatechsolutions/bc125at-tool.git
cd bc125at-tool
./setup.sh
```

If you prefer the manual path, this does the same thing:

```bash
/opt/homebrew/bin/python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[gui]"
```

## Usage

### Web GUI (recommended)

Start a programming session only when you want the app to take control of the scanner for editing, import/export, or settings work. When the session is released, the scanner is left free to scan normally.

Launch the browser-based interface from the repo root:

```bash
cd bc125at-tool
./run.sh
```

Manual launch is still available if you want it:

```bash
source .venv/bin/activate
DYLD_LIBRARY_PATH=/opt/homebrew/lib python -m bc125at.web.app
```

Opens automatically at `http://localhost:5125`. From here you can:
- View and edit all channels visually
- Load presets with one click
- Adjust all safe global settings with sliders and dropdowns
- Manage bank enable/disable state
- Clear a bank before repurposing it
- Edit Search and Close Call settings, custom search ranges, and lockout frequencies
- Take a manual status snapshot from the dashboard without background polling
- Export/import channel programming
- Create and restore full backups including channels, settings, search configuration, and bank enable state
- Import or export BC125AT season files (`.bc125at_ss`) for compatibility with Windows users

Audio note:
- The BC125AT control connection here is USB data, not USB audio
- If you want scanner audio on your Mac, feed the scanner's headphone/line output into your Mac audio input or a USB audio interface
- Use the app as a programmer/editor; it does not try to be a full live remote-control front panel

Control note:
- Current computer control covers safe programming, banks, settings, search/Close Call, backups, and manual status snapshots
- Direct front-panel style remote navigation such as scan/hold/channel-jump/key emulation is not currently implemented in this project
- While a programming session is active, the scanner may briefly show `REMOTE LOCK` or pause normal scanning; that is expected behavior for BC125AT computer control

### Command Line

```bash
# Activate the local virtual environment
source .venv/bin/activate

# Set the library path (add to your .zshrc for convenience)
export DYLD_LIBRARY_PATH=/opt/homebrew/lib

# Scanner info and status
python3 -m bc125at info

# Read a specific channel
python3 -m bc125at channels 51

# Read all channels in a bank
python3 -m bc125at channels --bank 2

# Program a channel
python3 -m bc125at set 1 155.0000 --name "My Channel" --modulation NFM

# List available presets
python3 -m bc125at presets list

# Load IMSA racing frequencies into bank 2
python3 -m bc125at presets load imsa --bank 2

# Load all racing presets into bank 1
python3 -m bc125at presets load racing-all --bank 1

# View/change settings
python3 -m bc125at settings
python3 -m bc125at settings volume 10
python3 -m bc125at settings backlight KY
python3 -m bc125at settings keybeep 99
python3 -m bc125at settings keylock 1
python3 -m bc125at settings bandplan 1
python3 -m bc125at settings battery 13

# Show/modify bank enable state
python3 -m bc125at banks
python3 -m bc125at banks --disable 3 4
python3 -m bc125at banks --enable 3 4

# Export channels to CSV
python3 -m bc125at export --format csv

# Full backup (channels + settings + search config)
python3 -m bc125at export --full-backup

# Export Windows-compatible BC125AT season file
python3 -m bc125at export season.bc125at_ss --full-backup

# Import from file
python3 -m bc125at import channels.csv
python3 -m bc125at import season.bc125at_ss
python3 -m bc125at import bc125at_backup.json

# Live monitor
python3 -m bc125at monitor

# View all search/Close Call settings
python3 -m bc125at search show

# View tone code reference
python3 -m bc125at tones
```

## Import Format

There are three useful formats in this project:

- **Full Backup JSON** — This app's richest backup format. Includes channels, settings, search configuration, and bank enable state.
- **BC125AT Season File (`.bc125at_ss`)** — Compatibility format used by the Windows BC125AT software.
- **CSV / pasted text** — The most portable interchange format for shared channel lists and race sheets.

The safest workflow is:

1. Export a CSV or JSON sample from the app.
2. Match that structure when creating or editing files.
3. Import the edited file back into the app or CLI.

There is no universal BC125AT JSON standard shared across Windows apps. CSV is the closest thing to a common interchange format, so treat CSV and pasted text as the most portable options. Full Backup JSON is this app's own round-trip backup format. `.bc125at_ss` exists for compatibility with the official Windows workflow.

The importer also recognizes race-style CSV layouts where one row contains a car, driver, and multiple frequency columns such as `Primary`, `Secondary`, and `Other`. Those rows are automatically expanded into individual scanner channels during import.

This project accepts both its native field names and some common aliases often produced by AI or radio users, including:

- `channel` or `channel_index`
- `name` or `alpha_tag`
- `frequency` or `freq`
- `modulation`, `mode`, or `mod`
- `tone` or `ctcss_dcs`

Accepted JSON shapes:

```json
[
  {
    "channel": 101,
    "name": "Anaheim ARA",
    "frequency": 146.79,
    "modulation": "NFM",
    "tone": "Search",
    "delay": 2,
    "lockout": false,
    "priority": false
  }
]
```

```json
{
  "metadata": {
    "bank_target": 3
  },
  "channels": [
    {
      "channel_index": 101,
      "alpha_tag": "Anaheim ARA",
      "frequency": 146.79,
      "modulation": "NFM",
      "ctcss_dcs": "Search"
    }
  ]
}
```

If a JSON file omits channel numbers entirely, you can still import it by using `metadata.bank_target` and listing channels in the order you want them written. In the web app, both file imports and pasted text support previewing the destination bank before anything is written.

## Racing Frequencies Note

Motorsport team frequencies change per event. The presets include race operations channels (race control, safety, timing) which are generally stable, plus example team frequencies.

For current race-weekend team frequencies, check:
- [Racing Electronics](https://www.racingelectronics.com) (official NASCAR scanner partner)
- [RadioReference.com](https://www.radioreference.com) (user-submitted databases by track)

The BC125AT is an analog-only scanner. F1 team radio is fully encrypted digital and cannot be monitored.

## Supported Hardware

- **Scanner**: Uniden BC125AT (USB Vendor ID `1965`, Product ID `0017`)
- **Also works with**: UBC125XLT, UBC126AT (international variants, untested)
- **Mac**: Any Mac running macOS 11+ with USB (Apple Silicon or Intel)
- **Connection**: USB cable to scanner, directly or via USB-C hub

## Technical Details

The BC125AT presents as a USB CDC ACM (Communications Device Class, Abstract Control Model) device. On macOS, especially Apple Silicon, the built-in `AppleUSBCDCACM` kernel driver fails to bind properly, so no `/dev/tty.*` serial port is created.

This tool bypasses the kernel driver entirely by using `libusb` for direct USB bulk transfers to the scanner's endpoints. All communication uses the Uniden BC125AT serial protocol — ASCII commands terminated by carriage return (`\r`).

## Notes

- The web app no longer polls the scanner continuously in the background. This is intentional, because aggressive reads can interfere with normal scanning on the BC125AT.
- The web app and CLI both target the same safe, reversible scanner programming surface. Firmware and other unsafe operations are intentionally out of scope.

## Contributing

Contributions are welcome! Some areas that would be great to improve:

- Additional frequency presets for specific regions/services
- Testing on UBC125XLT/UBC126AT international variants
- UI improvements and new features
- Bug reports from different Mac/macOS configurations

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See [LICENSE](LICENSE) for details.

A polished native macOS GUI application is available separately on the Mac App Store from [Pine Heights Ventures LLC](https://costamesatechsolutions.com).

## Credits

Built by [Costa Mesa Tech Solutions](https://costamesatechsolutions.com), a brand of Pine Heights Ventures LLC.

Protocol reference: Uniden BC125AT PC Protocol V1.01
