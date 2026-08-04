"""Drift guards: package metadata, __version__, and CITATION.cff move together."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import latenzy

ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_metadata() -> None:
    assert importlib.metadata.version("latenzy") == latenzy.__version__


def test_citation_cff_version_matches() -> None:
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert f"version: {latenzy.__version__}\n" in cff
