"""File discovery — scans ESP32 and STM32 project directories for bin files."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileEntry:
    """A single discovered file with its metadata."""

    logical_name: str
    path: Path
    size_bytes: int
    required: bool = True


@dataclass
class FileManifest:
    """All discovered files from both projects."""

    esp32_files: dict[str, FileEntry] = field(default_factory=dict)
    stm32_files: dict[str, FileEntry] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def all_found(self) -> bool:
        """True if no required files are missing."""
        return len(self.missing) == 0


# ESP32 bin file locations relative to the build directory
ESP32_FILE_MAP: dict[str, str] = {
    "bootloader": "bootloader/bootloader.bin",
    "partition_table": "partition_table/partition-table.bin",
    "ota_data_initial": "ota_data_initial.bin",
    "app_firmware": None,  # resolved dynamically from project name
    "webpage_1": "webpage_1.bin",
    "cdn": "cdn.bin",
}


def _find_esp32_app_firmware(build_dir: Path) -> Path | None:
    """Find the main ESP32 application .bin in the build directory."""
    # Look for a .bin file matching the project directory name pattern
    # ESP-IDF names it after the project: HST_ESP32_FW.bin, etc.
    candidates = [
        f
        for f in build_dir.glob("*.bin")
        if f.name not in ("webpage_1.bin", "cdn.bin", "ota_data_initial.bin")
        and "CMake" not in str(f)
    ]
    if len(candidates) == 1:
        return candidates[0]
    # If multiple, pick the largest (the app binary is always the biggest)
    if candidates:
        return max(candidates, key=lambda f: f.stat().st_size)
    return None


def scan_esp32(project_dir: Path, build_subdir: str = "build") -> tuple[dict[str, FileEntry], list[str]]:
    """Scan ESP32 project for required bin files."""
    build_dir = project_dir / build_subdir
    files: dict[str, FileEntry] = {}
    missing: list[str] = []

    if not build_dir.is_dir():
        missing.append(f"ESP32 build directory not found: {build_dir}")
        return files, missing

    for name, rel_path in ESP32_FILE_MAP.items():
        if name == "app_firmware":
            path = _find_esp32_app_firmware(build_dir)
            if path is None:
                missing.append("ESP32 app firmware .bin (main application)")
                continue
        else:
            path = build_dir / rel_path

        if path.is_file():
            files[name] = FileEntry(
                logical_name=name,
                path=path,
                size_bytes=path.stat().st_size,
            )
        else:
            missing.append(f"ESP32 {name}: {path}")

    return files, missing


def scan_stm32(
    project_dir: Path,
    build_subdir: str = "Debug",
) -> tuple[dict[str, FileEntry], list[str]]:
    """Scan STM32 project for firmware bin."""
    build_dir = project_dir / build_subdir
    files: dict[str, FileEntry] = {}
    missing: list[str] = []

    if not build_dir.is_dir():
        missing.append(f"STM32 build directory not found: {build_dir}")
        return files, missing

    # Find the .bin in build dir (should be exactly one)
    bin_files = list(build_dir.glob("*.bin"))
    if len(bin_files) == 1:
        path = bin_files[0]
        files["firmware"] = FileEntry(
            logical_name="firmware",
            path=path,
            size_bytes=path.stat().st_size,
        )
    elif len(bin_files) > 1:
        # Pick the largest
        path = max(bin_files, key=lambda f: f.stat().st_size)
        files["firmware"] = FileEntry(
            logical_name="firmware",
            path=path,
            size_bytes=path.stat().st_size,
        )
    else:
        missing.append(f"STM32 firmware .bin in {build_dir}")

    return files, missing


def scan_hmi(hmi_dir: Path) -> FileEntry | None:
    """Scan for HMI .tft file in the given directory (optional, version tracking only)."""
    if not hmi_dir.is_dir():
        return None
    tft_files = list(hmi_dir.glob("*.tft"))
    if len(tft_files) == 1:
        path = tft_files[0]
    elif len(tft_files) > 1:
        path = max(tft_files, key=lambda f: f.stat().st_mtime)
    else:
        return None
    return FileEntry(
        logical_name="hmi",
        path=path,
        size_bytes=path.stat().st_size,
        required=False,
    )


def scan_projects(
    esp32_dir: Path,
    stm32_dir: Path,
    esp32_build_subdir: str = "build",
    stm32_build_subdir: str = "Debug",
    hmi_subdir: str = "HMI",
) -> FileManifest:
    """Scan both projects and return a combined manifest."""
    esp32_files, esp32_missing = scan_esp32(esp32_dir, esp32_build_subdir)
    stm32_files, stm32_missing = scan_stm32(stm32_dir, stm32_build_subdir)

    # HMI: scan from firmware root (parent of ESP32/STM32 projects)
    firmware_root = esp32_dir.parent
    hmi_entry = scan_hmi(firmware_root / hmi_subdir)
    if hmi_entry:
        stm32_files["hmi"] = hmi_entry

    return FileManifest(
        esp32_files=esp32_files,
        stm32_files=stm32_files,
        missing=esp32_missing + stm32_missing,
    )
