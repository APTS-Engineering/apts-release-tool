"""CLI entry point — Typer app with Rich UI."""

import getpass
import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from apts_release import __version__
from apts_release.changelog import generate_changelog
from apts_release.config import ProjectConfig, find_config_file, load_config
from apts_release.excel_export import generate_excel
from apts_release.package_ota import generate_ota_package
from apts_release.package_rpi import PackageResult, generate_rpi_package
from apts_release.registry import (
    append_release,
    build_release_entry,
    get_latest_release_version,
    get_releases,
    has_release_version,
    load_registry,
)
from apts_release.scanner import FileManifest, scan_projects
from apts_release.utils import format_size
from apts_release.version_extractor import (
    VersionInfo,
    auto_release_version,
    extract_cmake_project_ver,
    extract_define_version,
    extract_hmi_version,
    extract_version_from_file,
)

app = typer.Typer(
    name="apts-release",
    help="APTS-IOT firmware packaging and release tracking tool.",
    no_args_is_help=False,
    invoke_without_command=True,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"apts-release v{__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
    esp32: Optional[str] = typer.Option(
        None,
        "--esp32",
        help="Path to ESP32 project folder.",
    ),
    stm32: Optional[str] = typer.Option(
        None,
        "--stm32",
        help="Path to STM32 project folder.",
    ),
    package: str = typer.Option(
        "all",
        "--package",
        help="Package type to generate: rpi, ota, or all.",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for release files.",
    ),
    product: Optional[str] = typer.Option(
        None,
        "--product",
        help="Product name (e.g. HSC-TUBE-CUTTER).",
    ),
) -> None:
    """Package APTS-IOT firmware into distribution-ready ZIP archives."""
    if ctx.invoked_subcommand is not None:
        return

    _show_banner()
    console.print()

    # Load config (search from cwd upward)
    config_file = find_config_file(Path.cwd())
    cfg = load_config(config_file)
    if config_file:
        console.print(f"  Config: [cyan]{config_file}[/cyan]")
    else:
        console.print("  [dim]No release-config.yaml found, using defaults.[/dim]")

    # Resolve project directories: CLI flags > config > auto-detect
    esp32_dir, stm32_dir = _resolve_project_dirs(
        esp32_cli=esp32, stm32_cli=stm32, cfg=cfg, config_file=config_file
    )

    # Resolve product name
    product_name = product or cfg.product_name
    if product_name == "UNKNOWN":
        product_name = typer.prompt("  Product name (e.g. HSC-TUBE-CUTTER)")

    # Resolve output dir and registry paths
    output_dir = Path(output).resolve() if output else Path(cfg.output_dir).resolve()
    registry_path = output_dir / f"{product_name}-release-registry.json"
    changelog_path = output_dir / f"{product_name}-CHANGELOG.md"
    excel_path = output_dir / f"{product_name}-release-tracker.xlsx"

    # Pre-flight: ensure output directory is writable
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        test_file = output_dir / ".write-test"
        test_file.write_text("ok")
        test_file.unlink()
    except OSError:
        console.print(f"[red]Cannot write to output directory: {output_dir}[/red]")
        raise typer.Exit(code=1)

    console.print(f"  Product: [bold cyan]{product_name}[/bold cyan]")
    console.print(f"  ESP32:   [cyan]{esp32_dir}[/cyan]")
    console.print(f"  STM32:   [cyan]{stm32_dir}[/cyan]")
    console.print(f"  Output:  [cyan]{output_dir}[/cyan]")
    console.print()

    # --- Scan files ---
    console.print("  [bold]Scanning projects...[/bold]")
    console.print()
    manifest = scan_projects(
        esp32_dir,
        stm32_dir,
        esp32_build_subdir=cfg.esp32_build_dir,
        stm32_build_subdir=cfg.stm32_build_dir,
        hmi_subdir=cfg.hmi_dir,
    )

    _display_file_table("ESP32 Files", manifest.esp32_files)
    _display_file_table("STM32 Files", manifest.stm32_files)

    if manifest.missing:
        console.print("[red bold]  Missing files:[/red bold]")
        for m in manifest.missing:
            console.print(f"    [red]- {m}[/red]")
        console.print()

    if not manifest.all_found:
        console.print(
            "[red]Cannot proceed — required files are missing. "
            "Build both projects first.[/red]"
        )
        raise typer.Exit(code=1)

    # --- Extract versions ---
    versions = _extract_versions(
        esp32_dir, stm32_dir, manifest, cfg, registry_path, product_name
    )
    _display_version_table(versions)

    # --- Prompt for release version override ---
    override = typer.prompt(
        f"  Release version [auto: V{versions.release_version}]",
        default=versions.release_version,
        show_default=False,
    )
    versions.release_version = override.lstrip("Vv")

    # --- Duplicate release version check ---
    if has_release_version(registry_path, product_name, versions.release_version):
        console.print(
            f"  [yellow]Warning: V{versions.release_version} already exists "
            f"for {product_name}.[/yellow]"
        )
        if not typer.confirm("  Continue anyway?", default=False):
            console.print("  [dim]Aborted.[/dim]")
            raise typer.Exit()

    # --- Prompt for release notes ---
    notes = typer.prompt("  Release notes (one-liner, Enter to skip)", default="")

    # --- Check for existing release folder ---
    gen_rpi = package in ("all", "rpi")
    gen_ota = package in ("all", "ota")

    release_folder_check = output_dir / f"{product_name}-V{versions.release_version}"
    if release_folder_check.is_dir() and any(release_folder_check.iterdir()):
        console.print(
            f"  [yellow]Release folder already exists: "
            f"{release_folder_check.name}/[/yellow]"
        )
        if not typer.confirm("  Overwrite?", default=True):
            console.print("  [dim]Aborted.[/dim]")
            raise typer.Exit()

    # --- Confirmation ---
    console.print()
    pkg_list = []
    if gen_rpi:
        pkg_list.append("RPI Flash")
    if gen_ota:
        pkg_list.append("OTA")
    console.print(f"  Packages to generate: [bold]{', '.join(pkg_list)}[/bold]")
    if not typer.confirm("  Proceed?", default=True):
        console.print("  [dim]Aborted.[/dim]")
        raise typer.Exit()

    console.print()

    # --- Create versioned release subfolder ---
    release_folder = output_dir / f"{product_name}-V{versions.release_version}"
    release_folder.mkdir(parents=True, exist_ok=True)

    # --- Generate packages with progress bar ---
    results: dict[str, PackageResult] = {}

    # Count total steps for progress
    total_steps = 0
    if gen_rpi:
        total_steps += 1
    if gen_ota:
        total_steps += 1
    total_steps += 3  # HMI copy + registry + changelog + Excel
    hmi_entry = manifest.stm32_files.get("hmi")
    if hmi_entry:
        total_steps += 1

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("  Generating release...", total=total_steps)

        if gen_rpi:
            progress.update(task, description="  Generating FLASH package...")
            rpi_result = generate_rpi_package(
                manifest=manifest,
                versions=versions,
                product_name=product_name,
                output_dir=release_folder,
            )
            results["rpi"] = rpi_result
            progress.advance(task)

        if gen_ota:
            progress.update(task, description="  Generating OTA package...")
            ota_result = generate_ota_package(
                manifest=manifest,
                versions=versions,
                product_name=product_name,
                output_dir=release_folder,
            )
            results["ota"] = ota_result
            progress.advance(task)

        # Copy HMI .tft into the release folder (for reference, not in ZIPs)
        if hmi_entry:
            progress.update(task, description="  Copying HMI file...")
            shutil.copy2(hmi_entry.path, release_folder / hmi_entry.path.name)
            progress.advance(task)

        # --- Release tracking (stays at top-level output_dir) ---
        progress.update(task, description="  Updating release registry...")
        released_by = cfg.released_by or getpass.getuser()
        entry = build_release_entry(
            product=product_name,
            board=cfg.board,
            release_version=versions.release_version,
            versions=versions,
            manifest=manifest,
            package_results=results,
            notes=notes,
            released_by=released_by,
            release_name=cfg.release_name,
        )
        release_id = append_release(registry_path, entry)
        progress.advance(task)

        # Regenerate changelog
        progress.update(task, description="  Generating CHANGELOG.md...")
        cl_count = generate_changelog(registry_path, changelog_path)
        progress.advance(task)

        # Regenerate Excel (warn on failure, don't abort)
        progress.update(task, description="  Generating release-tracker.xlsx...")
        try:
            generate_excel(registry_path, excel_path)
        except Exception as exc:
            progress.stop()
            console.print(
                f"  [yellow]Warning: Excel generation failed: {exc}[/yellow]"
            )
            console.print(
                "  [yellow]ZIPs, registry, and changelog are fine.[/yellow]"
            )
        progress.advance(task)

    # --- Summary ---
    console.print()
    _display_summary(
        release_id, results, release_folder, registry_path,
        changelog_path, excel_path, notes, hmi_entry,
    )


