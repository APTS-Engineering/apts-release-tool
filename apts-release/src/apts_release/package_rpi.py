"""RPI flash package generator — flat ZIP with renamed files + config JSON."""

import json
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from apts_release.scanner import FileManifest
from apts_release.utils import compute_sha256, safe_copy, ensure_dir
from apts_release.version_extractor import VersionInfo


@dataclass
class PackageResult:
    """Result of generating a package."""

    zip_path: Path
    size_bytes: int
    sha256: str


# Flash offsets for the RPI config (derived from partitions.csv)
ESP32_FLASH_MAP: list[dict[str, str]] = [
    {
        "logical": "bootloader",
        "address": "0x1000",
        "zip_name": "esp32_bootloader.bin",
        "description": "ESP32 second-stage bootloader",
    },
    {
        "logical": "partition_table",
        "address": "0x8000",
        "zip_name": "esp32_partition-table.bin",
        "description": "Partition table defining flash layout",
    },
    {
        "logical": "ota_data_initial",
        "address": "0xd000",
        "zip_name": "esp32_ota_data_initial.bin",
        "description": "OTA data partition for firmware updates",
    },
    {
        "logical": "app_firmware",
        "address": "0x10000",
        "zip_name": None,  # built dynamically: esp32_<PRODUCT>-V<ver>.bin
        "description": "Main application firmware",
    },
    {
        "logical": "webpage_1",
        "address": "0x410000",
        "zip_name": "esp32_webpage_1.bin",
        "description": "Web interface files (HTML, CSS, JS)",
    },
    {
        "logical": "cdn",
        "address": "0x510000",
        "zip_name": "esp32_cdn.bin",
        "description": "CDN resources (libraries, assets)",
    },
]


def _build_app_firmware_name(product_name: str, esp32_version: str) -> str:
    """Build the renamed ESP32 app firmware filename for the RPI package."""
    ver_clean = esp32_version.replace(".", "-")
    return f"esp32_{product_name}-V{ver_clean}.bin"


def _generate_config_json(
    product_name: str,
    esp32_version: str,
    stm32_version: str,
    app_fw_zip_name: str,
    machine_description: str,
) -> dict:
    """Generate the RPI programmer config.json matching the reference format."""
    firmware_files = []
    for entry in ESP32_FLASH_MAP:
        zip_name = entry["zip_name"] if entry["zip_name"] else app_fw_zip_name
        firmware_files.append({
            "file": zip_name,
            "address": entry["address"],
            "description": entry["description"],
        })

    return {
        "machine_id": product_name,
        "version": esp32_version,
        "description": f"{product_name} Machine - ESP32 + STM32 Control System",
        "esp32": {
            "enabled": True,
            "uart_port": None,
            "baud_rate": 115200,
            "flash_baud_rate": 921600,
            "firmware_files": firmware_files,
            "verification_message": "STM32 Enabled",
            "verification_timeout": 40,
        },
        "stm32": {
            "enabled": True,
            "chip_type": "stm32h723xx",
            "firmware_file": "stm32_firmware.bin",
            "flash_start_address": "0x08000000",
            "description": "STM32H723 motor/press controller firmware",
        },
        "options": {
            "auto_erase": False,
            "verify_after_flash": True,
            "log_level": "INFO",
        },
        "metadata": {
            "created_date": datetime.now().strftime("%Y-%m-%d"),
            "author": "Engineering Team",
            "machine_type": product_name,
            "notes": "Includes web interface and OTA update capability",
        },
    }


def generate_rpi_package(
    manifest: FileManifest,
    versions: VersionInfo,
    product_name: str,
    output_dir: Path,
) -> PackageResult:
    """Generate the RPI flash programmer ZIP package."""
    ensure_dir(output_dir)

    # ZIP filename: <PRODUCT>-FW-FLASH-V<release>.zip
    zip_name = f"{product_name}-FW-FLASH-V{versions.release_version}.zip"
    zip_path = output_dir / zip_name

    # App firmware name inside the ZIP
    app_fw_zip_name = _build_app_firmware_name(product_name, versions.esp32_version)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # Copy ESP32 files with renames
        for entry in ESP32_FLASH_MAP:
            logical = entry["logical"]
            file_entry = manifest.esp32_files.get(logical)
            if file_entry is None:
                continue
            if logical == "app_firmware":
                dst_name = app_fw_zip_name
            else:
                dst_name = entry["zip_name"]
            safe_copy(file_entry.path, tmp_dir / dst_name)

        # Copy STM32 firmware
        stm32_fw = manifest.stm32_files.get("firmware")
        if stm32_fw:
            safe_copy(stm32_fw.path, tmp_dir / "stm32_firmware.bin")

        # Generate config.json
        config = _generate_config_json(
            product_name=product_name,
            esp32_version=versions.esp32_version,
            stm32_version=versions.stm32_version,
            app_fw_zip_name=app_fw_zip_name,
            machine_description=f"{product_name} Machine",
        )
        config_path = tmp_dir / "config.json"
        config_path.write_text(
            json.dumps(config, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

        # Create ZIP (flat — all files in root)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(tmp_dir.iterdir()):
                zf.write(file, arcname=file.name)

    return PackageResult(
        zip_path=zip_path,
        size_bytes=zip_path.stat().st_size,
        sha256=compute_sha256(zip_path),
    )
