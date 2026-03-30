# BC125AT Scanner Tool for macOS

**The first native macOS tool for programming the Uniden BC125AT scanner.** No Windows required. No virtual machines. No Parallels. Just plug in your scanner and go.

Works on Apple Silicon (M1/M2/M3/M4) and Intel Macs.

## Why This Exists

Every existing BC125AT programming tool (Uniden's official software, FreeSCAN, BuTel ARC) is Windows-only. If you're on a Mac, you've been out of luck — until now.

This tool communicates directly with the scanner over USB, bypassing the macOS serial driver that doesn't work properly on Apple Silicon. It uses `libusb` for direct USB access, so no kernel extensions or special drivers are needed.

## Features

- **Full Channel Programming** — Read, write, and manage all 500 channels across 10 banks
- **Bank Management** — View bank enable/disable state, programmed counts, and manage banks from the web UI or CLI
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
- **Import/Export** — CSV and JSON formats, plus full backup (channels + settings + search config)
- **Web GUI** — Clean, modern browser-based interface
- **CLI** — Full command-line interface for power users and scripting
- **Live Monitor** — Watch what the scanner is receiving in real-time from the web UI or CLI

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

3. **Python packages**:
   ```bash
   pip3 install pyusb flask
   ```

### Install the tool

```bash
git clone https://github.com/costamesatechsolutions/bc125at-tool.git
cd bc125at-tool
pip3 install -e .
```

## Usage

### Web GUI (recommended)

Launch the browser-based interface:

```bash
DYLD_LIBRARY_PATH=/opt/homebrew/lib python3 -m bc125at.web.app
```

Opens automatically at `http://localhost:5125`. From here you can:
- View and edit all channels visually
- Load presets with one click
- Adjust all safe global settings with sliders and dropdowns
- Manage bank enable/disable state
- Edit Search and Close Call settings, custom search ranges, and lockout frequencies
- Monitor current scanner activity live from the dashboard
- Export/import channel programming
- Create full backups

Dashboard stats:
- `Programmed Channels` is the exact number of non-empty channels out of 500
- `Programmed Banks` is the exact number of banks containing at least one programmed channel
- `Enabled Banks` is the scanner's actual bank enable/disable state

Audio note:
- The BC125AT control connection here is USB data, not USB audio
- If you want scanner audio on your Mac, feed the scanner's headphone/line output into your Mac audio input or a USB audio interface
- The app can monitor/control scanner state while audio is routed separately

### Command Line

```bash
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

# Import from file
python3 -m bc125at import channels.csv

# Live monitor
python3 -m bc125at monitor

# View all search/Close Call settings
python3 -m bc125at search show

# View tone code reference
python3 -m bc125at tones
```

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

- The web app now computes dashboard channel and bank counts from the actual channel map rather than estimating from a single channel per bank.
- The web app and CLI both target the same safe, reversible scanner programming surface. Firmware and other unsafe operations are intentionally out of scope.
- Native macOS app planning notes live in [docs/NATIVE_MAC_APP_PLAN.md](docs/NATIVE_MAC_APP_PLAN.md).

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
