# APTS-IOT Firmware Packaging & Release Tool — Requirements & Implementation Plan

> **Document Version:** 2.0
> **Date:** 2026-02-28
> **Author:** APTS Engineering
> **Purpose:** Complete specification for Claude Code to build the `apts-release` CLI tool
> **Target Board:** APTS-IOT-V2-2 (Dual-controller: STM32H723VETx + ESP32)

---

## 1. Project Overview

### 1.1 What This Tool Does

`apts-release` is a Python CLI tool that packages firmware build artifacts from the APTS-IOT-V2-2 dual-controller board into distribution-ready ZIP archives. It produces two package types and maintains a complete release history:

1. **RPI Flash Programmer Package** — For manufacturing. Contains all bin files (ESP32 + STM32) plus a JSON config file. Used with a Raspberry Pi-based flash programmer that programs boards via cable.
2. **OTA Package** — For customers. Contains only the update-relevant firmware binaries organized in a specific folder tree. Used with the ESP32's over-the-air update feature.
3. **Release Registry** — A JSON file that stores the complete history of every release (source of truth).
4. **Release Tracker Excel** — An `.xlsx` spreadsheet generated from the registry for sharing with manufacturing, management, and customers.
5. **Changelog** — A `CHANGELOG.md` file generated from the registry for developer-facing release history.

### 1.2 How It Will Be Used

The developer runs `apts-release` from a terminal (anywhere). The tool interactively asks for the ESP32 project folder and STM32 project folder (or accepts them as arguments). It then:

- Locates all required `.bin` files from both build directories
- Extracts firmware version strings from source code
- Locates the HMI `.tft` file from a designated folder inside the STM32 project
- Prompts for a one-line release note describing what changed
- Generates both ZIP packages with correct naming, structure, and config
- Records the release in the JSON registry (source of truth)
- Regenerates `CHANGELOG.md` from the registry
- Updates the `release-tracker.xlsx` Excel file from the registry
- Outputs everything to a release folder

### 1.3 Tool Invocation Style

The tool should feel like a modern terminal application (similar to Claude Code or npm create). It should use:

- **Rich** library for colored output, panels, tables, progress indicators
- **Questionary** (or InquiryPy) for interactive prompts (path selection, confirmations)
- **Click** or **Typer** for CLI argument parsing

The tool is installed via `pip install -e .` (editable install during development) or `pip install apts-release` and invoked as:

```bash
# Interactive mode (asks for everything)
apts-release

# With arguments (skip prompts)
apts-release --esp32 ./path/to/esp32 --stm32 ./path/to/stm32

# Specific package only
apts-release --package rpi
apts-release --package ota
apts-release --package all   # default

# View release history
apts-release history

# Regenerate Excel/Changelog from registry (useful if manually edited)
apts-release export
```

---

## 2. Hardware & Build Context

### 2.1 Board Architecture

The APTS-IOT-V2-2 PCB has two controllers:

- **STM32H723VETx** — Main controller. ARM Cortex-M7, 512KB flash @ 0x08000000. Built with STM32CubeIDE. Produces a single `.bin` file.
- **ESP32** — IoT co-processor. Xtensa LX6, 16MB external SPI flash. Built with ESP-IDF v5.5.1 (`idf.py build`). Produces multiple `.bin` files (bootloader, partition table, app firmware, SPIFFS partitions).

### 2.2 ESP32 Build Output Location

After running `idf.py build`, the ESP32 project produces binaries in the `build/` directory. The key files and their typical paths:

```
esp32-project/
├── build/
│   ├── bootloader/
│   │   └── bootloader.bin              # ESP32 second-stage bootloader
│   ├── partition_table/
│   │   └── partition-table.bin         # Flash partition layout
│   ├── ota_data_initial/
│   │   └── ota_data_initial.bin        # OTA boot tracking data
│   ├── <project-name>.bin              # Main ESP32 application firmware
│   ├── webpage_1.bin                   # Web UI SPIFFS partition image
│   └── cdn.bin                         # Static assets SPIFFS partition image
├── main/
│   ├── app_config.h                    # ← ESP32 firmware version defined here (VERIFY)
│   └── ...
└── CMakeLists.txt
```

### 2.3 ESP32 Flash Partition Table (16MB)

This is critical for the RPI config file generation:

| Name         | Type | SubType  | Offset     | Size   | Purpose                      |
|-------------|------|----------|------------|--------|------------------------------|
| nvs          | data | nvs      | 0x9000     | 16 KB  | Settings, machine data       |
| otadata      | data | ota      | 0xD000     | 8 KB   | OTA boot tracking            |
| phy_init     | data | phy      | 0xF000     | 4 KB   | PHY calibration data         |
| factory      | app  | factory  | 0x10000    | 2 MB   | Factory firmware image       |
| ota_0        | app  | ota_0    | 0x210000   | 2 MB   | OTA firmware slot            |
| webpage_1    | data | spiffs   | 0x410000   | 512 KB | Web UI partition A           |
| webpage_2    | data | spiffs   | 0x490000   | 512 KB | Web UI partition B           |
| cdn          | data | spiffs   | 0x510000   | 2 MB   | Static assets (CSS, JS, img) |

> **Note:** The bootloader goes at offset 0x1000. The partition table at 0x8000.
> **IMPORTANT:** These offsets must be verified against the actual `partitions.csv` in the ESP32 project. The tool should ideally parse `partitions.csv` directly to get accurate offsets rather than hardcoding them.

### 2.4 STM32 Build Output Location

After building in STM32CubeIDE, the binary is at:

```
stm32-project/
├── Release/                            # or Debug/
│   └── <project-name>.bin              # STM32 firmware binary
├── Core/
│   └── Inc/
│       └── common/
│           ├── version.h               # ← STM32 firmware version defined here (VERIFY)
│           └── feature_config.h        # Machine type feature flags
├── HMI/                                # ← Manually placed HMI firmware
│   └── SMP-HMI-V1.6.7.tft             # Nextion HMI display firmware (manual)
└── STM32H723VETX.ioc
```

### 2.5 HMI File Handling

