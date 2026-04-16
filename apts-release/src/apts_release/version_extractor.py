"""Version extraction — parses versions from CMakeLists, C headers, text files, and filenames."""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VersionInfo:
    """Container for all extracted firmware version strings."""

    esp32_version: str
    stm32_version: str
    webpage_version: str
    hmi_version: str | None
    release_version: str  # auto-generated or user-supplied


def extract_cmake_project_ver(cmake_path: Path) -> str | None:
    """Extract PROJECT_VER from a CMakeLists.txt (e.g. set(PROJECT_VER "1.0.0"))."""
    pattern = r'set\s*\(\s*PROJECT_VER\s+"([^"]+)"\s*\)'
    content = cmake_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(pattern, content)
    return match.group(1) if match else None


def extract_define_version(header_path: Path, define_name: str) -> str | None:
    """Extract a version from a C #define — supports quoted strings and bare numbers.

    Matches:
      #define STM_FIRMWARE_VERSION "1.0.0"   -> "1.0.0"
      #define STM_FIRMWARE_VERSION 8.0f      -> "8.0"
      #define STM_FIRMWARE_VERSION 8.0       -> "8.0"
      #define STM_FIRMWARE_VERSION 3         -> "3.0"
    """
    content = header_path.read_text(encoding="utf-8", errors="replace")

    # Try quoted string first: #define NAME "x.y.z"
    quoted = rf'#define\s+{re.escape(define_name)}\s+"([^"]+)"'
    match = re.search(quoted, content)
    if match:
        return match.group(1)

    # Fall back to bare numeric: #define NAME 8.0f or #define NAME 8.0 or #define NAME 3
    bare = rf'#define\s+{re.escape(define_name)}\s+(\d+(?:\.\d+)*)f?'
    match = re.search(bare, content)
    if match:
        ver = match.group(1)
        # Ensure at least major.minor format
        if "." not in ver:
            ver += ".0"
        return ver

    return None


def extract_version_from_file(version_file: Path) -> str | None:
    """Read a plain-text version file (e.g. Version.txt containing '1.1.5')."""
    if not version_file.is_file():
        return None
    text = version_file.read_text(encoding="utf-8", errors="replace").strip()
    return text if text else None


def extract_hmi_version(tft_path: Path) -> str | None:
    """Extract version from an HMI .tft filename (e.g. SMP-HMI-V1.6.7.tft -> 1.6.7)."""
    pattern = r"[Vv](\d+\.\d+(?:\.\d+)?)"
    match = re.search(pattern, tft_path.name)
    return match.group(1) if match else None


def auto_release_version(previous_version: str | None) -> str:
    """Auto-increment patch version from previous release (e.g. '1.0.2' -> '1.0.3')."""
    if previous_version is None:
        return "1.0.0"
    # Strip leading V/v if present
    ver = previous_version.lstrip("Vv")
    parts = ver.split(".")
    if len(parts) < 3:
        parts.extend(["0"] * (3 - len(parts)))
    try:
        parts[2] = str(int(parts[2]) + 1)
    except ValueError:
        return "1.0.0"
    return ".".join(parts)
