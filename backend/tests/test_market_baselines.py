"""Tests for Zillow Research market baselines."""
import pytest

import market_baselines as mb
from conftest import ZHVI_FIXTURE


class TestParseSeries:
    def test_metro_rows_only(self):
        out = mb._parse_series_csv(ZHVI_FIXTURE)
        assert set(out) == {"Baltimore, MD", "Houston, TX", "Washington, DC"}
        assert "United States" not in out  # country row excluded

    def test_latest_and_year_ago(self):
        out = mb._parse_series_csv(ZHVI_FIXTURE)
        balt = out["Baltimore, MD"]
        assert balt["latest"] == 311200.0
        assert balt["year_ago"] == 314000.0  # 2025-12-31, last col <= 2025
        assert balt["as_of"] == "2026-08-31"

    def test_appreciation_sign(self):
        out = mb._parse_series_csv(ZHVI_FIXTURE)
        assert out["Baltimore, MD"]["latest"] < out["Baltimore, MD"]["year_ago"]
        assert out["Houston, TX"]["latest"] < out["Houston, TX"]["year_ago"]


class TestGetAppreciation:
    def test_exact_match_case_insensitive(self):
        assert mb.get_appreciation("Baltimore", "MD") == \
            round(311200 / 314000 - 1, 4)
        assert mb.get_appreciation("baltimore", "md") is not None

    def test_prefix_fallback_without_state(self):
        assert mb.get_appreciation("Baltimore", None) is not None

    def test_unknown_city_returns_none(self):
        assert mb.get_appreciation("Nowhereville", "ZZ") is None

    def test_city_metro_override(self):
        """Bethesda sits in the Washington, DC metro; Columbia in
        Baltimore's. The override map must route both."""
        beth = mb.get_metro_baseline("Bethesda", "MD")
        assert beth is not None
        assert beth["typical_value"] == 624000  # Washington fixture row
        assert beth["median_list_price"] == 642000
        assert mb.get_appreciation("Columbia", "MD") == round(
            311200 / 314000 - 1, 4)  # Baltimore row

    def test_override_missing_metro_falls_through(self, monkeypatch):
        """Override pointing at a metro absent from the data must not
        crash or fabricate — falls through to normal matching."""
        monkeypatch.setattr(
            mb, "CITY_METRO_OVERRIDES",
            {("bethesda", "md"): "Atlantis, ZZ"})
        monkeypatch.setattr(mb, "_cache", None)
        assert mb.get_appreciation("Bethesda", "MD") is None

    def test_prefix_match_respects_state(self, monkeypatch):
        """A city that prefixes a different state's metro must NOT
        match it (regression: Columbia, MD pulled Columbia, MO)."""
        zhvi = mb._parse_series_csv(
            'RegionID,SizeRank,RegionName,RegionType,StateName,'
            '2024-08-31,2025-08-31\n'
            '1,1,"Columbia, MO",msa,MO,200000,210000\n'
            '2,2,"Columbia, SC",msa,SC,300000,330000\n')
        monkeypatch.setattr(
            mb, "_fetch_series", lambda: {"zhvi": zhvi, "mlp": {}})
        monkeypatch.setattr(mb, "_cache", None)
        # Columbia MD has no metro -> None, NOT Missouri's +5%
        assert mb.get_appreciation("Columbia", "MD") is None
        assert mb.get_appreciation("Columbia", "SC") == 0.10

    def test_no_city_returns_none(self):
        assert mb.get_appreciation(None, "MD") is None


class TestCaching:
    def test_fetch_once_across_calls(self, monkeypatch):
        monkeypatch.setattr(mb, "_cache", None)
        calls = []
        orig = mb._fetch_series
        monkeypatch.setattr(
            mb, "_fetch_series",
            lambda: (calls.append(1), orig())[1])
        mb.get_appreciation("Baltimore", "MD")
        mb.get_appreciation("Houston", "TX")
        assert len(calls) == 1

    def test_failure_returns_none_not_raise(self, monkeypatch):
        def boom():
            raise OSError("network down")
        monkeypatch.setattr(mb, "_fetch_series", boom)
        monkeypatch.setattr(mb, "_cache", None)
        assert mb.get_appreciation("Baltimore", "MD") is None

    def test_failure_serves_stale_cache(self, monkeypatch):
        cached = mb.get_appreciation("Baltimore", "MD")  # populate cache
        monkeypatch.setattr(mb, "_cache_ts", 0.0)  # expire TTL
        def boom():
            raise OSError("network down")
        monkeypatch.setattr(mb, "_fetch_series", boom)
        assert cached is not None
        assert mb.get_appreciation("Baltimore", "MD") == cached


class TestGetMetroBaseline:
    def test_full_entry_for_match(self):
        entry = mb.get_metro_baseline("Baltimore", "MD")
        assert entry is not None
        assert entry["typical_value"] == 311200
        assert entry["median_list_price"] == 372000
        assert entry["typical_rent"] == 1820  # ZORI fixture row
        assert entry["as_of"] == "2026-08-31"

    def test_none_for_miss(self):
        assert mb.get_metro_baseline("Nowhereville", "ZZ") is None


class TestSnapshot:
    def test_snapshot_shape(self):
        snap = mb.get_baselines_snapshot()
        assert snap["ok"] is True
        assert snap["metro_count"] == 3
        entry = snap["metros"]["Baltimore, MD"]
        assert entry["median_list_price"] == 372000
        assert entry["as_of"] == "2026-08-31"