The Nextion HMI `.tft` file is NOT part of the automated build pipeline. The developer manually:
1. Exports the `.tft` file from Nextion Editor
2. Places it in the `HMI/` folder inside the STM32 project directory
3. Names it with a version in the filename (e.g., `SMP-HMI-V1.6.7.tft`)

The tool should:
- Look for `.tft` files in `<stm32-project>/HMI/`
- If exactly one `.tft` file exists, use it automatically
- If multiple exist, prompt the user to select one
- If none exist, warn and skip HMI from OTA package (RPI package doesn't include HMI)
- Extract the version from the filename using a regex pattern

---

## 3. Version Extraction Strategy

### 3.1 Version Sources

The tool needs to extract multiple independent version numbers:

| Component        | Version Source                        | Example Format          | Used In         |
|-----------------|---------------------------------------|------------------------|-----------------|
| ESP32 Firmware   | Source header file (e.g., `app_config.h`) | `#define FW_VERSION "2.0"` | RPI pkg name, OTA WIFI-FIRMWARE folder |
| STM32 Firmware   | Source header file (e.g., `version.h`)    | `#define STM32_FW_VERSION "2.1"` | RPI pkg name, OTA CORE-FIRMWARE folder |
| Web UI (webpage) | Source header or manifest              | `#define WEBPAGE_VERSION "1.3"` | OTA WEBPAGE folder |
| CDN              | Source header or manifest              | `#define CDN_VERSION "1.0"` | Not versioned in filename (optional) |
| HMI              | Filename of `.tft` file               | `SMP-HMI-V1.6.7.tft`  | OTA HMI folder |
| Overall Release  | User input OR computed                 | `V2.1.2`               | OTA root folder name, changelog, registry |

### 3.2 Version Extraction Approach

**IMPORTANT FOR CLAUDE CODE:** The exact `#define` names and file locations listed above are educated guesses. When you receive the actual project folders, you MUST:

1. Search for version-related defines: `grep -rn "VERSION\|FW_VER\|APP_VER" <project>/main/` (ESP32) and `grep -rn "VERSION\|FW_VER" <project>/Core/Inc/` (STM32)
2. Confirm the exact define names and file paths with the developer
3. Update the tool's config accordingly

The extraction logic should use regex:

```python
import re

def extract_version_from_header(filepath: str, define_name: str) -> str | None:
    """Extract version string from a C #define."""
    pattern = rf'#define\s+{define_name}\s+"([^"]+)"'
    with open(filepath, 'r') as f:
        content = f.read()
    match = re.search(pattern, content)
    return match.group(1) if match else None
```

### 3.3 Product Name Extraction

The product name (e.g., "SMART-PRESS") should be:
- Defined in a tool config file (`release-config.yaml`) in the project root, OR
- Extracted from the ESP32 project name in `CMakeLists.txt`, OR
- Prompted interactively if not found

---

## 4. Package Format Specifications

### 4.1 RPI Flash Programmer Package

**Purpose:** Full factory programming of a fresh APTS-IOT-V2-2 board. Programs both ESP32 (all partitions) and STM32 from scratch.

**ZIP filename pattern:**
```
APTS-IOT-<PRODUCT>-RPI-V<esp32_ver>-V<stm32_ver>.zip
```
Example: `APTS-IOT-SMART-PRESS-RPI-V2.0-V2.1.zip`

**Contents (flat structure, all files in ZIP root):**

| File in ZIP               | Source                                  | Description                     |
|--------------------------|-----------------------------------------|---------------------------------|
| `config`                  | Generated by tool (JSON)                | Flash addresses & file mapping  |
| `esp32_bootloader.bin`    | `build/bootloader/bootloader.bin`       | ESP32 bootloader                |
| `esp32_partition-table.bin`| `build/partition_table/partition-table.bin` | Partition layout             |
| `esp32_ota_data_initial.bin`| `build/ota_data_initial/ota_data_initial.bin` | OTA tracking data         |
| `esp32_<PRODUCT>-V<ver>.bin` | `build/<project-name>.bin`           | Main ESP32 app firmware         |
| `esp32_webpage_1.bin`     | `build/webpage_1.bin`                   | Web UI SPIFFS image             |
| `esp32_cdn.bin`           | `build/cdn.bin`                         | CDN static assets               |
| `stm32_firmware.bin`      | `Release/<project-name>.bin`            | STM32 firmware binary           |

**File naming rules:**
- All ESP32 files are prefixed with `esp32_`
- STM32 file is prefixed with `stm32_`
- The main ESP32 app firmware includes the product name and version
- Support files (bootloader, partition table, etc.) keep generic names with prefix

### 4.2 RPI Config File Specification

The `config` file is a JSON file that the Raspberry Pi flash programmer reads to know:
- Which files to flash
- At which flash addresses
- Flash parameters (baud rate, chip type, etc.)

**IMPORTANT FOR CLAUDE CODE:** The exact config format must be determined by examining an existing config file from a previous release. Ask the developer to provide a sample config file or its schema. Below is a probable structure based on ESP32 flash tooling conventions:

```json
{
  "board": "APTS-IOT-V2-2",
  "product": "SMART-PRESS",
  "esp32_version": "2.0",
  "stm32_version": "2.1",
  "esp32": {
    "chip": "esp32",
    "baud": 460800,
    "flash_size": "16MB",
    "flash_mode": "dio",
    "flash_freq": "40m",
    "files": [
      { "offset": "0x1000",   "file": "esp32_bootloader.bin" },
      { "offset": "0x8000",   "file": "esp32_partition-table.bin" },
      { "offset": "0xD000",   "file": "esp32_ota_data_initial.bin" },
      { "offset": "0x10000",  "file": "esp32_SMART-PRESS-V2.0.bin" },
      { "offset": "0x410000", "file": "esp32_webpage_1.bin" },
      { "offset": "0x510000", "file": "esp32_cdn.bin" }
    ]
  },
  "stm32": {
    "file": "stm32_firmware.bin",
    "address": "0x08000000",
    "method": "uart_bootloader"
  }
}
```

> **This is an assumed format.** The developer must confirm the actual config schema used by their RPI flash programmer software.

### 4.3 OTA Package

**Purpose:** Customer-side firmware update via the ESP32's OTA web interface. Contains only the files that can be updated over-the-air (no bootloader, no partition table).

**ZIP filename pattern:**
```
<PRODUCT>-FW-OTA-V<release_ver>.zip
```
Example: `SMART-PRESS-FW-OTA-V2.1.2.zip`

**Contents (folder tree structure):**

```
<PRODUCT>-FW-OTA-V<release_ver>/
├── CORE-FIRMWARE/
│   └── Core-Firmware-V<stm32_ver>.bin          # STM32 firmware
│
├── HMI/
│   └── <HMI-filename>.tft                       # Nextion HMI (copied as-is with version in name)
│
├── WEBPAGE/
│   └── UI-V<webpage_ver>.bin                    # Web UI SPIFFS image
│
└── WIFI-FIRMWARE/
    └── WIFI-V<esp32_ver>.bin                    # ESP32 main app firmware
```

**OTA file mapping:**

| OTA Folder       | Source File                    | Renamed To                         |
|-----------------|--------------------------------|------------------------------------|
| CORE-FIRMWARE/   | STM32 Release `.bin`           | `Core-Firmware-V<stm32_ver>.bin`   |
| HMI/             | `<stm32-project>/HMI/*.tft`   | Kept as-is (already versioned)     |
| WEBPAGE/         | `build/webpage_1.bin`          | `UI-V<webpage_ver>.bin`            |
| WIFI-FIRMWARE/   | `build/<project-name>.bin`     | `WIFI-V<esp32_ver>.bin`            |

**Notes:**
- The OTA package does NOT include: bootloader, partition table, ota_data_initial, or cdn.bin
- The CDN is excluded because it contains static assets that rarely change and are large
- The root folder inside the ZIP matches the ZIP filename (without .zip)
- If HMI `.tft` file is not available, the HMI/ folder is omitted with a warning

---

## 5. Release Tracking System

This is the core record-keeping architecture. The JSON registry is the **single source of truth**. Both the markdown changelog and Excel tracker are derived from it. This means they are always in sync and never need manual editing.

### 5.1 Data Flow

```
apts-release (packaging run)
         │
         ▼
┌─────────────────────────┐
│  release-registry.json  │  ← Single source of truth (append-only)
│  (append new entry)     │      Accumulates every release ever made
└───────────┬─────────────┘
            │
      ┌─────┴──────┐
      ▼            ▼
┌───────────┐  ┌──────────────────────┐
│CHANGELOG.md│  │release-tracker.xlsx  │
│(regenerated│  │(regenerated from     │
│ from JSON) │  │ JSON every time)     │
└───────────┘  └──────────────────────┘
```

Every time the tool runs:
1. It appends a new release entry to `release-registry.json`
2. It regenerates `CHANGELOG.md` completely from the registry (newest first)
3. It regenerates `release-tracker.xlsx` completely from the registry

This means if you manually fix a typo in the JSON registry and run `apts-release export`, both the changelog and Excel are rebuilt correctly.

### 5.2 Release Registry — `release-registry.json`

This file lives in the release output directory and accumulates every release across all products.

**Schema:**

```json
{
  "schema_version": "1.0",
  "releases": [
    {
      "id": "REL-2026-0001",
      "timestamp": "2026-02-28T14:30:00",
      "product": "SMART-PRESS",
      "board": "APTS-IOT-V2-2",
      "release_version": "V2.1.2",
      "components": {
        "esp32_firmware": {
          "version": "V2.0",
          "file": "esp32_SMART-PRESS-V2.0.bin",
          "size_bytes": 690176,
          "sha256": "a3f2b8c1d4e5..."
        },
        "stm32_firmware": {
          "version": "V2.1",
          "file": "stm32_firmware.bin",
          "size_bytes": 91136,
          "sha256": "7c1d4e9f2a3b..."
        },
        "webpage": {
          "version": "V1.3",
          "file": "esp32_webpage_1.bin",
          "size_bytes": 14336,
          "sha256": "b2c3d4e5f6a7..."
        },
        "cdn": {
          "version": null,
          "file": "esp32_cdn.bin",
          "size_bytes": 638976,
          "sha256": "d4e5f6a7b8c9..."
        },
        "hmi": {
          "version": "V1.6.7",
          "file": "SMP-HMI-V1.6.7.tft",
          "size_bytes": 2516582,
          "sha256": "e5f6a7b8c9d0..."
        }
      },
      "packages": {
        "rpi": {
          "filename": "APTS-IOT-SMART-PRESS-RPI-V2.0-V2.1.zip",
          "size_bytes": 1489920,
          "sha256": "f6a7b8c9d0e1..."
        },
        "ota": {
          "filename": "SMART-PRESS-FW-OTA-V2.1.2.zip",
          "size_bytes": 2990080,
          "sha256": "a7b8c9d0e1f2..."
        }
      },
      "notes": "Fixed servo homing sequence timeout on HSC mode",
      "released_by": "Siva"
    }
  ]
}
```

**Field details:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Auto-generated unique ID. Format: `REL-YYYY-NNNN` where NNNN is a zero-padded sequential counter for the year. |
| `timestamp` | string | ISO 8601 datetime when the release was created. |
| `product` | string | Product name (e.g., "SMART-PRESS", "HSC-TUBE-CUTTER", "PULL-TESTER"). |
| `board` | string | Board identifier, always "APTS-IOT-V2-2" for now. |
| `release_version` | string | Overall release version chosen by the developer. |
| `components` | object | Map of component name → version, filename, size, and SHA256 hash. |
| `components.*.version` | string or null | Version string. Null if the component has no version (e.g., CDN). |
| `components.*.file` | string | Filename as it appears in the package. |
| `components.*.size_bytes` | integer | Original file size in bytes. |
| `components.*.sha256` | string | SHA256 hash of the original bin file for integrity verification. |
| `packages` | object | Map of package type → output filename, size, and SHA256 hash. |
| `notes` | string | One-line release note describing what changed. Can be empty string. |
| `released_by` | string | Name of the person who ran the tool. Defaults to system username, overridable. |

**Release ID generation logic:**

```python
def generate_release_id(existing_releases: list) -> str:
    """Generate next sequential release ID for the current year."""
    year = datetime.now().year
    prefix = f"REL-{year}-"
    year_ids = [
        int(r["id"].split("-")[-1])
        for r in existing_releases
        if r["id"].startswith(prefix)
    ]
    next_num = max(year_ids, default=0) + 1
    return f"{prefix}{next_num:04d}"
```

### 5.3 Release Tracker Excel — `release-tracker.xlsx`

This spreadsheet is regenerated entirely from the registry every time. It is designed for humans — for sharing with manufacturing teams, management, or customers.

**Filename:** `release-tracker.xlsx` (in the release output directory)

**Sheet 1: "All Releases"**

A single table with one row per release, sorted newest first:

| Column | Source Field | Width | Format |
|--------|-------------|-------|--------|
| Release ID | `id` | 16 | Text, monospace-friendly |
| Date | `timestamp` | 12 | Date format: DD-MM-YYYY |
| Product | `product` | 20 | Text |
| Release Version | `release_version` | 14 | Text, bold |
| ESP32 Version | `components.esp32_firmware.version` | 14 | Text |
| STM32 Version | `components.stm32_firmware.version` | 14 | Text |
| WebUI Version | `components.webpage.version` | 14 | Text |
| HMI Version | `components.hmi.version` | 14 | Text (or "N/A") |
| RPI Package | `packages.rpi.filename` | 40 | Text |
| RPI Size | `packages.rpi.size_bytes` | 10 | KB/MB formatted |
| OTA Package | `packages.ota.filename` | 40 | Text |
| OTA Size | `packages.ota.size_bytes` | 10 | KB/MB formatted |
| Notes | `notes` | 50 | Text, word-wrap |
| Released By | `released_by` | 14 | Text |

**Formatting requirements:**
- Header row: Bold, background color (dark blue `#1F4E79`, white text), frozen row (stays visible when scrolling)
- Alternating row colors: White / Light blue (`#D6E4F0`) for readability
- Column auto-width or use the suggested widths above
- Date column: formatted as DD-MM-YYYY (Indian date format)
- Size columns: Display as "1.42 MB" or "89 KB" (human-readable, not raw bytes)
- The entire table should have thin borders for printability
- Sheet name: "All Releases"

**Sheet 2: "Product Summary"**

If the registry contains releases for more than one product, add a second sheet with a summary:

| Column | Description |
|--------|-------------|
| Product | Product name |
| Total Releases | Count of releases for this product |
| Latest Version | Most recent release_version |
| Latest Date | Date of most recent release |
| Latest ESP32 | ESP32 version in the most recent release |
| Latest STM32 | STM32 version in the most recent release |
| First Release | Date of the earliest release for this product |

This sheet is a quick overview for management — "what's the latest version of each product?"

**Implementation with openpyxl:**

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def generate_excel(registry_path: Path, output_path: Path) -> None:
    """Regenerate the Excel tracker from the registry."""
    registry = load_registry(registry_path)
    releases = registry.get("releases", [])

    wb = Workbook()
    ws = wb.active
    ws.title = "All Releases"

    # Header styling
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    light_blue = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")

    # Write headers
    headers = [
        "Release ID", "Date", "Product", "Release Version",
        "ESP32 Ver", "STM32 Ver", "WebUI Ver", "HMI Ver",
        "RPI Package", "RPI Size", "OTA Package", "OTA Size",
        "Notes", "Released By"
    ]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal="center")

    # Freeze header row
    ws.freeze_panes = "A2"

    # Write data rows (newest first)
    for row_idx, release in enumerate(reversed(releases), 2):
        row_data = [
            release["id"],
            release["timestamp"][:10],  # Date only
            release["product"],
            release["release_version"],
            release["components"]["esp32_firmware"]["version"],
            release["components"]["stm32_firmware"]["version"],
            release["components"]["webpage"]["version"],
            release["components"].get("hmi", {}).get("version", "N/A"),
            release["packages"].get("rpi", {}).get("filename", "—"),
            format_size(release["packages"].get("rpi", {}).get("size_bytes", 0)),
            release["packages"].get("ota", {}).get("filename", "—"),
            format_size(release["packages"].get("ota", {}).get("size_bytes", 0)),
            release.get("notes", ""),
            release.get("released_by", ""),
        ]
        for col, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col, value=value)
            cell.border = thin_border
            if row_idx % 2 == 0:
                cell.fill = light_blue

    # Auto-adjust column widths (approximate)
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = max(
            len(str(headers[col - 1])) + 4, 14
        )

    wb.save(output_path)