@app.command()
def history(
    registry: Optional[str] = typer.Option(
        None,
        "--registry",
        help="Path to release-registry.json.",
    ),
    product_filter: Optional[str] = typer.Option(
        None,
        "--product",
        help="Filter by product name.",
    ),
) -> None:
    """Display past releases in a rich terminal table."""
    _show_banner()
    console.print()

    if registry:
        reg_path = Path(registry)
    else:
        # Auto-find: load config to get product name
        config_file = find_config_file(Path.cwd())
        cfg = load_config(config_file)
        out_dir = Path(cfg.output_dir).resolve()
        reg_path = out_dir / f"{cfg.product_name}-release-registry.json"
        # Fallback to old name for backwards compat
        if not reg_path.is_file():
            reg_path = out_dir / "release-registry.json"
    if not reg_path.is_file():
        console.print(f"  [red]Registry not found: {reg_path}[/red]")
        console.print("  [dim]Run a release first, or specify --registry path.[/dim]")
        raise typer.Exit(code=1)

    releases = get_releases(reg_path, product=product_filter)
    if not releases:
        console.print("  [dim]No releases found.[/dim]")
        raise typer.Exit()

    table = Table(title="  APTS-IOT Release History", show_header=True, header_style="bold")
    table.add_column("ID", style="dim", min_width=16)
    table.add_column("Date", min_width=12)
    table.add_column("Product", style="cyan", min_width=18)
    table.add_column("Release", style="bold", min_width=8)
    table.add_column("ESP32", min_width=8)
    table.add_column("STM32", min_width=8)
    table.add_column("Notes", min_width=30)

    for release in reversed(releases):
        ts = release.get("timestamp", "")[:10]
        if len(ts) == 10 and ts[4] == "-":
            date_str = f"{ts[8:10]}-{ts[5:7]}-{ts[0:4]}"
        else:
            date_str = ts
        comps = release.get("components", {})
        table.add_row(
            release.get("id", ""),
            date_str,
            release.get("product", ""),
            release.get("release_version", ""),
            comps.get("esp32_firmware", {}).get("version", ""),
            comps.get("stm32_firmware", {}).get("version", ""),
            release.get("notes", "")[:50],
        )

    console.print(table)

    # Summary line
    products = {r.get("product") for r in releases}
    console.print(
        f"\n  Total: {len(releases)} releases across {len(products)} product(s)"
    )
    console.print(f"  Registry: [dim]{reg_path}[/dim]")


