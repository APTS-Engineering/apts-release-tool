# APTS-IOT Firmware Release Tool

CLI tool for packaging APTS-IOT-V2-2 firmware (STM32H723 + ESP32) into distribution-ready ZIP archives, with built-in release tracking and GitHub publishing.

---

## Quick Install (Team Members)

### Prerequisites
- **Python 3.10+** — download from https://www.python.org/downloads/
  - During install, check **"Add Python to PATH"**

### Option A: Install from GitHub (recommended)
```bash
pip install git+https://github.com/APTS-Engineering/apts-release-tool.git#subdirectory=apts-release
```

### Option B: Install from local copy
```bash
cd apts-cli-release-package-tool/apts-release
pip install .
```

### Verify
```bash
apts-release --version
```

### Windows PATH Fix
If `apts-release` is not recognized after install, run this in **PowerShell** and restart your terminal:
```powershell
$p = python -c "import sysconfig; print(sysconfig.get_path('scripts','nt_user'))"
[Environment]::SetEnvironmentVariable("Path","$env:Path;$p","User")
```

### For GitHub Publishing (optional)
```bash
winget install GitHub.cli
gh auth login
```

---

## Quick Start

### With config file (recommended)

Place a `release-config.yaml` in your firmware project root (see [Configuration](#configuration)), then:

```bash
cd HST_APTS_PCB_FW/
apts-release
```

That's it. Everything comes from the config.

### With auto-detection

If your folders follow the `*_ESP32_FW` / `*_STM32_FW` naming convention:

```bash
cd HST_APTS_PCB_FW/
apts-release --product HSC-TUBE-CUTTER
```

### With explicit paths

```bash
apts-release --esp32 HST_ESP32_FW --stm32 HST_STM32_FW --product HSC-TUBE-CUTTER
```

### What happens

1. Scans both project build directories for `.bin` files
2. Extracts firmware versions from source code automatically
3. Prompts for release version (auto-increments) and release notes
4. Generates **FLASH** and **OTA** ZIP packages in a versioned subfolder
5. Copies HMI `.tft` file into the release folder
6. Updates the release registry, changelog, and Excel tracker

---

## Commands

### Default — Package & Release

```bash
apts-release [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--esp32 PATH` | Path to ESP32 project folder |
| `--stm32 PATH` | Path to STM32 project folder |
| `--product NAME` | Product name, e.g. `HSC-TUBE-CUTTER` |
| `--package TYPE` | `rpi`, `ota`, or `all` (default: `all`) |
| `--output PATH` | Output directory (default: `./releases/`) |
| `--version`, `-V` | Show tool version and exit |

### `history` — View Past Releases

```bash
apts-release history
apts-release history --product HSC-TUBE-CUTTER
```

### `export` — Regenerate Changelog & Excel

```bash
apts-release export
```

### `publish` — Upload to GitHub Releases

```bash
apts-release publish           # latest release
apts-release publish 1.0.2     # specific version
apts-release publish --draft   # as draft
```

---

## Output Structure

```
releases/
├── HSC-TUBE-CUTTER-release-registry.json   ← source of truth
├── HSC-TUBE-CUTTER-CHANGELOG.md            ← auto-generated
├── HSC-TUBE-CUTTER-release-tracker.xlsx    ← auto-generated
├── HSC-TUBE-CUTTER-V1.0.0/
│   ├── HSC-TUBE-CUTTER-FW-FLASH-V1.0.0.zip
│   ├── HSC-TUBE-CUTTER-FW-OTA-V1.0.0.zip
│   └── HSC-HMI-V1.6.7.tft
├── HSC-TUBE-CUTTER-V1.0.1/
│   ├── HSC-TUBE-CUTTER-FW-FLASH-V1.0.1.zip
│   ├── HSC-TUBE-CUTTER-FW-OTA-V1.0.1.zip
│   └── HSC-HMI-V1.6.7.tft
└── ...
```

---

## Package Formats

### FLASH Package (flat ZIP — for RPI programmer)

```
HSC-TUBE-CUTTER-FW-FLASH-V1.0.0.zip
├── config.json                          # Programmer config (addresses, chip type)
├── esp32_bootloader.bin                 # @ 0x1000
├── esp32_partition-table.bin            # @ 0x8000
├── esp32_ota_data_initial.bin           # @ 0xD000
├── esp32_HSC-TUBE-CUTTER-V1-0-0.bin    # @ 0x10000 (main app)
├── esp32_webpage_1.bin                  # @ 0x410000
├── esp32_cdn.bin                        # @ 0x510000
└── stm32_firmware.bin                   # @ 0x08000000
```

### OTA Package (folder-tree ZIP — for customer updates)

```
HSC-TUBE-CUTTER-FW-OTA-V1.0.0/
├── CORE-FIRMWARE/
│   └── Core-Firmware-V1.0.0.bin
├── WIFI-FIRMWARE/
│   └── WIFI-V1.0.0.bin
└── WEBPAGE/
    └── UI-V1.1.5.bin
```

> HMI `.tft` is NOT included in either ZIP — it is copied to the release folder and version tracked in the registry/tracker only.

---

## Configuration

Place `release-config.yaml` in the firmware project root:

```yaml
product:
  name: HSC-TUBE-CUTTER
  board: APTS-IOT-V2-2

projects:
  esp32_dir: HST_ESP32_FW
  stm32_dir: HST_STM32_FW

esp32:
  build_dir: build
  version:
    file: CMakeLists.txt
  webpage_version:
    file: Webserver/data/Version.txt

stm32:
  build_dir: Debug
  version:
    file: Core/Inc/display/display_task.h
    define: STM_FIRMWARE_VERSION
  hmi_dir: HMI

release:
  name: HSC Tube Cutting Machine      # human-friendly name for tracker
  released_by: Siva                    # your name (falls back to PC username)
  output_dir: ./releases

github:
  repo: APTS-Engineering/apts-hsc-tube-cutter-releases
```

### Project Directory Resolution Order

1. **CLI flags** — `--esp32 PATH` / `--stm32 PATH` (highest priority)
2. **Config file** — `projects.esp32_dir` / `projects.stm32_dir`
3. **Auto-detect** — scans cwd for `*_ESP32_FW` / `*_STM32_FW` folders

---

## Version Sources

| Component | Source | How |
|-----------|--------|-----|
| ESP32 | `CMakeLists.txt` | `set(PROJECT_VER "1.0.0")` |
| STM32 | `display_task.h` | `#define STM_FIRMWARE_VERSION "1.0.0"` |
| Web UI | `Version.txt` | Plain text |
| HMI | `.tft` filename | e.g. `HSC-HMI-V1.6.7.tft` → `1.6.7` |
| Release | Auto-increment | Patch bump from last registry entry |

If extraction fails, the tool prompts for manual entry.

---

## Recommended Folder Structure

```
008_HSC/
├── 01_Software/
│   └── HST_APTS_PCB_FW/             ← cd here and run apts-release
│       ├── HST_ESP32_FW/
│       ├── HST_STM32_FW/
│       ├── HMI/                      ← place .tft files here
│       ├── release-config.yaml
│       └── releases/
└── ...
```

---

## Typical Workflow

```
1. Build ESP32:       idf.py build
2. Build STM32:       Build in STM32CubeIDE (Debug)
3. Copy HMI .tft:     Place latest .tft in HMI/ folder
4. Package:           cd HST_APTS_PCB_FW && apts-release
5. Review:            Check releases/<PRODUCT>-V<ver>/
6. Publish:           apts-release publish
7. View history:      apts-release history
```
