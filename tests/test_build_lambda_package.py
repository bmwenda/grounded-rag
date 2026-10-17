from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.build_lambda_package import build_lambda_package


def test_build_lambda_package_creates_linux_targeted_zip(tmp_path: Path) -> None:
    source_directory = tmp_path / "src"
    source_directory.mkdir()
    (source_directory / "__init__.py").write_text("")
    (source_directory / "s3_ingestion_handler.py").write_text("def lambda_handler(): pass\n")

    commands: list[Sequence[str]] = []

    def fake_command_runner(command: Sequence[str], _cwd: Path) -> None:
        commands.append(command)
        if command[1] == "export":
            Path(command[command.index("--output-file") + 1]).write_text("example==1.0\n")
        else:
            package_directory = Path(command[command.index("--target") + 1])
            (package_directory / "example").mkdir()
            (package_directory / "example" / "__init__.py").write_text("")

    archive_path = build_lambda_package(tmp_path, fake_command_runner)

    assert archive_path == tmp_path / "dist" / "ingestion.zip"
    assert [command[:2] for command in commands] == [["uv", "export"], ["uv", "pip"]]
    assert "--no-dev" in commands[0]
    assert "--python-version" in commands[1]
    assert commands[1][commands[1].index("--python-version") + 1] == "3.12"
    assert "--python-platform" in commands[1]
    assert commands[1][commands[1].index("--python-platform") + 1] == "x86_64-manylinux_2_28"
    assert commands[1][commands[1].index("--torch-backend") + 1] == "cpu"

    with zipfile.ZipFile(archive_path) as archive:
        assert sorted(archive.namelist()) == [
            "example/__init__.py",
            "src/__init__.py",
            "src/s3_ingestion_handler.py",
        ]


def test_build_lambda_package_rejects_archive_over_lambda_limit(tmp_path: Path) -> None:
    source_directory = tmp_path / "src"
    source_directory.mkdir()
    (source_directory / "s3_ingestion_handler.py").write_text("def lambda_handler(): pass\n")

    def fake_command_runner(command: Sequence[str], _cwd: Path) -> None:
        if command[1] == "export":
            Path(command[command.index("--output-file") + 1]).write_text("example==1.0\n")
        else:
            package_directory = Path(command[command.index("--target") + 1])
            (package_directory / "large_dependency.txt").write_text("too large")

    with pytest.raises(ValueError, match="Use the container-image deployment"):
        build_lambda_package(
            tmp_path,
            fake_command_runner,
            max_uncompressed_size_bytes=1,
        )

    assert not (tmp_path / "dist" / "ingestion.zip").exists()
