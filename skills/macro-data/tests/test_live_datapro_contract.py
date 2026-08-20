import os

import pytest

from macro_data.connectors.datapro import DataProConnector

pytestmark = pytest.mark.skipif(
    os.environ.get("MACRO_DATA_LIVE") != "1",
    reason="live DataPro test requires explicit MACRO_DATA_LIVE=1",
)


def test_live_datapro_returns_the_minimum_macro_contract():
    response = DataProConnector().search(
        "严格查询 World Bank WDI 口径：中国 2019—2024 年年度居民消费价格指数 CPI。"
    )

    assert response["code"] == 0
    assert response["dataset_type"] == "macro"
    assert isinstance(response["items"], list)
    assert "trace_id" not in response
