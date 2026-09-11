"""PBI-SPINE.1 static merge gates: licence + attribution present, no paid-API hostnames, surface
handlers hold no business imports, and the signal/feature hot path imports no LLM client."""
from __future__ import annotations

import re
from pathlib import Path

import exog_signals

PKG = Path(exog_signals.__file__).resolve().parent
ROOT = PKG.parent

PAID_HOSTS = re.compile(r"calendarific\.com|api\.openweathermap\.org/data/2\.5/onecall|tomorrow\.io|visualcrossing\.com")


def _py_files():
    return list(PKG.rglob("*.py"))


def test_license_and_notice_present_with_attribution():
    assert (ROOT / "LICENSE").is_file()
    notice = (ROOT / "NOTICE")
    assert notice.is_file() and "FieldAssist" in notice.read_text()


def test_no_paid_api_hostnames_in_source():
    offenders = [str(f) for f in _py_files() if PAID_HOSTS.search(f.read_text())]
    assert offenders == [], f"paid-API host referenced in: {offenders}"


def test_surface_handlers_import_no_business_logic():
    # tools.py + http_server.py are pure transport (Anuj §8.1) — they take collaborators as params,
    # never import infrastructure/application. (cli.py is the composition root and is exempt.)
    for name in ("tools.py", "http_server.py"):
        for line in (PKG / "surfaces" / name).read_text().splitlines():
            if line.strip().startswith(("import ", "from ")):
                assert "infrastructure" not in line, f"{name} imports infrastructure: {line!r}"
                assert "application" not in line, f"{name} imports application: {line!r}"


def test_hot_path_never_imports_the_llm_client():
    hot = ["application/region_resolver.py", "application/provenance.py", "application/composer.py",
           "application/calibrator.py", "infrastructure/store.py", "surfaces/tools.py",
           "surfaces/http_server.py"]
    for rel in hot:
        src = (PKG / rel).read_text()
        for line in src.splitlines():
            if line.strip().startswith(("import ", "from ")):
                assert "llm" not in line, f"{rel} imports the LLM client on the hot path: {line!r}"