```

### 5.4 Changelog — `CHANGELOG.md`

The changelog is regenerated from the registry. It is a developer-facing markdown file, sorted newest first.

**Format:**

```markdown
# APTS-IOT Firmware Release Changelog

> Auto-generated from release-registry.json. Do not edit manually.

---

## [V2.1.2] - 28-02-2026 — SMART-PRESS

**Release ID:** REL-2026-0012
**Released by:** Siva

| Component | Version |
|-----------|---------|
| ESP32 Firmware | V2.0 |
| STM32 Firmware | V2.1 |
| Web UI | V1.3 |
| HMI | V1.6.7 |

**Packages:**
- `APTS-IOT-SMART-PRESS-RPI-V2.0-V2.1.zip` (1.42 MB)
- `SMART-PRESS-FW-OTA-V2.1.2.zip` (2.85 MB)

**Notes:** Fixed servo homing sequence timeout on HSC mode

---

## [V2.1.1] - 15-02-2026 — SMART-PRESS

...
```

**Generation logic:** Iterate over `releases` array in reverse order (newest first), format each entry using the template above. The entire file is overwritten each time — it's always a complete regeneration.

### 5.5 Where Release Files Live

All release tracking files live in the configured output directory:

```
releases/                               # Configurable via release-config.yaml
├── release-registry.json               # Source of truth (append-only)
├── release-tracker.xlsx                # Regenerated from registry
├── CHANGELOG.md                        # Regenerated from registry
│
├── APTS-IOT-SMART-PRESS-RPI-V2.0-V2.1.zip    # RPI package
├── SMART-PRESS-FW-OTA-V2.1.2.zip              # OTA package
│
├── APTS-IOT-SMART-PRESS-RPI-V1.9-V2.0.zip    # Previous RPI package
├── SMART-PRESS-FW-OTA-V2.1.1.zip              # Previous OTA package
└── ...                                         # All historical ZIPs
```

Previous release ZIPs are never deleted. They accumulate in the release directory alongside the registry.

---

## 6. Tool Architecture

### 6.1 Project Structure

```
apts-release/
├── pyproject.toml                  # Package config (PEP 621), CLI entry point
├── README.md
├── src/
│   └── apts_release/
│       ├── __init__.py
│       ├── cli.py                  # CLI entry point (typer + rich)
│       ├── config.py               # Project config loading (release-config.yaml)
│       ├── scanner.py              # Scans project dirs, locates bin files
│       ├── version_extractor.py    # Extracts versions from source headers
│       ├── package_rpi.py          # RPI flash package generator
│       ├── package_ota.py          # OTA package generator
│       ├── registry.py             # Release registry (JSON read/write/append)
│       ├── changelog.py            # Changelog generation from registry
│       ├── excel_export.py         # Excel tracker generation from registry
│       └── utils.py                # Shared utilities (file ops, hashing, formatting)
└── tests/
    ├── test_scanner.py
    ├── test_version_extractor.py
    ├── test_package_rpi.py
    ├── test_package_ota.py
    ├── test_registry.py
    └── test_excel_export.py
