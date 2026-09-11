"""FR-SPINE.1 — resolve any region input to a canonical ``RegionKey``.

Accepts an ISO-3166-1 code ("IN"), an ISO-3166-2 code ("IN-MH"), a place name ("Maharashtra",
"India"), or a ``(lat, lon)`` pair. Uses only repo-shipped data (``data/regions.json``) — there is
no external geocoder on the hot path (NFR-SPINE.2). Unknown input raises ``UnresolvedRegion`` — it is
never guessed."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple, Union

from ..domain.errors import RegionTooCoarse, UnresolvedRegion
from ..domain.types import RegionKey

_DATA = Path(__file__).resolve().parent.parent / "data" / "regions.json"


def _grid_id(lat: float, lon: float) -> str:
    return "g:{:.2f}:{:.2f}".format(round(lat * 4) / 4, round(lon * 4) / 4)


class RegionResolver:
    def __init__(self, data_path: Optional[Path] = None) -> None:
        raw = json.loads((data_path or _DATA).read_text())
        self.countries = raw["countries"]
        self.subdivisions = raw["subdivisions"]
        self.aliases = {k.lower(): v for k, v in raw["aliases"].items()}

    # ── public API ──────────────────────────────────────────────────────────────────────────────
    def resolve(self, value: Union[str, Tuple[float, float]], require_subcountry: bool = False) -> RegionKey:
        rk = self._resolve(value)
        if require_subcountry and rk.subdivision is None:
            raise RegionTooCoarse(
                f"weather requires a sub-country region; {value!r} resolved only to country {rk.country!r}")
        return rk

    # ── internals ───────────────────────────────────────────────────────────────────────────────
    def _resolve(self, value: Union[str, Tuple[float, float]]) -> RegionKey:
        if isinstance(value, (tuple, list)):
            if len(value) != 2:
                raise UnresolvedRegion(f"coordinate must be (lat, lon), got {value!r}")
            return self._from_coords(float(value[0]), float(value[1]))

        if not isinstance(value, str) or not value.strip():
            raise UnresolvedRegion(f"cannot resolve empty/typeless region {value!r}")

        token = value.strip()
        up = token.upper()

        if up in self.subdivisions:
            sub = self.subdivisions[up]
            return RegionKey(country=up.split("-")[0], subdivision=up, grid_id=_grid_id(sub["lat"], sub["lon"]))
        if up in self.countries:
            return RegionKey(country=up, subdivision=None, grid_id=None)

        alias = self.aliases.get(token.lower())
        if alias is not None:
            return self._resolve(alias)

        raise UnresolvedRegion(f"no region matches {value!r} (not an ISO code, known name, or alias)")

    def _from_coords(self, lat: float, lon: float) -> RegionKey:
        # nearest subdivision centroid (squared distance — adequate for picking among coarse centroids)
        best_code, best_d = None, None
        for code, sub in self.subdivisions.items():
            d = (sub["lat"] - lat) ** 2 + (sub["lon"] - lon) ** 2
            if best_d is None or d < best_d:
                best_code, best_d = code, d
        if best_code is None:
            raise UnresolvedRegion("no subdivision centroids loaded")
        return RegionKey(country=best_code.split("-")[0], subdivision=best_code, grid_id=_grid_id(lat, lon))

    def tz_of(self, region_key: RegionKey) -> str:
        if region_key.subdivision and region_key.subdivision in self.subdivisions:
            return self.subdivisions[region_key.subdivision]["tz"]
        return "UTC"
