"""Project configuration — YAML loading with defaults."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class VersionSource:
    """Where to find a version string."""

    file: str  # relative path from project root
    define: str | None = None  # #define name (None = read file contents)


@dataclass
class ProjectConfig:
    """Complete tool configuration, loaded from YAML or defaults."""

    product_name: str = "UNKNOWN"
    board: str = "APTS-IOT-V2-2"

    # Project directory names (relative to config file or workspace root)
    esp32_project_dir: str | None = None
    stm32_project_dir: str | None = None

    esp32_build_dir: str = "build"
    esp32_version: VersionSource = field(
        default_factory=lambda: VersionSource(file="CMakeLists.txt")
    )
    esp32_webpage_version: VersionSource = field(
        default_factory=lambda: VersionSource(file="Webserver/data/Version.txt")
    )

    stm32_build_dir: str = "Debug"
    stm32_version: VersionSource = field(
        default_factory=lambda: VersionSource(
            file="Core/Inc/display/display_task.h",
            define="STM_FIRMWARE_VERSION",
        )
    )
    hmi_dir: str = "HMI"

    release_name: str = ""  # human-friendly name, e.g. "HSC Tube Cutting Machine"
    released_by: str = ""  # person name, falls back to OS username if empty
    output_dir: str = "./releases"
    registry_path: str = "./releases/release-registry.json"
    changelog_path: str = "./releases/CHANGELOG.md"
    excel_path: str = "./releases/release-tracker.xlsx"

    github_repo: str | None = None  # e.g. "MyOrg/apts-firmware-releases"


def load_config(config_path: Path | None = None) -> ProjectConfig:
    """Load config from YAML file, or return defaults if not found."""
    cfg = ProjectConfig()

    if config_path is None or not config_path.is_file():
        return cfg

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Product
    product = data.get("product", {})
    if product.get("name"):
        cfg.product_name = product["name"]
    if product.get("board"):
        cfg.board = product["board"]

    # Project directories
    projects = data.get("projects", {})
    if projects.get("esp32_dir"):
        cfg.esp32_project_dir = projects["esp32_dir"]
    if projects.get("stm32_dir"):
        cfg.stm32_project_dir = projects["stm32_dir"]

    # ESP32
    esp = data.get("esp32", {})
    if esp.get("build_dir"):
        cfg.esp32_build_dir = esp["build_dir"]
    ver = esp.get("version", {})
    if ver.get("file"):
        cfg.esp32_version = VersionSource(
            file=ver["file"],
            define=ver.get("define"),
        )
    web_ver = esp.get("webpage_version", {})
    if web_ver.get("file"):
        cfg.esp32_webpage_version = VersionSource(
            file=web_ver["file"],
            define=web_ver.get("define"),
        )

    # STM32
    stm = data.get("stm32", {})
    if stm.get("build_dir"):
        cfg.stm32_build_dir = stm["build_dir"]
    ver = stm.get("version", {})
    if ver.get("file"):
        cfg.stm32_version = VersionSource(
            file=ver["file"],
            define=ver.get("define"),
        )
    if stm.get("hmi_dir"):
        cfg.hmi_dir = stm["hmi_dir"]

    # Release paths
    rel = data.get("release", {})
    if rel.get("name"):
        cfg.release_name = rel["name"]
    if rel.get("released_by"):
        cfg.released_by = rel["released_by"]
    if rel.get("output_dir"):
        cfg.output_dir = rel["output_dir"]
    if rel.get("registry"):
        cfg.registry_path = rel["registry"]
    if rel.get("changelog"):
        cfg.changelog_path = rel["changelog"]
    if rel.get("excel"):
        cfg.excel_path = rel["excel"]

    # GitHub
    gh = data.get("github", {})
    if gh.get("repo"):
        cfg.github_repo = gh["repo"]

    return cfg


def find_config_file(start_dir: Path) -> Path | None:
    """Search for release-config.yaml starting from start_dir upward."""
    current = start_dir.resolve()
    for _ in range(10):  # limit upward search
        candidate = current / "release-config.yaml"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