```

### 6.2 Module Responsibilities

#### `cli.py` — Entry Point & User Interface

- Parses CLI arguments (`--esp32`, `--stm32`, `--package`, `--output`, `--no-changelog`)
- Subcommands: default (package), `history` (show past releases), `export` (regenerate Excel/changelog)
- If paths not provided, shows interactive folder browser/prompt
- Displays a rich panel with detected project info (product name, versions, files found)
- **Prompts for release notes** (one-liner, or Enter to skip)
- Shows confirmation table before packaging
- Displays progress during ZIP creation
- Prints summary with output file paths, sizes, and release ID

#### `config.py` — Project Configuration

- Looks for `release-config.yaml` in the project root (or a parent directory)
- Falls back to interactive prompts if no config found
- Stores product name, version define names, custom file mappings

**release-config.yaml schema:**

```yaml
# This file lives in the project root (parent of esp32/ and stm32/ folders)
product:
  name: "SMART-PRESS"               # Product name used in filenames
  board: "APTS-IOT-V2-2"            # Board identifier

esp32:
  build_dir: "build"                 # Relative to ESP32 project root
  version:
    file: "main/app_config.h"        # Relative to ESP32 project root
    define: "FW_VERSION"             # The #define name to search for
  webpage_version:
    file: "main/app_config.h"        # Can be same or different file
    define: "WEBPAGE_VERSION"        # The #define for webpage version

