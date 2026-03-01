"""Changelog generation — generates CHANGELOG.md from the release registry."""

from pathlib import Path

from apts_release.registry import load_registry
from apts_release.utils import format_size


def generate_changelog(registry_path: Path, output_path: Path) -> int:
    """Regenerate CHANGELOG.md from the registry. Returns number of entries written."""
    registry = load_registry(registry_path)
    releases = registry.get("releases", [])

    lines: list[str] = [
        "# APTS-IOT Firmware Release Changelog",
        "",
        "> Auto-generated from release-registry.json. Do not edit manually.",
        "",
        "---",
        "",
    ]

    # Newest first
    for release in reversed(releases):
        rel_ver = release.get("release_version", "?")
        ts = release.get("timestamp", "")[:10]
        # Format date as DD-MM-YYYY
        if len(ts) == 10 and ts[4] == "-":
            date_str = f"{ts[8:10]}-{ts[5:7]}-{ts[0:4]}"
        else:
            date_str = ts
        product = release.get("product", "?")
        release_name = release.get("release_name", "")
        rel_id = release.get("id", "?")
        released_by = release.get("released_by", "?")

        heading = f"## [{rel_ver}] - {date_str} — {product}"
        if release_name:
            heading = f"## [{rel_ver}] - {date_str} — {release_name} ({product})"
        lines.append(heading)
        lines.append("")
        lines.append(f"**Release ID:** {rel_id}")
        lines.append(f"**Released by:** {released_by}")
        lines.append("")

        # Component version table
        components = release.get("components", {})
        lines.append("| Component | Version |")
        lines.append("|-----------|---------|")

        comp_labels = {
            "esp32_firmware": "ESP32 Firmware",
            "stm32_firmware": "STM32 Firmware",
            "webpage": "Web UI",
            "hmi": "HMI",
        }
        for key, label in comp_labels.items():
            comp = components.get(key)
            if comp:
                ver = comp.get("version") or "N/A"
                lines.append(f"| {label} | {ver} |")

        lines.append("")

        # Packages
        packages = release.get("packages", {})
        lines.append("**Packages:**")
        for pkg_type in ("rpi", "ota"):
            pkg = packages.get(pkg_type)
            if pkg:
                fname = pkg.get("filename", "?")
                size = format_size(pkg.get("size_bytes", 0))
                lines.append(f"- `{fname}` ({size})")

        lines.append("")

        # Notes
        notes = release.get("notes", "")
        if notes:
            lines.append(f"**Notes:** {notes}")
            lines.append("")

        lines.append("---")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(releases)
