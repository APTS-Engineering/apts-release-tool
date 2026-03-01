# Claude Code Briefing — APTS-IOT Firmware Release Tool

> **Read this document FIRST before reading APTS-RELEASE-TOOL-PLAN.md**
> **This document explains the intent, context, and how you should work with the developer.**

---

## Who You Are Working With

You are working with **Siva**, a firmware/hardware engineer at **APTS Engineering / Competent Crimping Machinery Pvt. Ltd**. He designs industrial automation systems built around a custom dual-controller PCB called the **APTS-IOT-V2-2**. This board has an STM32H723 (real-time machine control) and an ESP32 (WiFi, OTA updates, web server).

Siva is highly technical in embedded systems, C firmware, and hardware design. He is comfortable with Python but this tool is outside his daily workflow — he needs you to own the implementation. He will guide you on firmware-specific details (version locations, file names, config formats) that only he knows.

---

## What Problem We Are Solving

Every time Siva finishes a firmware build cycle, he has to manually:

1. Collect 7-8 `.bin` files scattered across two separate build directories (ESP32 and STM32)
2. Rename them according to specific naming conventions
3. Organize them into different folder structures depending on the target audience
4. Create a JSON config file with flash memory addresses
5. ZIP everything with version-stamped filenames
6. Do this for TWO different package formats (RPI flash programmer + OTA customer update)
7. Update a changelog
8. Track which versions were released when, for which product, in a format he can share with manufacturing and management

This is tedious, error-prone, and happens every release. The tool automates all of it into a single terminal command.

---

## What You Are Building

A Python CLI tool called `apts-release` that:

- Asks for (or accepts as arguments) the ESP32 and STM32 project folder paths
- Finds all the `.bin` files automatically
- Reads firmware version numbers from C source code `#define` statements
- Prompts for a one-line release note
- Generates two ZIP packages with correct structure, naming, and config
- Records the release in a JSON registry (the source of truth for all releases)
- Generates a formatted Excel spreadsheet from the registry (for sharing with teams)
- Generates a CHANGELOG.md from the registry (for developer reference)

The tool also has two utility subcommands:
- `apts-release history` — Display past releases in a rich terminal table
- `apts-release export` — Regenerate the Excel and Changelog from the registry (useful after manual edits to the JSON)

---

## The Release Tracking Architecture (Important — Understand This)

This is the key design decision in the tool. There are three output files that track releases:

```
release-registry.json  ──→  CHANGELOG.md
        │
        └──────────────→  release-tracker.xlsx
```

**`release-registry.json`** is the SINGLE SOURCE OF TRUTH. Every time the tool runs, it appends one new entry to this JSON file. This file is append-only — entries are never deleted or modified by the tool.

**`CHANGELOG.md`** is DERIVED from the registry. Every time the tool runs, it regenerates this file completely by iterating over all entries in the registry. If Siva manually edits the JSON (e.g., fixes a typo in notes), he can run `apts-release export` to regenerate the changelog.

**`release-tracker.xlsx`** is also DERIVED from the registry. Same regeneration logic. This Excel file is what gets shared with the manufacturing team and management — it has formatted headers, alternating row colors, frozen header row, and a product summary sheet.

The reason for this architecture: the JSON is easy for the tool to read/write programmatically, the changelog is easy for developers to skim in a repo, and the Excel is easy for non-technical people to filter and print. All three stay in sync because they come from one source.

---

## What You Should NOT Do

- **Do NOT build a web UI, GUI, or dashboard.** This is a terminal-only CLI tool.
- **Do NOT add Git integration, CI/CD hooks, or deployment features.** Those are future scope.
- **Do NOT over-engineer.** No plugin systems, no abstract factory patterns, no database. Simple Python modules that do one thing each.
- **Do NOT guess firmware details.** When you encounter something you're unsure about (version define names, config file format, bin file locations), STOP and ask Siva. He will tell you exactly what to look for.
- **Do NOT hardcode paths or version strings.** Everything should come from the project scan or the `release-config.yaml`.
- **Do NOT manually edit CHANGELOG.md or the Excel file.** Always generate them from the registry. If something needs to change, change the registry JSON and regenerate.