stm32:
  build_dir: "Release"               # Relative to STM32 project root
  version:
    file: "Core/Inc/common/version.h" # Relative to STM32 project root
    define: "STM32_FW_VERSION"        # The #define name to search for
  hmi_dir: "HMI"                     # Folder containing .tft file

release:
  output_dir: "./releases"           # Where to put generated ZIPs + registry + Excel
  registry: "./releases/release-registry.json"
  changelog: "./releases/CHANGELOG.md"
  excel: "./releases/release-tracker.xlsx"
```

#### `scanner.py` — File Discovery

- Given ESP32 and STM32 project paths, locates all required bin files
- Validates that all expected files exist
- Reports missing files with clear error messages
- Returns a structured manifest of found files with their full paths

**Expected files for ESP32:**

| Logical Name     | Search Path (relative to ESP32 project)      | Required |
|-----------------|-----------------------------------------------|----------|
| bootloader       | `build/bootloader/bootloader.bin`             | Yes      |
| partition_table  | `build/partition_table/partition-table.bin`    | Yes      |
| ota_data_initial | `build/ota_data_initial/ota_data_initial.bin` | Yes      |
| app_firmware     | `build/*.bin` (main app, largest file or match project name) | Yes |
| webpage_1        | `build/webpage_1.bin`                         | Yes      |
| cdn              | `build/cdn.bin`                               | Yes      |

**Expected files for STM32:**

| Logical Name | Search Path (relative to STM32 project)      | Required |
|-------------|-----------------------------------------------|----------|
| firmware     | `Release/*.bin` (should be exactly one)        | Yes      |
| hmi          | `HMI/*.tft` (zero or one)                     | No       |

#### `version_extractor.py` — Version Parsing

- Reads C header files and extracts `#define` version strings
- Extracts HMI version from `.tft` filename
- Returns a VersionInfo dataclass:

```python
@dataclass
class VersionInfo:
    esp32_version: str          # e.g., "2.0"
    stm32_version: str          # e.g., "2.1"
    webpage_version: str        # e.g., "1.3"
    hmi_version: str | None     # e.g., "1.6.7" (None if no HMI)
    release_version: str        # e.g., "2.1.2" (prompted or computed)
```

#### `package_rpi.py` — RPI Flash Package Generator

- Takes file manifest + version info
- Creates a temporary directory
- Copies and renames files per the RPI naming convention (Section 4.1)
- Generates the `config` JSON file (Section 4.2)
- ZIPs everything flat
- Returns a PackageResult with path, size, and SHA256

#### `package_ota.py` — OTA Package Generator

- Takes file manifest + version info
- Creates the folder tree structure (Section 4.3)
- Copies and renames files per OTA conventions
- ZIPs with the root folder preserved inside the archive
- Returns a PackageResult with path, size, and SHA256

#### `registry.py` — Release Registry Management

This is the core record-keeping module. It owns the `release-registry.json` file.

**Functions:**

```python
def load_registry(registry_path: Path) -> dict:
    """Load existing registry or create empty one."""

def append_release(registry_path: Path, release_entry: dict) -> str:
    """Append a new release entry. Returns the generated release ID."""

def get_releases(registry_path: Path, product: str | None = None) -> list[dict]:
    """Get all releases, optionally filtered by product name."""

def get_latest_release(registry_path: Path, product: str) -> dict | None:
    """Get the most recent release for a product."""

def build_release_entry(
    product: str,
    board: str,
    release_version: str,
    versions: VersionInfo,
    file_manifest: dict,
    package_results: dict,
    notes: str,
    released_by: str,
) -> dict:
    """Build a complete release entry dict ready for appending."""
```

**Key behaviors:**
- If `release-registry.json` doesn't exist, create it with an empty releases array
- Never delete or modify existing entries (append-only)
- Generate release IDs sequentially per year
- Compute SHA256 hashes for all bin files and generated ZIPs

#### `changelog.py` — Changelog Generation

- Reads the registry and regenerates `CHANGELOG.md` completely
- Sorted newest-first
- Follows the format specified in Section 5.4
- One function: `generate_changelog(registry_path: Path, output_path: Path)`

#### `excel_export.py` — Excel Tracker Generation

- Reads the registry and regenerates `release-tracker.xlsx` completely
- Uses `openpyxl` library
- Creates formatted table with styling per Section 5.3 specs
- One function: `generate_excel(registry_path: Path, output_path: Path)`

#### `utils.py` — Shared Utilities

- `compute_sha256(filepath: Path) -> str` — SHA256 hash of a file
- `format_size(size_bytes: int) -> str` — "1.42 MB" or "89 KB" format
- `safe_copy(src: Path, dst: Path) -> None` — Copy with size verification
- `ensure_dir(path: Path) -> None` — Create directory if it doesn't exist

### 6.3 CLI Flow (Step by Step)

```
$ apts-release

  ╭─────────────────────────────────────────╮
  │  APTS-IOT Firmware Release Tool v1.0    │
  │  Board: APTS-IOT-V2-2                   │
  ╰─────────────────────────────────────────╯

? ESP32 project folder: ./firmware/esp32-smart-press
? STM32 project folder: ./firmware/stm32-smart-press

  Scanning projects...

  ┌─────────────────────────────────────────────┐
  │  ESP32 Files Found                          │
  ├─────────────────┬───────────┬───────────────┤
  │ File            │ Size      │ Status        │
  ├─────────────────┼───────────┼───────────────┤
  │ bootloader.bin  │ 16 KB     │ ✓ Found       │
  │ partition-table │ 1 KB      │ ✓ Found       │
  │ ota_data_init   │ 1 KB      │ ✓ Found       │
  │ app firmware    │ 674 KB    │ ✓ Found       │
  │ webpage_1.bin   │ 14 KB     │ ✓ Found       │
  │ cdn.bin         │ 623 KB    │ ✓ Found       │
  └─────────────────┴───────────┴───────────────┘

  ┌─────────────────────────────────────────────┐
  │  STM32 Files Found                          │
  ├─────────────────┬───────────┬───────────────┤
  │ firmware.bin    │ 89 KB     │ ✓ Found       │
  │ HMI .tft       │ 2.40 MB   │ ✓ Found       │
  └─────────────────┴───────────┴───────────────┘

  ┌─────────────────────────────────────────────┐
  │  Versions Detected                          │
  ├─────────────────┬───────────────────────────┤
  │ ESP32 Firmware  │ V2.0                      │
  │ STM32 Firmware  │ V2.1                      │
  │ Web UI          │ V1.3                      │
  │ HMI             │ V1.6.7 (from filename)    │
  └─────────────────┴───────────────────────────┘

? Overall release version: V2.1.2
? Release notes: Fixed servo homing sequence timeout on HSC mode
? Generate packages: [✓] RPI Flash  [✓] OTA

  Generating packages...
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%

  ╭──────────────────────────────────────────────────────────────────╮
  │  ✓ Release Complete — REL-2026-0012                             │
  │                                                                  │
  │  RPI:  ./releases/APTS-IOT-SMART-PRESS-RPI-V2.0-V2.1.zip      │
  │        Size: 1.42 MB | SHA256: a3f2b8c1...                      │
  │                                                                  │
  │  OTA:  ./releases/SMART-PRESS-FW-OTA-V2.1.2.zip                │
  │        Size: 2.85 MB | SHA256: 7c1d4e9f...                      │
  │                                                                  │
  │  Registry:   ./releases/release-registry.json  (13 releases)    │
  │  Excel:      ./releases/release-tracker.xlsx                     │
  │  Changelog:  ./releases/CHANGELOG.md                             │
  ╰──────────────────────────────────────────────────────────────────╯
```

### 6.4 History Subcommand

```
$ apts-release history

  ╭─────────────────────────────────────────────────────────────────────────────────────────╮
  │  APTS-IOT Release History                                                               │
  ╰─────────────────────────────────────────────────────────────────────────────────────────╯

  ┌──────────────────┬────────────┬─────────────────┬─────────┬──────┬──────┬──────────────┐
  │ ID               │ Date       │ Product         │ Release │ ESP32│ STM32│ Notes        │
  ├──────────────────┼────────────┼─────────────────┼─────────┼──────┼──────┼──────────────┤
  │ REL-2026-0012    │ 28-02-2026 │ SMART-PRESS     │ V2.1.2  │ V2.0 │ V2.1 │ Servo fix    │
  │ REL-2026-0011    │ 15-02-2026 │ SMART-PRESS     │ V2.1.1  │ V2.0 │ V2.0 │ HMI update   │
  │ REL-2026-0010    │ 10-02-2026 │ HSC-TUBE-CUTTER │ V1.3.0  │ V1.8 │ V3.2 │ Initial HSC  │
  └──────────────────┴────────────┴─────────────────┴─────────┴──────┴──────┴──────────────┘

  Total: 12 releases across 2 products
  Registry: ./releases/release-registry.json
```

### 6.5 Export Subcommand

```
$ apts-release export

  Regenerating from ./releases/release-registry.json ...
  ✓ CHANGELOG.md  (12 entries)
  ✓ release-tracker.xlsx  (12 rows, 2 sheets)
```

This is useful when you manually edit the registry JSON (e.g., fix a typo in notes) and want to regenerate the derived files.

---

## 7. Dependencies

### 7.1 Python Packages

```toml
[project]
name = "apts-release"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = [
    "typer>=0.9.0",           # CLI framework (built on click)
    "rich>=13.0.0",           # Terminal formatting (panels, tables, progress)
    "questionary>=2.0.0",     # Interactive prompts (path input, checkboxes)
    "pyyaml>=6.0",            # YAML config parsing
    "openpyxl>=3.1.0",        # Excel file generation
]

[project.scripts]
apts-release = "apts_release.cli:app"
```

### 7.2 Python Version

Minimum Python 3.10 (for match/case and modern type hints). Target 3.11+ for best performance.

---

## 8. Configuration File Defaults

If no `release-config.yaml` exists, the tool should work with sensible defaults and interactive prompts. The defaults are:

```python
DEFAULTS = {
    "esp32_build_dir": "build",
    "stm32_build_dir": "Release",
    "hmi_dir": "HMI",
    "output_dir": "./releases",
    "registry_path": "./releases/release-registry.json",
    "changelog_path": "./releases/CHANGELOG.md",
    "excel_path": "./releases/release-tracker.xlsx",
    "esp32_version_file": None,     # Must be discovered or prompted
    "esp32_version_define": None,   # Must be discovered or prompted
    "stm32_version_file": None,     # Must be discovered or prompted
    "stm32_version_define": None,   # Must be discovered or prompted
}
```

When version source files are not configured, the tool should:
1. Search for common patterns (`grep -r "VERSION" --include="*.h"`) in the project
2. Display found candidates and let the user pick
3. Offer to save the selection to `release-config.yaml` for next time

---

## 9. Error Handling

### 9.1 Pre-flight Checks

Before any packaging, the tool validates:

| Check                              | Action on Failure                          |
|------------------------------------|--------------------------------------------|
| ESP32 project path exists           | Error: "ESP32 project not found at: ..."   |
| STM32 project path exists           | Error: "STM32 project not found at: ..."   |
| ESP32 `build/` directory exists     | Error: "ESP32 not built. Run `idf.py build` first." |
| STM32 `Release/` directory exists   | Error: "STM32 not built. Build in Release mode first." |
| All required bin files present      | Error: list missing files                   |
| Version strings extractable         | Warning: prompt for manual version input    |
| HMI `.tft` file present            | Warning: "No HMI file found. OTA will skip HMI folder." |
| Output directory writable           | Error: "Cannot write to output directory"   |
| Duplicate release version           | Warning: "V2.1.2 already exists for SMART-PRESS. Continue?" |
| Registry JSON valid                | Warning: back up as `.bak`, create fresh    |

### 9.2 Recovery Behavior

- If version extraction fails for any component, prompt the user to enter it manually
- If the output ZIP already exists, ask before overwriting
- Never partially write a ZIP — use a temp directory and atomic move
- If registry JSON is corrupted, back it up as `.json.bak` and start fresh with a warning
- If Excel generation fails (openpyxl error), warn but don't abort — ZIPs and registry are more important

---

## 10. Future Enhancements (Not in V1)

These are explicitly OUT OF SCOPE for the initial build but documented for future reference:

1. **Python Flash Tool Package** — Third package format with different naming conventions (can be added as `package_python.py` following the same pattern)
2. **Git Integration** — Auto-tag releases, push to a release branch
3. **CI/CD Integration** — GitHub Actions / GitLab CI wrapper
4. **Partition Table Parser** — Read `partitions.csv` to auto-compute flash offsets for config
5. **Diff Report** — Show what changed since last release (file sizes, version deltas)
6. **Multi-product Batch** — Package for multiple machine variants in one run
7. **Registry Editing** — Interactive TUI for editing/deleting registry entries
8. **Excel Charts** — Add a chart sheet showing version timeline per product

---

## 11. Implementation Order for Claude Code

When building this tool, follow this sequence:

### Phase 1: Scaffolding
1. Create the project structure (`pyproject.toml`, package layout, `__init__.py`)
2. Set up the CLI entry point with Typer + Rich
3. Implement basic `--help` and `--version` commands
4. Test that `apts-release` runs from terminal after `pip install -e .`

### Phase 2: Core Logic
5. Implement `scanner.py` — file discovery for both ESP32 and STM32
6. Implement `version_extractor.py` — header parsing and HMI filename parsing
7. Implement `config.py` — YAML config loading with defaults
8. Implement `utils.py` — SHA256 hashing, size formatting, file operations

### Phase 3: Package Generators
9. Implement `package_rpi.py` — flat ZIP with renamed files + config JSON
10. Implement `package_ota.py` — folder-tree ZIP with OTA structure
11. Integrate both generators into the CLI flow

### Phase 4: Release Tracking
12. Implement `registry.py` — JSON registry load/append/query
13. Implement `changelog.py` — generate CHANGELOG.md from registry
14. Implement `excel_export.py` — generate release-tracker.xlsx from registry
15. Wire registry + changelog + Excel into the main CLI flow after packaging

### Phase 5: Polish
16. Add the `history` subcommand (read registry, display Rich table)
17. Add the `export` subcommand (regenerate changelog + Excel from registry)
18. Add the interactive Rich UI (panels, tables, progress)
19. Add error handling, pre-flight validation, and duplicate detection
20. Test end-to-end with real project folders

### Key Decision Points (Ask the Developer)

During implementation, Claude Code MUST pause and ask the developer to confirm:

1. **"What are the exact #define names for versions in your ESP32 and STM32 source?"** — Search with grep, show candidates, and confirm.
2. **"Can you show me an existing RPI config file?"** — The JSON structure must match what the RPI programmer expects. Don't guess.
3. **"What is the main ESP32 .bin filename in your build/ directory?"** — It's typically the project name from CMakeLists.txt but must be confirmed.
4. **"What is the STM32 .bin filename in your Release/ directory?"** — Same reason.
5. **"How do you determine the overall release version (e.g., V2.1.2)?"** — Is it derived from component versions, or independently chosen?

---

## 12. Testing Strategy

### 12.1 Unit Tests

- `test_version_extractor.py` — Test regex extraction with various `#define` formats
- `test_scanner.py` — Test file discovery with mock directory structures
- `test_package_rpi.py` — Verify ZIP contents and naming
- `test_package_ota.py` — Verify folder tree structure in ZIP
- `test_registry.py` — Test append, load, ID generation, duplicate detection
- `test_excel_export.py` — Verify Excel file creation, column count, formatting

### 12.2 Integration Test

Create a mock project structure with dummy `.bin` files and run the full CLI flow:

```bash
# Create test fixtures
mkdir -p test_esp32/build/bootloader test_esp32/build/partition_table
mkdir -p test_esp32/build/ota_data_initial test_esp32/main
mkdir -p test_stm32/Release test_stm32/Core/Inc/common test_stm32/HMI

# Create dummy files
dd if=/dev/zero of=test_esp32/build/bootloader/bootloader.bin bs=1024 count=16
dd if=/dev/zero of=test_esp32/build/partition_table/partition-table.bin bs=1024 count=1
# ... etc

# Create version headers
echo '#define FW_VERSION "2.0"' > test_esp32/main/app_config.h
echo '#define STM32_FW_VERSION "2.1"' > test_stm32/Core/Inc/common/version.h

# Run tool
apts-release --esp32 ./test_esp32 --stm32 ./test_stm32
```

---

## Appendix A: File Naming Quick Reference

### RPI Package Files
```
esp32_bootloader.bin
esp32_partition-table.bin
esp32_ota_data_initial.bin
esp32_SMART-PRESS-V2.0.bin          ← product name + ESP32 version
esp32_webpage_1.bin
esp32_cdn.bin
stm32_firmware.bin
config                               ← JSON, no extension
```

### OTA Package Tree
```
SMART-PRESS-FW-OTA-V2.1.2/
├── CORE-FIRMWARE/Core-Firmware-V2.1.bin
├── HMI/SMP-HMI-V1.6.7.tft
├── WEBPAGE/UI-V1.3.bin
└── WIFI-FIRMWARE/WIFI-V2.0.bin
```

### Release Tracking Files
```
releases/
├── release-registry.json        ← Source of truth (never regenerated, only appended)
├── release-tracker.xlsx          ← Regenerated from registry
├── CHANGELOG.md                  ← Regenerated from registry
├── *.zip                         ← All release packages (accumulate)
```

---

## Appendix B: Sample release-config.yaml

```yaml
product:
  name: "SMART-PRESS"
  board: "APTS-IOT-V2-2"

esp32:
  build_dir: "build"
  version:
    file: "main/app_config.h"
    define: "FW_VERSION"
  webpage_version:
    file: "main/app_config.h"
    define: "WEBPAGE_VERSION"

stm32:
  build_dir: "Release"
  version:
    file: "Core/Inc/common/version.h"
    define: "STM32_FW_VERSION"
  hmi_dir: "HMI"

release:
  output_dir: "./releases"
  registry: "./releases/release-registry.json"
  changelog: "./releases/CHANGELOG.md"
  excel: "./releases/release-tracker.xlsx"
```

---

## Appendix C: Sample release-registry.json

```json
{
  "schema_version": "1.0",
  "releases": [
    {
      "id": "REL-2026-0001",
      "timestamp": "2026-02-10T09:15:00",
      "product": "HSC-TUBE-CUTTER",
      "board": "APTS-IOT-V2-2",
      "release_version": "V1.3.0",
      "components": {
        "esp32_firmware": {
          "version": "V1.8",
          "file": "esp32_HSC-TUBE-CUTTER-V1.8.bin",
          "size_bytes": 655360,
          "sha256": "abc123..."
        },
        "stm32_firmware": {
          "version": "V3.2",
          "file": "stm32_firmware.bin",
          "size_bytes": 102400,
          "sha256": "def456..."
        },
        "webpage": {
          "version": "V1.1",
          "file": "esp32_webpage_1.bin",
          "size_bytes": 14336,
          "sha256": "ghi789..."
        },
        "cdn": {
          "version": null,
          "file": "esp32_cdn.bin",
          "size_bytes": 638976,
          "sha256": "jkl012..."
        },
        "hmi": {
          "version": "V1.2.0",
          "file": "HSC-HMI-V1.2.0.tft",
          "size_bytes": 1048576,
          "sha256": "mno345..."
        }
      },
      "packages": {
        "rpi": {
          "filename": "APTS-IOT-HSC-TUBE-CUTTER-RPI-V1.8-V3.2.zip",
          "size_bytes": 1310720,
          "sha256": "pqr678..."
        },
        "ota": {
          "filename": "HSC-TUBE-CUTTER-FW-OTA-V1.3.0.zip",
          "size_bytes": 2621440,
          "sha256": "stu901..."
        }
      },
      "notes": "Initial release for HSC Tube Cutting Machine",
      "released_by": "Siva"
    },
    {
      "id": "REL-2026-0002",
      "timestamp": "2026-02-15T16:45:00",
      "product": "SMART-PRESS",
      "board": "APTS-IOT-V2-2",
      "release_version": "V2.1.1",
      "components": {
        "esp32_firmware": {
          "version": "V2.0",
          "file": "esp32_SMART-PRESS-V2.0.bin",
          "size_bytes": 690176,
          "sha256": "vwx234..."
        },
        "stm32_firmware": {
          "version": "V2.0",
          "file": "stm32_firmware.bin",
          "size_bytes": 89088,
          "sha256": "yza567..."
        },
        "webpage": {
          "version": "V1.3",
          "file": "esp32_webpage_1.bin",
          "size_bytes": 14336,
          "sha256": "bcd890..."
        },
        "cdn": {
          "version": null,
          "file": "esp32_cdn.bin",
          "size_bytes": 638976,
          "sha256": "efg123..."
        },
        "hmi": {
          "version": "V1.6.5",
          "file": "SMP-HMI-V1.6.5.tft",
          "size_bytes": 2516582,
          "sha256": "hij456..."
        }
      },
      "packages": {
        "rpi": {
          "filename": "APTS-IOT-SMART-PRESS-RPI-V2.0-V2.0.zip",
          "size_bytes": 1480000,
          "sha256": "klm789..."
        },
        "ota": {
          "filename": "SMART-PRESS-FW-OTA-V2.1.1.zip",
          "size_bytes": 2880000,
          "sha256": "nop012..."
        }
      },
      "notes": "HMI page layout update for batch counter display",
      "released_by": "Siva"
    }
  ]
}
```

---

*End of Requirements Document*
