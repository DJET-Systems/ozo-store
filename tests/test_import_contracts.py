"""Tests verifying import-linter architecture contracts and enforcement."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from importlinter.cli import EXIT_STATUS_ERROR, EXIT_STATUS_SUCCESS, lint_imports

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_real_codebase_passes_import_linter_contracts() -> None:
    """All configured import-linter contracts pass on the real repository."""
    exit_code = lint_imports(
        config_filename=str(REPO_ROOT / "pyproject.toml"),
        no_cache=True,
        no_logo=True,
    )
    assert exit_code == EXIT_STATUS_SUCCESS


def test_forbidden_core_to_addon_import_fails_contract(tmp_path: Path) -> None:
    """A synthetic import from apps.core into apps.addons violates the contract."""
    apps_dir = tmp_path / "apps"
    for pkg in (
        "core",
        "catalog",
        "inventory",
        "customers",
        "orders",
        "payments",
        "shipping",
        "purchasing",
        "notifications",
        "reports",
        "dashboard",
        "storefront",
        "presets",
        "addons",
    ):
        (apps_dir / pkg).mkdir(parents=True)
        (apps_dir / pkg / "__init__.py").write_text("", encoding="utf-8")
    (apps_dir / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "__init__.py").write_text("", encoding="utf-8")

    # Deliberately introduce a forbidden core -> addons dependency
    (apps_dir / "addons" / "sample.py").write_text("FLAG = True\n", encoding="utf-8")
    (apps_dir / "core" / "bad.py").write_text(
        "from apps.addons.sample import FLAG\n", encoding="utf-8"
    )

    cfg = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(cfg, encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from importlinter.cli import lint_imports; "
                "rc = lint_imports(config_filename='pyproject.toml', no_cache=True, no_logo=True); "
                "sys.exit(rc)"
            ),
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == EXIT_STATUS_ERROR
    assert "Core apps must never import addons" in proc.stdout
