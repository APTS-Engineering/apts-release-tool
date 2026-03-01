"""Release registry — JSON read/write/append for release tracking."""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from apts_release.scanner import FileManifest
from apts_release.utils import compute_sha256, format_size
from apts_release.version_extractor import VersionInfo
from apts_release.package_rpi import PackageResult

SCHEMA_VERSION = "1.0"


def load_registry(registry_path: Path) -> dict:
    """Load existing registry or create an empty one.

    If the JSON file is corrupted, backs it up as .json.bak and returns
    an empty registry so the caller can start fresh.
    """
    if registry_path.is_file():
        try:
            with open(registry_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "releases" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            # Corrupted JSON — back it up and warn
            bak_path = registry_path.with_suffix(".json.bak")
            shutil.copy2(registry_path, bak_path)
            print(
                f"WARNING: Registry JSON is corrupted. "
                f"Backed up to {bak_path.name}, starting fresh.",
                file=sys.stderr,
            )
    return {"schema_version": SCHEMA_VERSION, "releases": []}


def _save_registry(registry_path: Path, registry: dict) -> None:
    """Write registry to disk."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def generate_release_id(existing_releases: list[dict]) -> str:
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


def get_latest_release_version(registry_path: Path, product: str | None = None) -> str | None:
    """Get the release_version of the most recent release, optionally filtered by product."""
    registry = load_registry(registry_path)
    releases = registry.get("releases", [])
    if product:
        releases = [r for r in releases if r.get("product") == product]
    if not releases:
        return None
    return releases[-1].get("release_version")


def build_release_entry(
    product: str,
    board: str,
    release_version: str,
    versions: VersionInfo,
    manifest: FileManifest,
    package_results: dict[str, PackageResult],
    notes: str,
    released_by: str,
    release_name: str = "",
) -> dict:
    """Build a complete release entry dict ready for appending."""
    # Component entries with hashes from original source files
    components: dict[str, dict] = {}

    esp32_fw = manifest.esp32_files.get("app_firmware")
    if esp32_fw:
        components["esp32_firmware"] = {
            "version": f"V{versions.esp32_version}",
            "file": esp32_fw.path.name,
            "size_bytes": esp32_fw.size_bytes,
            "sha256": compute_sha256(esp32_fw.path),
        }

    stm32_fw = manifest.stm32_files.get("firmware")
    if stm32_fw:
        components["stm32_firmware"] = {
            "version": f"V{versions.stm32_version}",
            "file": stm32_fw.path.name,
            "size_bytes": stm32_fw.size_bytes,
            "sha256": compute_sha256(stm32_fw.path),
        }

    webpage = manifest.esp32_files.get("webpage_1")
    if webpage:
        components["webpage"] = {
            "version": f"V{versions.webpage_version}",
            "file": webpage.path.name,
            "size_bytes": webpage.size_bytes,
            "sha256": compute_sha256(webpage.path),
        }

    cdn = manifest.esp32_files.get("cdn")
    if cdn:
        components["cdn"] = {
            "version": None,
            "file": cdn.path.name,
            "size_bytes": cdn.size_bytes,
            "sha256": compute_sha256(cdn.path),
        }

    hmi = manifest.stm32_files.get("hmi")
    if hmi:
        components["hmi"] = {
            "version": f"V{versions.hmi_version}" if versions.hmi_version else None,
            "file": hmi.path.name,
            "size_bytes": hmi.size_bytes,
            "sha256": compute_sha256(hmi.path),
        }

    # Package entries
    packages: dict[str, dict] = {}
    for pkg_type, result in package_results.items():
        packages[pkg_type] = {
            "filename": result.zip_path.name,
            "size_bytes": result.size_bytes,
            "sha256": result.sha256,
        }

    return {
        "id": "",  # filled by append_release
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "product": product,
        "release_name": release_name,
        "board": board,
        "release_version": f"V{release_version}",
        "components": components,
        "packages": packages,
        "notes": notes,
        "released_by": released_by,
    }


def append_release(registry_path: Path, release_entry: dict) -> str:
    """Append a new release entry to the registry. Returns the generated release ID."""
    registry = load_registry(registry_path)
    release_id = generate_release_id(registry["releases"])
    release_entry["id"] = release_id
    registry["releases"].append(release_entry)
    _save_registry(registry_path, registry)
    return release_id


def has_release_version(registry_path: Path, product: str, release_version: str) -> bool:
    """Check if a release version already exists for a given product."""
    registry = load_registry(registry_path)
    normalised = release_version if release_version.startswith("V") else f"V{release_version}"
    return any(
        r.get("product") == product and r.get("release_version") == normalised
        for r in registry.get("releases", [])
    )


def get_releases(registry_path: Path, product: str | None = None) -> list[dict]:
    """Get all releases, optionally filtered by product name."""
    registry = load_registry(registry_path)
    releases = registry.get("releases", [])
    if product:
        releases = [r for r in releases if r.get("product") == product]
    return releases
