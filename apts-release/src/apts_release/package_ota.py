"""OTA package generator — folder-tree ZIP with OTA update structure."""

import tempfile
import zipfile
from pathlib import Path

from apts_release.scanner import FileManifest
from apts_release.utils import compute_sha256, safe_copy, ensure_dir
from apts_release.version_extractor import VersionInfo
from apts_release.package_rpi import PackageResult


def generate_ota_package(
    manifest: FileManifest,
    versions: VersionInfo,
    product_name: str,
    output_dir: Path,
) -> PackageResult:
    """Generate the OTA update ZIP package with folder tree structure."""
    ensure_dir(output_dir)

    # ZIP filename: <PRODUCT>-FW-OTA-V<release_ver>.zip
    zip_name = f"{product_name}-FW-OTA-V{versions.release_version}.zip"
    zip_path = output_dir / zip_name

    # Root folder inside ZIP matches the ZIP name (without .zip)
    root_folder = f"{product_name}-FW-OTA-V{versions.release_version}"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp) / root_folder

        # CORE-FIRMWARE/ — STM32 firmware
        stm32_fw = manifest.stm32_files.get("firmware")
        if stm32_fw:
            core_dir = ensure_dir(tmp_dir / "CORE-FIRMWARE")
            dst_name = f"Core-Firmware-V{versions.stm32_version}.bin"
            safe_copy(stm32_fw.path, core_dir / dst_name)

        # WIFI-FIRMWARE/ — ESP32 main app firmware
        esp32_fw = manifest.esp32_files.get("app_firmware")
        if esp32_fw:
            wifi_dir = ensure_dir(tmp_dir / "WIFI-FIRMWARE")
            dst_name = f"WIFI-V{versions.esp32_version}.bin"
            safe_copy(esp32_fw.path, wifi_dir / dst_name)

        # WEBPAGE/ — Web UI SPIFFS image
        webpage = manifest.esp32_files.get("webpage_1")
        if webpage:
            web_dir = ensure_dir(tmp_dir / "WEBPAGE")
            dst_name = f"UI-V{versions.webpage_version}.bin"
            safe_copy(webpage.path, web_dir / dst_name)

        # HMI .tft is NOT included in ZIP — version tracked in registry only

        # Create ZIP preserving the folder tree
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(tmp_dir.rglob("*")):
                if file.is_file():
                    arcname = file.relative_to(tmp_dir.parent)
                    zf.write(file, arcname=str(arcname))

    return PackageResult(
        zip_path=zip_path,
        size_bytes=zip_path.stat().st_size,
        sha256=compute_sha256(zip_path),
    )
