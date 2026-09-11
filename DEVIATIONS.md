# Reference-implementation choices (deviations from the LLD production stack)

The design docs (`day1_kit/docs/plans/2026-09-09-exogenous-signals/LLD.md`) name a production stack
(Python 3.12, `uv`, Polars, pydantic v2, the `mcp` SDK, DuckDB/Postgres, FastAPI). This repository's
**reference implementation is stdlib-first** so it honours ruling **D-EXOG-2 — "free tier + open
source only, such that anyone can use it"** literally: it runs on a stock Python 3.9+ with **zero
third-party dependencies and zero secrets**. Each production component is kept as a documented seam,
not removed.

| LLD production choice | Reference impl here | Seam to production |
|---|---|---|
| pydantic v2 models | `dataclasses` + `__post_init__` validation (`domain/types.py`) | Same field names/invariants; a pydantic mirror can wrap these 1:1 |
| DuckDB (local) / Postgres (prod) | `sqlite3` `SqliteStore` (default) | `infrastructure/store.py` defines a `Store` protocol; DuckDB/Postgres are drop-in adapters |
| Polars | stdlib (`statistics`, lists) in the calibrator | pure functions take row lists; a Polars fast-path can replace the internals |
| `mcp` SDK (stdio) | shared tool registry + stdlib-`http.server` surface | `surfaces/tools.py` is transport-agnostic; the stdio SDK (needs 3.10+) binds the same registry |
| FastAPI | stdlib `http.server` (`surfaces/http_server.py`) | same handlers; FastAPI can mount the registry |
| `uv` | `python -m venv` + `pip` (documented) | `pyproject.toml` declares deps + extras |
| typer CLI | `argparse` (`surfaces/cli.py`) | same verbs |
| Hypothesis property tests | deterministic `pytest.mark.parametrize` enumerations | same invariants, exhaustive over enum cross-products |
| Anthropic LLM client | `LlmClient` protocol + `NullLlmClient` (returns `unknown` / `skipped`) | a real client is an optional extra; the 80% lane logic is client-agnostic |
| Python 3.12 | authored 3.9-safe (`from __future__ import annotations`) | `requires-python = ">=3.10"` in pyproject for the published intent; the stdio-MCP extra needs 3.10+ |

**Nothing about the design's *behaviour* changes:** the honesty model (`measured`/`prior`/`unknown`),
the 80%-earned-confidence auto-accept lane, the never-block degradation, the region×week grain, and
the provenance/staleness stamping are all implemented and tested here. These are engineering choices
about *dependencies*, made to satisfy the "anyone can run it" ruling; they are reversible per the
seams above.
