# APTS-Release CLI Tool — Developer Reference

> Internal CLI tool for packaging APTS-IOT-V2-2 firmware (STM32H723VETx + ESP32)
> into distribution-ready ZIP archives with built-in release tracking and GitHub publishing.

**Company:** Competent Crimping Machinery Pvt. Ltd / APTS Engineering
**Board:** APTS-IOT-V2-2 (dual-controller: STM32H723VETx + ESP32)
**Machines:** Tube Cutting (HSC), Smart Crimping Press, Pull Tester, and others

---

## Project Structure

```
apts-cli-release-package-tool/
├── CLAUDE.md                           ← this file
├── apts-release/
│   ├── pyproject.toml                  ← package config (deps, entry point)
│   ├── README.md                       ← user-facing documentation
│   ├── src/apts_release/
│   │   ├── __init__.py                 ← version: 1.0.0
│   │   ├── cli.py                      ← main CLI (Typer app, all subcommands)
│   │   ├── config.py                   ← YAML config loader (ProjectConfig dataclass)
│   │   ├── scanner.py                  ← file discovery (scans build dirs for .bin files)
│   │   ├── version_extractor.py        ← version parsing (CMake, C headers, txt, filenames)
│   │   ├── package_rpi.py              ← FLASH ZIP generator (flat, with config.json)
│   │   ├── package_ota.py              ← OTA ZIP generator (folder-tree structure)
│   │   ├── registry.py                 ← JSON release registry (append, query, integrity)
│   │   ├── changelog.py                ← CHANGELOG.md generator from registry
│   │   ├── excel_export.py             ← release-tracker.xlsx generator (openpyxl)
│   │   └── utils.py                    ← SHA256, file copy, size formatting
│   └── tests/                          ← (placeholder for future tests)
└── example-bin-files-reference/        ← reference files showing expected ZIP structures
```

---

## Architecture & Data Flow

```
                    release-config.yaml
                           │
                           ▼
┌─────────────────────────────────────────────────┐
│  cli.py (main entry point)                       │
│                                                  │
│  1. Load config (config.py)                      │
│  2. Resolve project dirs (CLI > config > auto)   │
│  3. Scan files (scanner.py)                      │
│  4. Extract versions (version_extractor.py)      │
│  5. Prompt user for release version & notes      │
│  6. Generate FLASH ZIP (package_rpi.py)          │
│  7. Generate OTA ZIP (package_ota.py)            │
│  8. Copy HMI .tft to release folder              │
│  9. Update registry (registry.py)                │
│  10. Regenerate changelog (changelog.py)         │
│  11. Regenerate Excel (excel_export.py)          │
└─────────────────────────────────────────────────┘
                           │
                           ▼
            releases/<PRODUCT>-V<ver>/
            ├── <PRODUCT>-FW-FLASH-V<ver>.zip
            ├── <PRODUCT>-FW-OTA-V<ver>.zip
            └── <HMI>.tft
            releases/<PRODUCT>-release-registry.json
            releases/<PRODUCT>-CHANGELOG.md
            releases/<PRODUCT>-release-tracker.xlsx
```

---

## Module Reference

### cli.py — CLI Entry Point
- **Framework:** Typer + Rich (panels, tables, progress bars)
- **Subcommands:**
  - `apts-release` (default) — full packaging flow
  - `apts-release history` — display past releases in terminal table
  - `apts-release export` — regenerate Excel + changelog from registry
  - `apts-release publish [VERSION]` — upload release to GitHub Releases
- **Project dir resolution:** `_resolve_project_dirs()` — 3-tier: CLI flags > config > auto-detect `*_ESP32_FW`/`*_STM32_FW`
- **Version extraction:** `_extract_versions()` — pulls from CMake, C headers, text files, HMI filenames
- **Safety:** duplicate version check, overwrite confirmation, pre-flight writable check

### config.py — Configuration
- **Dataclass:** `ProjectConfig` with all configurable fields
- **Loader:** `load_config(Path)` — parses `release-config.yaml`
- **Finder:** `find_config_file(Path)` — searches upward from cwd (max 10 levels)
- **Key fields:** `product_name`, `board`, `esp32_project_dir`, `stm32_project_dir`, `release_name`, `released_by`, `github_repo`

### scanner.py — File Discovery
- **ESP32 files:** bootloader, partition-table, ota_data_initial, app_firmware (auto-detected), webpage_1, cdn
- **STM32 files:** single .bin from build dir (picks largest if multiple)
- **HMI:** scans `HMI/` dir at firmware root for `.tft` files (optional, version tracking only)
- **Returns:** `FileManifest` with `esp32_files`, `stm32_files`, `missing` lists