@app.command()
def export(
    registry: Optional[str] = typer.Option(
        None,
        "--registry",
        help="Path to release-registry.json.",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for generated files.",
    ),
) -> None:
    """Regenerate Excel and Changelog from the release registry."""
    _show_banner()
    console.print()

    # Load config for product name
    config_file = find_config_file(Path.cwd())
    cfg = load_config(config_file)
    product_name = cfg.product_name

    if registry:
        reg_path = Path(registry)
    else:
        out_dir_default = Path(cfg.output_dir).resolve()
        reg_path = out_dir_default / f"{product_name}-release-registry.json"
        if not reg_path.is_file():
            reg_path = out_dir_default / "release-registry.json"

    if not reg_path.is_file():
        console.print(f"  [red]Registry not found: {reg_path}[/red]")
        raise typer.Exit(code=1)

    out_dir = Path(output).resolve() if output else reg_path.parent

    console.print(f"  Regenerating from {reg_path} ...")

    cl_path = out_dir / f"{product_name}-CHANGELOG.md"
    cl_count = generate_changelog(reg_path, cl_path)
    console.print(f"    [green]{cl_path.name}  ({cl_count} entries)[/green]")

    xl_path = out_dir / f"{product_name}-release-tracker.xlsx"
    xl_count = generate_excel(reg_path, xl_path)
    console.print(f"    [green]{xl_path.name}  ({xl_count} rows)[/green]")


