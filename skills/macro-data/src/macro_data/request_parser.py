"""Parse bounded natural-language requests into the macro-data request contract."""

from __future__ import annotations

import re
from typing import Any

_MONTH_RANGE = re.compile(
    r"(?P<start>\d{4}-(?:0[1-9]|1[0-2]))\s*(?:至|—|–|~)\s*"
    r"(?P<end>\d{4}-(?:0[1-9]|1[0-2]))"
)
_CHINESE_MONTH_RANGE = re.compile(
    r"(?:从)?(?P<start_year>\d{4})年(?P<start_month>\d{1,2})月"
    r"\s*(?:至|到|—|–|~)\s*"
    r"(?P<end_year>\d{4})年(?P<end_month>\d{1,2})月"
)
_QUARTER_RANGE = re.compile(
    r"(?P<start>\d{4}Q[1-4])\s*(?:至|—|–|-|~)\s*"
    r"(?P<end>\d{4}Q[1-4])",
    re.IGNORECASE,
)
_CHINESE_QUARTER_RANGE = re.compile(
    r"(?:从)?(?P<start_year>\d{4})年(?:第)?(?P<start_quarter>[一二三四1-4])季度"
    r"\s*(?:至|到|—|–|~)\s*"
    r"(?P<end_year>\d{4})年(?:第)?(?P<end_quarter>[一二三四1-4])季度"
)
_YEAR_RANGE = re.compile(
    r"(?:从)?(?P<start>\d{4})\s*年?\s*(?:至|到|—|–|-|~)\s*"
    r"(?P<end>\d{4})\s*年?"
)
_QUARTER_NUMBER = {"一": "1", "二": "2", "三": "3", "四": "4"}


