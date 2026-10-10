"""Shared fixtures. Keeps the suite network-free: Zillow Research
baselines resolve from local fixture data instead of live S3."""
import pytest

import market_baselines as mb

ZHVI_FIXTURE = """RegionID,SizeRank,RegionName,RegionType,StateName,2025-08-31,2025-09-30,2025-10-31,2025-11-30,2025-12-31,2026-01-31,2026-02-28,2026-03-31,2026-04-30,2026-05-31,2026-06-30,2026-07-31,2026-08-31
102001,0,United States,country,,395000,396000,397000,398000,399000,400000,401000,402000,403000,404000,405000,406000,407000
394913,1,"Baltimore, MD",msa,MD,310000,311000,312000,313000,314000,315000,316000,317000,318000,319000,320000,321000,311200
394913,2,"Houston, TX",msa,TX,350000,349000,348000,347000,346000,345000,344000,343000,342000,341000,345000,346000,344400
"""

MLP_FIXTURE = """RegionID,SizeRank,RegionName,RegionType,StateName,2026-06-30,2026-07-31,2026-08-31
102001,0,United States,country,,400000,401000,402000
394913,1,"Baltimore, MD",msa,MD,370000,371000,372000
394913,2,"Houston, TX",msa,TX,345000,344000,343000
"""


@pytest.fixture(autouse=True)
def stub_market_baselines(monkeypatch):
    """Serve fixture Zillow data and reset the module cache."""
    def fake_fetch():
        return {"zhvi": mb._parse_series_csv(ZHVI_FIXTURE),
                "mlp": mb._parse_series_csv(MLP_FIXTURE)}

    monkeypatch.setattr(mb, "_fetch_series", fake_fetch)
    monkeypatch.setattr(mb, "_cache", None)
    monkeypatch.setattr(mb, "_cache_ts", 0.0)
    yield