@app.command()
def publish(
    version_tag: Optional[str] = typer.Argument(
        None,
        help="Release version to publish (e.g. 1.0.0). Defaults to latest.",
    ),
    repo: Optional[str] = typer.Option(
        None,
        "--repo",
        help="GitHub repo (e.g. MyOrg/apts-firmware-releases).",
    ),
    draft: bool = typer.Option(
        False,
        "--draft",
        help="Create as draft release.",
    ),
) -> None:
    """Publish a release to GitHub Releases."""
    import subprocess

    _show_banner()
    console.print()

    # Load config
    config_file = find_config_file(Path.cwd())
    cfg = load_config(config_file)

    github_repo = repo or cfg.github_repo
    if not github_repo:
        console.print(
            "[red]  No GitHub repo configured.[/red]\n"
            "  Set github.repo in release-config.yaml or use --repo."
        )
        raise typer.Exit(code=1)

    # Check gh CLI is available
    try:
        subprocess.run(
            ["gh", "--version"], capture_output=True, check=True,
        )
    except FileNotFoundError:
        console.print(
            "[red]  GitHub CLI (gh) not found.[/red]\n"
            "  Install: https://cli.github.com\n"
            "  Then run: gh auth login"
        )
        raise typer.Exit(code=1)

    # Load registry
    output_dir = Path(cfg.output_dir).resolve()
    product_name = cfg.product_name
    registry_path = output_dir / f"{product_name}-release-registry.json"
    # Fallback to old name
    if not registry_path.is_file():
        registry_path = output_dir / "release-registry.json"
    if not registry_path.is_file():
        console.print(f"  [red]Registry not found: {registry_path}[/red]")
        raise typer.Exit(code=1)
    releases = get_releases(registry_path, product=product_name)
    if not releases:
        console.print("  [red]No releases found in registry.[/red]")
        raise typer.Exit(code=1)

    # Find the target release
    if version_tag:
        normalised = version_tag if version_tag.startswith("V") else f"V{version_tag}"
        target = next(
            (r for r in reversed(releases) if r.get("release_version") == normalised),
            None,
        )
        if not target:
            console.print(f"  [red]{normalised} not found in registry.[/red]")
            raise typer.Exit(code=1)
    else:
        target = releases[-1]  # latest

    rel_ver = target["release_version"]
    release_folder = output_dir / f"{product_name}-{rel_ver}"

    if not release_folder.is_dir():
        console.print(f"  [red]Release folder not found: {release_folder}[/red]")
        raise typer.Exit(code=1)

    # Collect assets: release folder files + tracker files from output_dir
    assets = sorted(f for f in release_folder.iterdir() if f.is_file())
    if not assets:
        console.print(f"  [red]Release folder is empty: {release_folder.name}[/red]")
        raise typer.Exit(code=1)

    # Include Excel tracker and changelog so production has full context
    excel_file = output_dir / f"{product_name}-release-tracker.xlsx"
    changelog_file = output_dir / f"{product_name}-CHANGELOG.md"
    # Fallback to old names
    if not excel_file.is_file():
        excel_file = output_dir / "release-tracker.xlsx"
    if not changelog_file.is_file():
        changelog_file = output_dir / "CHANGELOG.md"
    if excel_file.is_file():
        assets.append(excel_file)
    if changelog_file.is_file():
        assets.append(changelog_file)

    # Build release notes from registry entry
    comps = target.get("components", {})
    released_by = target.get("released_by", "")
    timestamp = target.get("timestamp", "")[:10]
    release_name = target.get("release_name", "")
    title_line = f"## {product_name} — {rel_ver}"
    if release_name:
        title_line = f"## {release_name} ({product_name}) — {rel_ver}"
    notes_lines = [
        title_line,
        "",
        f"**Board:** {target.get('board', 'APTS-IOT-V2-2')}",
        f"**Release ID:** {target.get('id', '')}",
        f"**Date:** {timestamp}",
    ]
    if released_by:
        notes_lines.append(f"**Released by:** {released_by}")
    notes_lines.extend([
        "",
        "### Component Versions",
        "",
        "| Component | Version |",
        "|-----------|---------|",
    ])
    for comp_key, comp in comps.items():
        label = comp_key.replace("_", " ").title()
        ver = comp.get("version", "N/A")
        if ver:
            notes_lines.append(f"| {label} | {ver} |")
    notes_lines.extend([
        "",
        "### Assets",
        "",
        "| File | Description |",
        "|------|-------------|",
        f"| `{product_name}-FW-FLASH-{rel_ver}.zip` | Full flash package (bootloader + all bins) |",
        f"| `{product_name}-FW-OTA-{rel_ver}.zip` | OTA update package (app + webpage only) |",
        f"| `{product_name}-release-tracker.xlsx` | Full release history spreadsheet |",
        f"| `{product_name}-CHANGELOG.md` | Human-readable changelog |",
    ])
    # Check if HMI exists in assets
    hmi_assets = [a for a in assets if a.suffix == ".tft"]
    if hmi_assets:
        notes_lines.append(f"| `{hmi_assets[0].name}` | HMI display firmware |")
    user_notes = target.get("notes", "")
    if user_notes:
        notes_lines.append(f"\n### Notes\n\n{user_notes}")

    release_notes = "\n".join(notes_lines)

    # Tag: just the version (repo is already per-machine)
    tag = rel_ver

    # Show what will be published
    console.print(f"  Repo:    [bold cyan]{github_repo}[/bold cyan]")
    console.print(f"  Tag:     [bold]{tag}[/bold]")
    console.print(f"  Title:   {product_name} {rel_ver}")
    console.print(f"  Assets:  {len(assets)} files")
    for a in assets:
        console.print(f"    - {a.name}")
    console.print()

    if not typer.confirm("  Publish to GitHub?", default=True):
        console.print("  [dim]Aborted.[/dim]")
        raise typer.Exit()

    # Build gh command
    cmd = [
        "gh", "release", "create", tag,
        "--repo", github_repo,
        "--title", f"{product_name} {rel_ver}",
        "--notes", release_notes,
    ]
    if draft:
        cmd.append("--draft")
    for asset in assets:
        cmd.append(str(asset))

    console.print("\n  Publishing...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        url = result.stdout.strip()
        console.print(f"  [bold green]Published![/bold green]")
        console.print(f"  [cyan]{url}[/cyan]")
    else:
        console.print(f"  [red]Failed:[/red] {result.stderr.strip()}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _show_banner() -> None:
    """Display the tool welcome banner."""
    banner = Panel(
        "[bold white]APTS-IOT Firmware Release Tool[/bold white]"
        f"  [dim]v{__version__}[/dim]\n"
        "[dim]Board: APTS-IOT-V2-2  |  STM32H723 + ESP32[/dim]",
        border_style="bright_blue",
        padding=(1, 2),
    )
    console.print(banner)


def _display_file_table(title: str, files: dict) -> None:
    """Show a Rich table of discovered files."""
    table = Table(title=f"  {title}", show_header=True, header_style="bold")
    table.add_column("File", style="cyan", min_width=22)
    table.add_column("Size", justify="right", min_width=10)
    table.add_column("Status", min_width=10)

    for entry in files.values():
        table.add_row(
            entry.path.name,
            format_size(entry.size_bytes),
            "[green]Found[/green]",
        )

    if not files:
        table.add_row("[dim]---[/dim]", "[dim]---[/dim]", "[red]None found[/red]")

    console.print(table)
    console.print()


def _display_version_table(versions: VersionInfo) -> None:
    """Show a Rich table of extracted versions."""
    table = Table(title="  Versions Detected", show_header=True, header_style="bold")
    table.add_column("Component", style="cyan", min_width=18)
    table.add_column("Version", min_width=16)
    table.add_column("Source", style="dim", min_width=24)

    table.add_row("ESP32 Firmware", versions.esp32_version, "CMakeLists.txt")
    table.add_row("STM32 Firmware", versions.stm32_version, "display_task.h")
    table.add_row("Web UI", versions.webpage_version, "Version.txt")

    hmi_ver = versions.hmi_version or "[dim]N/A (no HMI)[/dim]"
    hmi_src = "filename" if versions.hmi_version else "---"
    table.add_row("HMI", hmi_ver, hmi_src)

    table.add_row(
        "[bold]Release Version[/bold]",
        f"[bold]V{versions.release_version}[/bold]",
        "auto (patch bump)",
    )

    console.print(table)
    console.print()


def _display_summary(
    release_id: str,
    results: dict[str, PackageResult],
    release_folder: Path,
    registry_path: Path,
    changelog_path: Path,
    excel_path: Path,
    notes: str,
    hmi_entry=None,
) -> None:
    """Display the release summary panel."""
    lines = [f"[bold]Release ID:[/bold] {release_id}"]
    lines.append(f"[bold]Folder:[/bold]    {release_folder.name}/")
    lines.append("")

    for pkg_type, result in results.items():
        label = "FLASH" if pkg_type == "rpi" else "OTA"
        lines.append(
            f"[bold]{label}:[/bold]  {result.zip_path.name}\n"
            f"        Size: {format_size(result.size_bytes)}  |  "
            f"SHA256: {result.sha256[:12]}..."
        )

    if hmi_entry:
        lines.append(f"[bold]HMI:[/bold]   {hmi_entry.path.name}")

    lines.append("")
    lines.append(f"Registry:   [dim]{registry_path}[/dim]")
    lines.append(f"Changelog:  [dim]{changelog_path}[/dim]")
    lines.append(f"Excel:      [dim]{excel_path}[/dim]")
    if notes:
        lines.append(f"\nNotes: {notes}")

    panel = Panel(
        "\n".join(lines),
        title="[bold green]Release Complete[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
    console.print(panel)


# ---------------------------------------------------------------------------
# Project directory resolution
# ---------------------------------------------------------------------------


def _resolve_project_dirs(
    esp32_cli: str | None,
    stm32_cli: str | None,
    cfg: ProjectConfig,
    config_file: Path | None,
) -> tuple[Path, Path]:
    """Resolve ESP32 and STM32 project directories.

    Priority: CLI flags > release-config.yaml > auto-detect (*_ESP32_FW / *_STM32_FW).
    """
    # Base directory for relative paths in config
    base_dir = config_file.parent if config_file else Path.cwd()

    esp32_dir: Path | None = None
    stm32_dir: Path | None = None

    # 1) CLI flags (highest priority)
    if esp32_cli:
        esp32_dir = Path(esp32_cli).resolve()
    if stm32_cli:
        stm32_dir = Path(stm32_cli).resolve()

    # 2) Config file
    if esp32_dir is None and cfg.esp32_project_dir:
        candidate = (base_dir / cfg.esp32_project_dir).resolve()
        if candidate.is_dir():
            esp32_dir = candidate
            console.print(f"  [dim]ESP32 from config: {candidate.name}[/dim]")

    if stm32_dir is None and cfg.stm32_project_dir:
        candidate = (base_dir / cfg.stm32_project_dir).resolve()
        if candidate.is_dir():
            stm32_dir = candidate
            console.print(f"  [dim]STM32 from config: {candidate.name}[/dim]")

    # 3) Auto-detect: scan cwd for *_ESP32_FW / *_STM32_FW
    if esp32_dir is None:
        matches = sorted(Path.cwd().glob("*_ESP32_FW"))
        dirs = [d for d in matches if d.is_dir()]
        if len(dirs) == 1:
            esp32_dir = dirs[0].resolve()
            console.print(f"  [dim]ESP32 auto-detected: {dirs[0].name}[/dim]")
        elif len(dirs) > 1:
            console.print(
                f"[yellow]  Multiple *_ESP32_FW folders found: "
                f"{', '.join(d.name for d in dirs)}. Use --esp32 to pick one.[/yellow]"
            )

    if stm32_dir is None:
        matches = sorted(Path.cwd().glob("*_STM32_FW"))
        dirs = [d for d in matches if d.is_dir()]
        if len(dirs) == 1:
            stm32_dir = dirs[0].resolve()
            console.print(f"  [dim]STM32 auto-detected: {dirs[0].name}[/dim]")
        elif len(dirs) > 1:
            console.print(
                f"[yellow]  Multiple *_STM32_FW folders found: "
                f"{', '.join(d.name for d in dirs)}. Use --stm32 to pick one.[/yellow]"
            )

    # Validate
    if esp32_dir is None or stm32_dir is None:
        missing = []
        if esp32_dir is None:
            missing.append("ESP32")
        if stm32_dir is None:
            missing.append("STM32")
        console.print(
            f"[red]  Could not find {' and '.join(missing)} project folder(s).[/red]"
        )
        console.print(
            "  [dim]Use --esp32 / --stm32, set projects.esp32_dir / projects.stm32_dir "
            "in release-config.yaml, or name folders *_ESP32_FW / *_STM32_FW.[/dim]"
        )
        raise typer.Exit(code=1)

    if not esp32_dir.is_dir():
        console.print(f"[red]ESP32 project not found at: {esp32_dir}[/red]")
        raise typer.Exit(code=1)
    if not stm32_dir.is_dir():
        console.print(f"[red]STM32 project not found at: {stm32_dir}[/red]")
        raise typer.Exit(code=1)

    return esp32_dir, stm32_dir


# ---------------------------------------------------------------------------
# Version extraction
# ---------------------------------------------------------------------------


def _extract_versions(
    esp32_dir: Path,
    stm32_dir: Path,
    manifest: FileManifest,
    cfg: ProjectConfig,
    registry_path: Path,
    product_name: str,
) -> VersionInfo:
    """Extract all version strings from project sources."""
    # ESP32: from CMakeLists.txt PROJECT_VER
    esp32_ver = extract_cmake_project_ver(esp32_dir / cfg.esp32_version.file)
    if esp32_ver is None:
        console.print(
            "[yellow]  Warning: Could not extract ESP32 version "
            f"from {cfg.esp32_version.file}[/yellow]"
        )
        esp32_ver = typer.prompt("  Enter ESP32 firmware version manually (e.g. 1.0.0)")

    # STM32: from #define STM_FIRMWARE_VERSION in header
    stm32_ver_src = cfg.stm32_version
    if stm32_ver_src.define:
        stm32_ver = extract_define_version(
            stm32_dir / stm32_ver_src.file, stm32_ver_src.define
        )
    else:
        stm32_ver = extract_version_from_file(stm32_dir / stm32_ver_src.file)
    if stm32_ver is None:
        console.print(
            "[yellow]  Warning: Could not extract STM32 version "
            f"from {stm32_ver_src.file}[/yellow]"
        )
        stm32_ver = typer.prompt("  Enter STM32 firmware version manually (e.g. 1.0.0)")

    # Webpage: from Version.txt
    webpage_ver = extract_version_from_file(
        esp32_dir / cfg.esp32_webpage_version.file
    )
    if webpage_ver is None:
        console.print(
            "[yellow]  Warning: Could not extract webpage version "
            f"from {cfg.esp32_webpage_version.file}[/yellow]"
        )
        webpage_ver = typer.prompt("  Enter Web UI version manually (e.g. 1.0.0)")

    # HMI: from .tft filename
    hmi_ver: str | None = None
    hmi_entry = manifest.stm32_files.get("hmi")
    if hmi_entry:
        hmi_ver = extract_hmi_version(hmi_entry.path)

    # Release version: auto-increment from registry
    prev_ver = get_latest_release_version(registry_path, product=product_name)
    release_ver = auto_release_version(prev_ver)

    return VersionInfo(
        esp32_version=esp32_ver,
        stm32_version=stm32_ver,
        webpage_version=webpage_ver,
        hmi_version=hmi_ver,
        release_version=release_ver,
    )
