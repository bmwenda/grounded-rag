"""Build the deployment ZIP for the SQS-triggered ingestion Lambda."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAMBDA_RUNTIME_VERSION = "3.12"
LAMBDA_PLATFORM = "x86_64-manylinux_2_28"
MAX_UNCOMPRESSED_SIZE_BYTES = 250 * 1024 * 1024

CommandRunner = Callable[[Sequence[str], Path], None]


def run_command(command: Sequence[str], cwd: Path) -> None:
    """Run a packaging command and stop when it fails."""
    subprocess.run(command, cwd=cwd, check=True)


def copy_application(source_directory: Path, package_directory: Path) -> None:
    """Add application code without host-specific Python cache files."""
    shutil.copytree(
        source_directory,
        package_directory / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def create_archive(
    package_directory: Path,
    archive_path: Path,
    max_uncompressed_size_bytes: int = MAX_UNCOMPRESSED_SIZE_BYTES,
) -> tuple[int, int]:
    """Create a ZIP archive and return its compressed and expanded sizes."""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive_path = archive_path.with_suffix(".zip.tmp")

    try:
        with zipfile.ZipFile(
            temporary_archive_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for source_path in sorted(package_directory.rglob("*")):
                if source_path.is_file():
                    archive.write(source_path, source_path.relative_to(package_directory))

        with zipfile.ZipFile(temporary_archive_path) as archive:
            uncompressed_size = sum(member.file_size for member in archive.infolist())

        if uncompressed_size > max_uncompressed_size_bytes:
            raise ValueError(
                "Lambda ZIP packages may be at most "
                f"{max_uncompressed_size_bytes} bytes uncompressed; "
                f"this package is {uncompressed_size} bytes. "
                "Use the container-image deployment tracked in issue #83."
            )

        compressed_size = temporary_archive_path.stat().st_size
        temporary_archive_path.replace(archive_path)
        return compressed_size, uncompressed_size
    finally:
        temporary_archive_path.unlink(missing_ok=True)


def build_lambda_package(
    project_root: Path = PROJECT_ROOT,
    command_runner: CommandRunner = run_command,
    max_uncompressed_size_bytes: int = MAX_UNCOMPRESSED_SIZE_BYTES,
) -> Path:
    """Build ``dist/ingestion.zip`` with Lambda-compatible dependencies."""
    project_root = project_root.resolve()
    source_directory = project_root / "src"
    handler_path = source_directory / "s3_ingestion_handler.py"
    if not handler_path.is_file():
        raise FileNotFoundError(f"Lambda handler not found: {handler_path}")

    build_directory = project_root / "build"
    build_directory.mkdir(exist_ok=True)
    archive_path = project_root / "dist" / "ingestion.zip"

    with tempfile.TemporaryDirectory(dir=build_directory) as temporary_directory:
        temporary_path = Path(temporary_directory)
        package_directory = temporary_path / "package"
        requirements_path = temporary_path / "requirements.txt"
        package_directory.mkdir()

        command_runner(
            [
                "uv",
                "export",
                "--quiet",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--no-emit-workspace",
                "--output-file",
                str(requirements_path),
            ],
            project_root,
        )
        command_runner(
            [
                "uv",
                "pip",
                "install",
                "--quiet",
                "--target",
                str(package_directory),
                "--requirements",
                str(requirements_path),
                "--python-version",
                LAMBDA_RUNTIME_VERSION,
                "--python-platform",
                LAMBDA_PLATFORM,
                "--torch-backend",
                "cpu",
                "--strict",
            ],
            project_root,
        )
        copy_application(source_directory, package_directory)
        compressed_size, uncompressed_size = create_archive(
            package_directory,
            archive_path,
            max_uncompressed_size_bytes,
        )

    print(
        f"Created {archive_path.relative_to(project_root)} "
        f"({compressed_size} bytes compressed, {uncompressed_size} bytes uncompressed)."
    )
    return archive_path


def main() -> None:
    """Run the Lambda ZIP builder as a uv project command."""
    build_lambda_package()


if __name__ == "__main__":
    main()