### version_extractor.py — Version Parsing
- `extract_cmake_project_ver()` — regex: `set(PROJECT_VER "x.y.z")`
- `extract_define_version()` — regex: `#define NAME "x.y.z"`
- `extract_version_from_file()` — plain text file contents
- `extract_hmi_version()` — regex from filename: `*-V1.6.7.tft`
- `auto_release_version()` — patch bump from previous (1.0.2 → 1.0.3)

### package_rpi.py — FLASH Package
- **Output:** `<PRODUCT>-FW-FLASH-V<release>.zip`
- **Structure:** flat ZIP with renamed files + `config.json` for RPI programmer
- **Flash map:** bootloader@0x1000, partition@0x8000, ota_data@0xD000, app@0x10000, webpage@0x410000, cdn@0x510000, STM32@0x08000000
- **config.json:** contains machine_id, flash addresses, chip type, baud rates

### package_ota.py — OTA Package
- **Output:** `<PRODUCT>-FW-OTA-V<release>.zip`
- **Structure:** folder-tree: `CORE-FIRMWARE/`, `WIFI-FIRMWARE/`, `WEBPAGE/`
- **HMI .tft is NOT included in ZIP** — only version tracked in registry

### registry.py — Release Registry
- **Format:** JSON with `schema_version` and `releases[]` array
- **Release ID:** `REL-YYYY-NNNN` (sequential per year)
- **Entry fields:** id, timestamp, product, release_name, board, release_version, components (with SHA256), packages, notes, released_by
- **Corruption recovery:** backs up as `.json.bak` on parse failure
- **Key functions:** `append_release()`, `get_releases()`, `has_release_version()`, `get_latest_release_version()`

### excel_export.py — Excel Tracker
- **Sheet 1:** "All Releases" — full table with all fields (newest first)
- **Sheet 2:** "Product Summary" — per-product stats
- **Columns:** Release ID, Date, Product, Release Name, Release Version, ESP32/STM32/WebUI/HMI versions, package names, sizes, notes, released by
- **Styling:** header fill, alternating row colors, frozen header row, word-wrap on Notes

### changelog.py — Changelog Generator
- **Output:** Markdown newest-first, with component version tables and package lists
- **Source:** always regenerated from registry (not manually edited)

---

## release-config.yaml — Full Reference

```yaml
product:
  name: HSC-TUBE-CUTTER              # product identifier (used in filenames, registry)
  board: APTS-IOT-V2-2               # board name (default: APTS-IOT-V2-2)

projects:
  esp32_dir: HST_ESP32_FW            # ESP32 project folder (relative to config file)
  stm32_dir: HST_STM32_FW            # STM32 project folder (relative to config file)

esp32:
  build_dir: build                    # ESP-IDF build output dir (default: build)
  version:
    file: CMakeLists.txt              # file containing PROJECT_VER
  webpage_version:
    file: Webserver/data/Version.txt  # plain text version file

stm32:
  build_dir: Debug                    # STM32CubeIDE build config (default: Debug)
  version:
    file: Core/Inc/display/display_task.h
    define: STM_FIRMWARE_VERSION      # #define name to extract version from
  hmi_dir: HMI                        # HMI .tft folder at firmware root

release:
  name: HSC Tube Cutting Machine      # human-friendly name (shown in tracker, changelog, GitHub)
  released_by: Siva                   # your name (falls back to OS username if empty)
  output_dir: ./releases              # output directory for all release artifacts

github:
  repo: APTS-Engineering/apts-hsc-tube-cutter-releases   # GitHub repo (one per machine)
```

---

## Output Structure

```
releases/
├── <PRODUCT>-release-registry.json     ← source of truth (never delete)
├── <PRODUCT>-CHANGELOG.md              ← auto-generated
├── <PRODUCT>-release-tracker.xlsx      ← auto-generated
├── <PRODUCT>-V1.0.0/                   ← versioned release folder
│   ├── <PRODUCT>-FW-FLASH-V1.0.0.zip
│   ├── <PRODUCT>-FW-OTA-V1.0.0.zip
│   └── HSC-HMI-V1.6.7.tft
├── <PRODUCT>-V1.0.1/
│   ├── <PRODUCT>-FW-FLASH-V1.0.1.zip
│   ├── <PRODUCT>-FW-OTA-V1.0.1.zip
│   └── HSC-HMI-V1.6.7.tft
└── ...
```

---

## GitHub Publishing

- **Strategy:** one GitHub repo per machine (avoids clutter with 5-6 machines × many releases)
- **Naming:** `APTS-Engineering/apts-<machine>-releases`
- **Tags:** just the version (`V1.0.0`), no product prefix (repo is already machine-specific)
- **Assets uploaded:** FLASH ZIP, OTA ZIP, HMI .tft, release-tracker.xlsx, CHANGELOG.md
- **Release body:** auto-generated markdown with component version table, asset descriptions
- **Requires:** GitHub CLI (`gh`) installed and authenticated (`gh auth login`)
- **Command:** `apts-release publish` (latest) or `apts-release publish 1.0.2` (specific version)