---

## How To Work With The Plan Document

The file `APTS-RELEASE-TOOL-PLAN.md` is your detailed technical specification. It contains:

| Section | What It Tells You |
|---------|-------------------|
| Section 2 | Hardware context — understand what ESP32 and STM32 build outputs look like |
| Section 3 | How to extract firmware versions from C header files |
| Section 4 | **Exact file structure** for each ZIP package — follow these tables precisely |
| Section 5 | **Release tracking system** — registry JSON schema, Excel format specs, changelog format, data flow architecture |
| Section 6 | Code architecture — module layout and responsibilities |
| Section 7 | Python dependencies to install |
| Section 8 | Default config values when no YAML config exists |
| Section 9 | Error handling — what to check before packaging |
| Section 11 | **Build order** — follow this phase sequence |
| Appendix A | Quick reference for file naming in each package |
| Appendix B | Sample YAML config file |
| Appendix C | Sample registry JSON with two releases showing multi-product support |

**IMPORTANT:** Some details in the plan document are marked as assumptions (noted with phrases like "VERIFY", "IMPORTANT FOR CLAUDE CODE", or "assumed format"). These are places where you MUST ask Siva before proceeding.

---

## The 5 Things You Must Ask Siva Before Writing Package Logic

These are non-negotiable. Do not skip them.

### 1. Version Define Discovery
Before implementing version extraction, scan the actual project folders:

```bash
# Run these in the ESP32 project
grep -rn "VERSION\|FW_VER\|APP_VER" --include="*.h" --include="*.c" main/ components/

# Run these in the STM32 project
grep -rn "VERSION\|FW_VER\|APP_VER" --include="*.h" Core/Inc/
```

Show Siva the results and ask: **"Which of these defines represent the firmware versions I should extract?"**

### 2. RPI Config File Format
The RPI flash programmer reads a `config` JSON file. The plan document has a guessed structure. Ask Siva: **"Can you show me an existing config file from a previous RPI flash package, or describe exactly what fields your RPI programmer expects?"**

Do NOT generate the config file until you know the exact schema.

### 3. Main Firmware Binary Names
The ESP32 build produces a main `.bin` file whose name comes from the CMakeLists.txt project name. The STM32 build produces a `.bin` in Release/. Ask Siva: **"What is the exact filename of the main .bin file in your ESP32 build/ directory and STM32 Release/ directory?"**

### 4. Flash Offsets
The plan lists ESP32 flash offsets (0x1000, 0x8000, 0x10000, etc.) based on common ESP-IDF defaults. These must match the actual `partitions.csv`. Ask Siva: **"Can you confirm the flash offsets, or point me to your partitions.csv file so I can parse it?"**

### 5. Release Version Convention
The OTA package has an overall release version (like V2.1.2) that's separate from individual component versions. Ask Siva: **"How do you decide the overall release version number? Is it in a file somewhere, or do you choose it manually each time?"**

---

## Implementation Approach

### Step 1: Scaffold First, Verify It Runs

Create the project structure, `pyproject.toml`, and a bare CLI that prints a welcome banner. Install it with `pip install -e .` and verify `apts-release` works from the terminal. Show Siva.

### Step 2: Point at Real Project Folders, Discover Everything

Once Siva gives you the ESP32 and STM32 project paths:
- List the build directory contents
- Find all `.bin` files
- Search for version defines
- Show Siva what you found and confirm before proceeding

### Step 3: Build Packaging One at a Time