def _parse_entities(text: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    remaining = text
    territory_mappings = (("中国香港", "HKG"), ("中国澳门", "MAC"))
    for label, code in territory_mappings:
        if label in remaining:
            entities.append(
                {
                    "name_or_code": code,
                    "entity_type": "territory",
                    "code_scheme": "ISO-3166-1-alpha-3",
                }
            )
            remaining = remaining.replace(label, "")
    country_mappings = (
        ("中国", "CHN"),
        ("美国", "USA"),
        ("日本", "JPN"),
        ("德国", "DEU"),
        ("法国", "FRA"),
        ("英国", "GBR"),
    )
    for label, code in country_mappings:
        if label in remaining:
            entities.append(
                {
                    "name_or_code": code,
                    "entity_type": "country",
                    "code_scheme": "ISO-3166-1-alpha-3",
                }
            )
    if not entities:
        raise ValueError("entity is required and must be explicit")
    return entities


def _parse_time_range(text: str) -> tuple[dict[str, str], str]:
    month = _CHINESE_MONTH_RANGE.search(text)
    if month:
        return {
            "start": (f"{month.group('start_year')}-{int(month.group('start_month')):02d}"),
            "end": (f"{month.group('end_year')}-{int(month.group('end_month')):02d}"),
        }, "M"
    quarter = _CHINESE_QUARTER_RANGE.search(text)
    if quarter:
        start_quarter = _QUARTER_NUMBER.get(
            quarter.group("start_quarter"),
            quarter.group("start_quarter"),
        )
        end_quarter = _QUARTER_NUMBER.get(
            quarter.group("end_quarter"),
            quarter.group("end_quarter"),
        )
        return {
            "start": f"{quarter.group('start_year')}-Q{start_quarter}",
            "end": f"{quarter.group('end_year')}-Q{end_quarter}",
        }, "Q"
    for pattern, frequency in (
        (_MONTH_RANGE, "M"),
        (_QUARTER_RANGE, "Q"),
        (_YEAR_RANGE, "A"),
    ):
        match = pattern.search(text)
        if match:
            inferred = frequency
            if any(marker in text for marker in ("月度", "每月", "月频")):
                inferred = "M"
            elif any(marker in text for marker in ("季度", "每季", "季频")):
                inferred = "Q"
            elif any(marker in text for marker in ("年度", "每年", "年频")):
                inferred = "A"
            return {
                "start": match.group("start").upper(),
                "end": match.group("end").upper(),
            }, inferred
    raise ValueError("time range is required and must be explicit")


def _parse_indicators(text: str) -> list[tuple[str, str | None, str | None]]:
    upper = text.upper()
    indicators: list[tuple[str, str | None, str | None]] = []
    if "CPI" in upper or "居民消费价格指数" in text:
        indicators.append(
            (
                "居民消费价格指数",
                "FP.CPI.TOTL",
                "Consumer price index (2010 = 100)",
            )
        )
    if "GDP" in upper or "国内生产总值" in text:
        indicators.append(
            (
                "实际国内生产总值" if "实际" in text else "国内生产总值",
                "NY.GDP.MKTP.KD" if "实际" in text else None,
                None,
            )
        )
    explicit_codes = re.findall(r"\b[A-Z]{2}(?:\.[A-Z0-9]+){2,}\b", upper)
    known_codes = {item[1] for item in indicators if item[1]}
    indicators.extend((code, code, None) for code in explicit_codes if code not in known_codes)
    return indicators or [(text.strip("。 "), None, None)]


def _native_constraints(
    research_question: str,
    parsed_indicators: list[tuple[str, str | None, str | None]],
) -> list[dict[str, str | None]]:
    native_constraints: list[dict[str, str | None]] = []
    upper_question = research_question.upper()
    is_wdi = any(
        marker in upper_question
        for marker in (
            "WDI",
            "WORLD BANK",
            "WORLD_BANK",
            "WORLD DEVELOPMENT INDICATORS",
            "世界银行",
        )
    )
    if is_wdi:
        native_constraints.extend(
            {
                "source_system": "WORLD_BANK",
                "dataset_name": "World Development Indicators",
                "indicator_code": indicator_code,
            }
            for _, indicator_code, _ in parsed_indicators
        )
    return native_constraints


def _research_use(research_question: str) -> str:
    if any(marker in research_question for marker in ("实时", "实时数据")):
        return "real_time"
    if any(marker in research_question for marker in ("预测", "预报")):
        return "forecasting"
    if any(marker in research_question for marker in ("面板", "跨国", "比较")):
        return "panel_analysis"
    return "descriptive_latest"


def _request_policies() -> dict[str, Any]:
    return {
        "fallback_policy": {
            "mode": "never",
            "allowed_sources": [],
            "allow_semantic_substitute": False,
            "allow_cross_source_stitching": False,
        },
        "transformation_policy": {
            "allow_unit_scaling": False,
            "allow_currency_conversion": False,
            "allow_downsampling": False,
            "allow_upsampling": False,
            "allow_imputation": False,
            "allow_self_seasonal_adjustment": False,
            "allow_rebasing": False,
            "requested_transformations": [],
        },
        "output_format": ["csv", "parquet", "json"],
    }


def build_candidate_request(text: str) -> dict[str, Any]:
    """Parse the first bounded Chinese macro-data request family."""

    research_question = text.strip()
    entities = _parse_entities(research_question)
    time_range, frequency = _parse_time_range(research_question)
    parsed_indicators = _parse_indicators(research_question)
    price_type = "real" if "实际" in research_question else "source_native"
    return {
        "schema_version": "0.2.0-beta",
        "research_question": research_question,
        "research_use": _research_use(research_question),
        "concepts": [
            {
                "concept": concept,
                "role": "outcome",
                "definition_constraints": [definition] if definition else [],
            }
            for concept, _, definition in parsed_indicators
        ],
        "indicators": [
            {
                "name_or_code": indicator_code or concept,
                "required_definition": definition,
            }
            for concept, indicator_code, definition in parsed_indicators
        ],
        "entities": entities,
        "time_range": time_range,
        "frequency": frequency,
        "unit": None,
        "seasonal_adjustment": "source_native",
        "price_basis": {
            "type": price_type,
            "base_period": None,
            "chain_linked": None,
        },
        "currency": None,
        "release_or_vintage": {"mode": "latest", "value": None},
        "preferred_sources": ["datapro"],
        "native_source_constraints": _native_constraints(
            research_question,
            parsed_indicators,
        ),
        **_request_policies(),
    }


def parse_research_request(text: str) -> dict[str, Any]:
    """Compatibility alias for the non-authoritative candidate parser."""

    return build_candidate_request(text)