---

## Installation

### Prerequisites
- Python 3.10+ (tested on 3.14)
- pip

### Install (editable/dev mode)
```bash
cd apts-release
pip install -e .
```

### Install (from git for team members)
```bash
pip install git+https://github.com/APTS-Engineering/apts-release-tool.git#subdirectory=apts-release
```

### Install (from local wheel)
```bash
cd apts-release
pip install .
```

### Verify
```bash
apts-release --version
```

### PATH issue (Windows)
If `apts-release` is not found, add the Python Scripts dir to PATH:
```powershell
$scriptsDir = python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"
[Environment]::SetEnvironmentVariable("Path", "$env:Path;$scriptsDir", "User")
```
Then restart your terminal.

### For GitHub publishing (optional)
```bash
winget install GitHub.cli
gh auth login
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| typer | >=0.9.0 | CLI framework (commands, options, prompts) |
| rich | >=13.0.0 | Terminal UI (panels, tables, progress bars) |
| questionary | >=2.0.0 | Interactive prompts (unused currently, kept for future) |
| pyyaml | >=6.0 | YAML config file parsing |
| openpyxl | >=3.1.0 | Excel .xlsx generation |

---

## Key Design Decisions

1. **Registry is source of truth** — changelog and Excel are always regenerated from it, never the reverse
2. **Product-named files** — all tracker files include product name to avoid conflicts when downloading from multiple machines
3. **HMI not in ZIP** — HMI .tft is copied to the release folder but NOT included in FLASH or OTA ZIPs (version tracked in registry only)
4. **Release version is independent** — auto-incremented patch version, separate from component versions (ESP32/STM32 may stay at 1.0.0 while release bumps to 1.0.5)
5. **Three-tier project resolution** — CLI > config > auto-detect, so tool works with zero flags if config exists
6. **Per-machine GitHub repos** — keeps releases page clean, production teams subscribe to only their machine
7. **Corruption recovery** — corrupted registry JSON is backed up as .bak and tool starts fresh

---

## Adding a New Machine

1. Create the firmware project folder structure:
   ```
   XXX_Machine/01_Software/XXX_APTS_PCB_FW/
   ├── XXX_ESP32_FW/
   ├── XXX_STM32_FW/
   ├── HMI/
   └── release-config.yaml
   ```

2. Copy and edit `release-config.yaml`:
   ```yaml
   product:
     name: SMART-PRESS              # change this
   projects:
     esp32_dir: SMP_ESP32_FW        # change this
     stm32_dir: SMP_STM32_FW        # change this
   release:
     name: Smart Crimping Press     # change this
     released_by: YourName
   github:
     repo: APTS-Engineering/apts-smart-press-releases
   ```

3. Create the GitHub repo:
   ```bash
   gh repo create APTS-Engineering/apts-smart-press-releases --public --description "Smart Press firmware releases"
   gh api repos/APTS-Engineering/apts-smart-press-releases/contents/README.md -X PUT -f message="init" -f content="IyBTbWFydCBQcmVzcyBSZWxlYXNlcwo="
   ```

4. Build firmware, then run:
   ```bash
   cd XXX_APTS_PCB_FW
   apts-release
   apts-release publish
   ```

---

## Typical Workflow

```
1. Build ESP32:       idf.py build
2. Build STM32:       Build in STM32CubeIDE (Debug config)
3. Copy HMI .tft:     Place latest .tft in HMI/ folder
4. Package release:   cd XXX_APTS_PCB_FW && apts-release
5. Review output:     Check releases/<PRODUCT>-V<ver>/ folder
6. Publish:           apts-release publish
7. View history:      apts-release history
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `apts-release: command not found` | Add Python Scripts dir to PATH (see Installation section) |
| `ESP32 build directory not found` | Run `idf.py build` first in the ESP32 project |
| `STM32 firmware .bin not found` | Build in STM32CubeIDE (Debug configuration) |
| `No release-config.yaml found` | Create one or use `--esp32`/`--stm32`/`--product` flags |
| `Registry JSON is corrupted` | Tool auto-recovers (backs up as .bak, starts fresh) |
| `GitHub CLI (gh) not found` | `winget install GitHub.cli` then `gh auth login` |
| `Repository is empty` (GitHub publish) | Initialize repo with a README first (see "Adding a New Machine") |
| `Tag already exists` (GitHub publish) | Delete old release: `gh release delete V1.0.0 --repo ORG/REPO --yes` |