Build the RPI package generator first (it's simpler — flat ZIP). Get Siva to verify the output ZIP matches what the RPI programmer expects. Then build the OTA package generator.

### Step 4: Build Release Tracking

Once both packages generate correctly:
- Implement the JSON registry (append new entries, generate IDs)
- Implement changelog generation (read registry, write markdown)
- Implement Excel generation (read registry, write formatted xlsx with openpyxl)
- Wire all three into the CLI flow so they happen automatically after packaging

### Step 5: Wire Up the Interactive UI and Subcommands

Add the Rich panels, tables, and progress bars. Add the `history` and `export` subcommands. The logic should work correctly before you make it pretty.

---

## Code Style Guidelines

- **Python 3.10+** with type hints on all function signatures
- **Pathlib** for all file path operations (no `os.path.join`)
- **Dataclasses** for structured data (VersionInfo, FileManifest, PackageResult)
- **f-strings** for string formatting
- **No classes where functions suffice.** The scanner, version extractor, and packagers can be modules with plain functions. Only use classes for data containers.
- **Docstrings** on every public function (one-liner is fine)
- **No print() statements.** Use `rich.console.Console` for all output so formatting is consistent.
- Keep functions short. If a function exceeds 40 lines, split it.

---

## File Organization Reminder

```
apts-release/
├── pyproject.toml              # Package metadata + CLI entry point
├── README.md                   # Usage instructions
├── src/
│   └── apts_release/
│       ├── __init__.py         # Package version
│       ├── cli.py              # Typer app, commands, Rich UI
│       ├── config.py           # YAML loading, defaults
│       ├── scanner.py          # Find bin files in project dirs
│       ├── version_extractor.py # Parse #define versions from headers
│       ├── package_rpi.py      # Generate RPI flash ZIP
│       ├── package_ota.py      # Generate OTA ZIP
│       ├── registry.py         # JSON release registry (read/append/query)
│       ├── changelog.py        # Generate CHANGELOG.md from registry
│       ├── excel_export.py     # Generate release-tracker.xlsx from registry
│       └── utils.py            # File ops, hashing, formatting
└── tests/
    └── ...
```

---

## Success Criteria

The tool is done when Siva can:

1. Run `apts-release` from his terminal
2. Point it at his ESP32 and STM32 project folders
3. See all detected files and versions displayed clearly
4. Enter a one-line release note when prompted
5. Confirm, and get two ZIP files generated in seconds
6. Open the RPI ZIP and see it matches the structure in Image 1 of the plan (flat, with `esp32_` prefixes and config JSON)
7. Open the OTA ZIP and see it matches the OTA tree structure (CORE-FIRMWARE/, HMI/, WEBPAGE/, WIFI-FIRMWARE/ folders with versioned files)
8. See `release-registry.json` updated with the new release entry (including SHA256 hashes, file sizes, component versions, release notes, and release ID)
9. Open `release-tracker.xlsx` and see a formatted table with all releases — headers frozen, alternating row colors, sizes in human-readable format, filterable by product
10. See `CHANGELOG.md` regenerated with the new release at the top
11. Run `apts-release history` and see a Rich table of all past releases in the terminal
12. Run `apts-release export` and see the Excel and Changelog regenerated from the registry

If all 12 points work, V1 is complete.

---

## Context Files Available

Siva has the following reference documents that may help you understand the hardware:

- **APTS_IOT_V2_2_HARDWARE_REFERENCE.md** — Complete PCB hardware reference with pin maps, partition tables, memory maps, and peripheral assignments. Read this if you need to understand the board architecture, flash layout, or inter-controller communication.

- **DSY-RS_Series_Low_Voltage_Servo_Drive_User_manual__V1_0_.pdf** — Servo drive manual. NOT relevant to this tool. Ignore unless Siva specifically brings it up.

---

## Summary

You are building a straightforward CLI packaging tool with a release tracking system. The hardest part is not the code — it's getting the firmware-specific details right (version locations, config format, file names). Always ask before assuming. Build incrementally. Verify each step with Siva. Keep it simple.

The release tracking system (registry → changelog + Excel) is the most valuable long-term feature. Get the JSON schema right from the start, because everything else is derived from it.

---

*End of Briefing Document*
