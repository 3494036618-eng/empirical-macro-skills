"""World Bank WDI Indicators API connector."""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from macro_data.connectors.base import ConnectorRequest, ConnectorResponse
from macro_data.result_parser import parse_world_bank_response

BASE_URL = "https://api.worldbank.org/v2"
WDI_SOURCE_ID = "2"
MAX_WDI_PAGES = 100
_CODE = re.compile(r"^[A-Z0-9.]+$")
_ENTITY = re.compile(r"^[A-Z]{3}$")
_YEAR = re.compile(r"^\d{4}$")


class WorldBankConnector:
    code = "world_bank"

    def __init__(
        self,
        *,
        transport: Callable[[str], Any] | None = None,
    ) -> None:
        self._transport = transport or self._http_transport

    def retrieve(self, request: ConnectorRequest) -> ConnectorResponse:
        specification = request.research_request
        if specification is None:
            raise ValueError("World Bank connector requires a structured request")
        entities = specification["entities"]
        indicators = specification["indicators"]
        if not entities or not indicators:
            raise ValueError("World Bank connector requires entities and indicators")
        if len(indicators) > 60:
            raise ValueError("World Bank connector supports at most 60 indicators")
        if any(item["entity_type"] not in {"country", "territory"} for item in entities):
            raise ValueError("World Bank panel entities must be country or territory")
        if specification["frequency"] != "A":
            raise ValueError("World Bank WDI connector currently supports annual data")

        entity_codes = sorted({item["name_or_code"] for item in entities})
        indicator_codes = sorted({item["name_or_code"] for item in indicators})
        start = specification["time_range"]["start"]
        end = specification["time_range"]["end"]
        if any(not _ENTITY.fullmatch(code) for code in entity_codes):
            raise ValueError("World Bank entity must be an ISO alpha-3 code")
        if any(not _CODE.fullmatch(code) for code in indicator_codes):
            raise ValueError("World Bank indicator must be an official indicator code")
        if not _YEAR.fullmatch(start) or not _YEAR.fullmatch(end):
            raise ValueError("World Bank WDI connector requires annual time bounds")

        entity_path = quote(";".join(entity_codes))
        indicator_path = quote(";".join(indicator_codes))
        observation_url = self._url(
            f"/country/{entity_path}/indicator/{indicator_path}",
            {
                "date": f"{start}:{end}",
                "format": "json",
                "source": WDI_SOURCE_ID,
                "per_page": "1000",
                "footnote": "y",
            },
        )
        indicator_url = self._url(
            f"/indicator/{indicator_path}",
            {"format": "json", "source": WDI_SOURCE_ID},
        )
        source_url = self._url(
            f"/source/{WDI_SOURCE_ID}",
            {"format": "json"},
        )
        raw = {
            "request": {
                "entity_codes": entity_codes,
                "indicator_codes": indicator_codes,
                "time_range": {"start": start, "end": end},
                "frequency": "A",
                "source_id": WDI_SOURCE_ID,
                "urls": {
                    "observations": observation_url,
                    "indicator_metadata": indicator_url,
                    "source_metadata": source_url,
                },
            },
            "observations": self._fetch_pages(observation_url),
            "indicator_metadata": self._fetch_pages(indicator_url),
            "source_metadata": self._fetch_pages(source_url),
        }
        return ConnectorResponse(
            provider=self.code,
            request_id=request.request_id,
            raw=raw,
            retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    @staticmethod
    def parse_response(raw: dict[str, Any]) -> dict[str, Any]:
        return parse_world_bank_response(raw)

    @staticmethod
    def _url(path: str, parameters: dict[str, str]) -> str:
        return f"{BASE_URL}{path}?{urlencode(parameters)}"

    @staticmethod
    def _page_url(url: str, page: int) -> str:
        parts = urlsplit(url)
        parameters = dict(parse_qsl(parts.query, keep_blank_values=True))
        parameters["page"] = str(page)
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(parameters), parts.fragment)
        )

    def _fetch_pages(self, url: str) -> Any:
        first = self._transport(url)
        if not isinstance(first, list) or len(first) != 2 or not isinstance(first[0], dict):
            return first
        try:
            pages = int(first[0].get("pages", 1))
        except (TypeError, ValueError):
            return first
        if pages <= 1:
            return first
        if pages > MAX_WDI_PAGES:
            raise ValueError(f"World Bank response exceeds page limit: {pages} > {MAX_WDI_PAGES}")
        return {
            "page_responses": [
                first,
                *[self._transport(self._page_url(url, page)) for page in range(2, pages + 1)],
            ]
        }

    @staticmethod
    def _http_transport(url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "macro-data/0.1",
            },
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
