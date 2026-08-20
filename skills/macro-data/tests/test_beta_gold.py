import importlib
import json

import pytest
from conftest import FIXTURES, load_json

from macro_data.contracts import validate_document
from macro_data.provenance import sha256_file
from macro_data.source_registry import SourceRegistry
from macro_data.transformation_engine import apply_transformations


def request(
    *,
    question="比较中国2019年至2021年的年度居民消费价格。",
    research_use="panel_analysis",
    entities=(("CHN", "country"),),
    indicators=("FP.CPI.TOTL",),
    start="2019",
    end="2021",
    frequency="A",
):
    return {
        "schema_version": "0.2.0-beta",
        "research_question": question,
        "research_use": research_use,
        "concepts": [
            {
                "concept": code,
                "role": "outcome",
                "definition_constraints": [],
            }
            for code in indicators
        ],
        "indicators": [{"name_or_code": code, "required_definition": None} for code in indicators],
        "entities": [
            {
                "name_or_code": code,
                "entity_type": entity_type,
                "code_scheme": (
                    "ISO-3166-1-alpha-3"
                    if entity_type in {"country", "territory"}
                    else "World Bank"
                ),
            }
            for code, entity_type in entities
        ],
        "time_range": {"start": start, "end": end},
        "frequency": frequency,
        "unit": None,
        "seasonal_adjustment": "source_native",
        "price_basis": {
            "type": "source_native",
            "base_period": None,
            "chain_linked": None,
        },
        "currency": None,
        "release_or_vintage": {"mode": "latest", "value": None},
        "preferred_sources": ["datapro", "world_bank"],
        "native_source_constraints": [
            {
                "source_system": "WORLD_BANK",
                "dataset_name": "World Development Indicators",
                "indicator_code": code,
            }
            for code in indicators
        ],
        "fallback_policy": {
            "mode": "allow_official",
            "allowed_sources": ["world_bank"],
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


def candidate(
    entity,
    indicator,
    period,
    *,
    value=100.0,
    source="WORLD_BANK",
    series_suffix="",
    frequency="A",
):
    return {
        "provider": "world_bank",
        "series_key": (
            f"{source}|World Development Indicators|{entity}|{indicator}{series_suffix}"
        ),
        "source_system": source,
        "dataset_id": "2",
        "dataset_name": "World Development Indicators",
        "entity_code": entity,
        "entity_name": entity,
        "indicator_code": indicator,
        "indicator_name": indicator,
        "time_raw": period,
        "time_grain": {"A": "year", "Q": "quarter", "M": "month"}[frequency],
        "observed_frequency": frequency,
        "value": value,
        "unit": {"value": "index, 2010=100", "status": "source_documented"},
        "seasonal_adjustment": {"value": None, "status": "not_applicable"},
        "price_basis": {
            "value": {
                "type": "index",
                "base_period": "2010=100",
                "chain_linked": None,
            },
            "status": "source_documented",
        },
        "definition": {"value": "Official definition", "status": "source_provided"},
        "release_date": {"value": None, "status": "unresolved"},
        "vintage": {"value": None, "status": "unresolved"},
        "p_date": {
            "value": "2026-07-13",
            "semantics": "source_last_updated",
        },
        "license": {
            "id": "CC-BY-4.0",
            "url": "https://example.test/license",
            "attribution": "World Bank",
            "use_status": "allowed",
            "allows_requested_use": True,
        },
    }


def parsed(items, provider="world_bank", provider_code=0):
    return {
        "provider": provider,
        "execution": {"provider_code": provider_code, "message": "test"},
        "candidates": items,
        "raw_response": {"items": items},
        "fixture_provenance": {},
        "transformations": [],
    }


def evaluate(req, items, **kwargs):
    module = importlib.import_module("macro_data.semantic_validator")
    return module.evaluate_candidates(req, parsed(items, **kwargs))


def complete_items(req):
    return [
        candidate(entity["name_or_code"], indicator["name_or_code"], str(year))
        for entity in req["entities"]
        for indicator in req["indicators"]
        for year in range(
            int(req["time_range"]["start"]),
            int(req["time_range"]["end"]) + 1,
        )
    ]


def test_a01_single_country_single_indicator_is_analysis_ready():
    req = request()
    result = evaluate(req, complete_items(req))
    assert (
        result["execution_status"],
        result["research_readiness"],
        result["delivery_eligibility"],
    ) == ("success", "ready", "analysis_ready")


def test_a02_cross_country_panel_keeps_aggregate_separate():
    req = request(entities=(("CHN", "country"), ("USA", "country"), ("WLD", "region")))
    result = evaluate(req, complete_items(req))
    assert result["delivery_eligibility"] == "analysis_ready"
    assert {item["entity_code"] for item in result["selected_items"]} == {
        "CHN",
        "USA",
        "WLD",
    }


def test_a03_monthly_periods_are_preserved():
    req = request(start="2019-01", end="2019-03", frequency="M")
    items = [
        candidate("CHN", "FP.CPI.TOTL", f"2019-{month:02d}", frequency="M") for month in range(1, 4)
    ]
    result = evaluate(req, items)
    assert result["delivery_eligibility"] == "analysis_ready"
    assert [item["time_raw"] for item in result["selected_items"]] == [
        "2019-01",
        "2019-02",
        "2019-03",
    ]


def test_a04_quarterly_periods_are_preserved():
    req = request(start="2019-Q1", end="2019-Q4", frequency="Q")
    items = [
        candidate("CHN", "FP.CPI.TOTL", f"2019Q{quarter}", frequency="Q") for quarter in range(1, 5)
    ]
    result = evaluate(req, items)
    assert result["delivery_eligibility"] == "analysis_ready"
    assert {item["time_raw"] for item in result["selected_items"]} == {
        "2019Q1",
        "2019Q2",
        "2019Q3",
        "2019Q4",
    }


def test_a05_same_indicator_with_two_series_is_blocked():
    req = request(start="2019", end="2019")
    items = [
        candidate("CHN", "FP.CPI.TOTL", "2019"),
        candidate("CHN", "FP.CPI.TOTL", "2019", series_suffix="|ALT"),
    ]
    result = evaluate(req, items)
    assert "indicator_ambiguity" in result["issue_codes"]
    assert result["delivery_eligibility"] == "not_deliverable"


def test_a06_same_indicator_with_different_units_is_blocked():
    req = request(start="2019", end="2019")
    level = candidate("CHN", "FP.CPI.TOTL", "2019")
    percent = candidate("CHN", "FP.CPI.TOTL", "2019", series_suffix="|PERCENT")
    percent["unit"] = {"value": "percent", "status": "source_provided"}
    result = evaluate(req, [level, percent])
    assert "unit_conflict" in result["issue_codes"]
    assert result["research_readiness"] == "blocked"


def test_a07_nominal_and_real_variants_are_blocked():
    req = request(start="2019", end="2019")
    nominal = candidate("CHN", "FP.CPI.TOTL", "2019")
    real = candidate("CHN", "FP.CPI.TOTL", "2019", series_suffix="|REAL")
    nominal["price_basis"] = {
        "value": {"type": "nominal", "base_period": None, "chain_linked": None},
        "status": "source_provided",
    }
    real["price_basis"] = {
        "value": {"type": "real", "base_period": "2015", "chain_linked": False},
        "status": "source_provided",
    }
    result = evaluate(req, [nominal, real])
    assert "price_basis_conflict" in result["issue_codes"]
    assert result["delivery_eligibility"] == "not_deliverable"


def test_a08_sa_and_nsa_variants_are_blocked():
    req = request(start="2019", end="2019")
    sa = candidate("CHN", "FP.CPI.TOTL", "2019")
    nsa = candidate("CHN", "FP.CPI.TOTL", "2019", series_suffix="|NSA")
    sa["seasonal_adjustment"] = {"value": "SA", "status": "source_provided"}
    nsa["seasonal_adjustment"] = {"value": "NSA", "status": "source_provided"}
    result = evaluate(req, [sa, nsa])
    assert "seasonal_adjustment_conflict" in result["issue_codes"]
    assert result["delivery_eligibility"] == "not_deliverable"


def _assert_request_mismatch_is_blocked(req, item, issue_code):
    validate_document("request", req)
    result = evaluate(req, [item])
    assert issue_code in result["issue_codes"]
    assert result["research_readiness"] == "blocked"
    assert result["delivery_eligibility"] == "not_deliverable"
    assert result["eligible_for_estimation"] is False


def test_explicit_unit_must_match_the_single_candidate():
    req = request(start="2019", end="2019")
    req["unit"] = "percent"
    item = candidate("CHN", "FP.CPI.TOTL", "2019")

    _assert_request_mismatch_is_blocked(req, item, "unit_mismatch")


def test_explicit_seasonal_adjustment_must_match_the_single_candidate():
    req = request(start="2019", end="2019")
    req["seasonal_adjustment"] = "SA"
    item = candidate("CHN", "FP.CPI.TOTL", "2019")
    item["seasonal_adjustment"] = {
        "value": "NSA",
        "status": "source_provided",
    }

    _assert_request_mismatch_is_blocked(
        req,
        item,
        "seasonal_adjustment_mismatch",
    )


def test_explicit_price_basis_must_match_the_single_candidate():
    req = request(start="2019", end="2019")
    req["price_basis"] = {
        "type": "real",
        "base_period": "2015",
        "chain_linked": False,
    }
    item = candidate("CHN", "FP.CPI.TOTL", "2019")

    _assert_request_mismatch_is_blocked(req, item, "price_basis_mismatch")


def test_required_definition_must_match_the_single_candidate():
    req = request(start="2019", end="2019")
    req["indicators"][0]["required_definition"] = "Required definition"
    item = candidate("CHN", "FP.CPI.TOTL", "2019")

    _assert_request_mismatch_is_blocked(req, item, "definition_mismatch")


def test_concept_definition_constraint_requires_an_explicit_indicator_mapping():
    req = request(start="2019", end="2019")
    req["concepts"][0]["definition_constraints"] = ["Must use a constant-price definition"]
    item = candidate("CHN", "FP.CPI.TOTL", "2019")

    _assert_request_mismatch_is_blocked(
        req,
        item,
        "concept_definition_mapping_unresolved",
    )


def test_explicit_currency_must_match_the_single_candidate():
    req = request(start="2019", end="2019")
    req["currency"] = "USD"
    item = candidate("CHN", "FP.CPI.TOTL", "2019")
    item["currency"] = "EUR"

    _assert_request_mismatch_is_blocked(req, item, "currency_mismatch")


def test_a09_entity_mapping_conflict_is_blocked():
    req = request(start="2019", end="2019")
    item = candidate("CHN", "FP.CPI.TOTL", "2019")
    item["entity_mapping_status"] = "conflict"
    result = evaluate(req, [item])
    assert "entity_mapping_conflict" in result["issue_codes"]
    assert result["delivery_eligibility"] == "not_deliverable"


def test_a10_missing_value_and_break_are_comparison_only():
    req = request(start="2019", end="2020")
    missing = candidate("CHN", "FP.CPI.TOTL", "2019", value=None)
    broken = candidate("CHN", "FP.CPI.TOTL", "2020")
    broken["obs_status"] = "break"
    result = evaluate(req, [missing, broken])
    assert {"missing_values", "structural_break"} <= set(result["issue_codes"])
    assert result["delivery_eligibility"] == "comparison_only"


def test_a11_cross_source_value_conflict_is_comparison_only():
    req = request(start="2019", end="2019")
    req["native_source_constraints"] = []
    world_bank = candidate("CHN", "FP.CPI.TOTL", "2019", value=100.0)
    imf = candidate(
        "CHN",
        "FP.CPI.TOTL",
        "2019",
        value=101.0,
        source="IMF",
        series_suffix="|IMF",
    )
    result = evaluate(req, [world_bank, imf])
    assert "cross_source_conflict" in result["issue_codes"]
    assert result["delivery_eligibility"] == "comparison_only"


def test_a12_as_of_request_without_vintage_is_not_deliverable():
    req = request(start="2019", end="2019")
    req["release_or_vintage"] = {"mode": "as_of", "value": "2020-01-01"}
    result = evaluate(req, complete_items(req))
    assert result["execution_status"] == "failed"
    assert result["delivery_eligibility"] == "not_deliverable"


def test_a13_provider_error_with_fallback_never_fails():
    req = request()
    req["fallback_policy"] = {
        "mode": "never",
        "allowed_sources": [],
        "allow_semantic_substitute": False,
        "allow_cross_source_stitching": False,
    }
    result = evaluate(req, [], provider="datapro", provider_code=500)
    assert result["execution_status"] == "failed"
    assert result["delivery_eligibility"] == "not_deliverable"


def test_a14_fallback_ask_requires_review_before_execution():
    router_module = importlib.import_module("macro_data.source_router")
    req = request()
    req["fallback_policy"]["mode"] = "ask"
    plan = router_module.SourceRouter(SourceRegistry.default()).plan(req)
    assert plan.fallback_candidates == ["world_bank"]
    assert plan.review_required is True


def test_a15_cross_source_stitching_is_rejected_by_schema():
    req = request()
    req["fallback_policy"]["allow_cross_source_stitching"] = True
    with pytest.raises(ValueError, match="allow_cross_source_stitching"):
        validate_document("request", req)


def test_a16_unknown_license_is_not_deliverable():
    req = request(start="2019", end="2019")
    item = candidate("CHN", "FP.CPI.TOTL", "2019")
    item["license"] = {
        "id": None,
        "url": None,
        "attribution": None,
        "use_status": "unknown",
        "allows_requested_use": False,
    }
    result = evaluate(req, [item])
    assert "license_unresolved" in result["issue_codes"]
    assert result["delivery_eligibility"] == "not_deliverable"


def _replay_bundle(tmp_path, name):
    parser = importlib.import_module("macro_data.request_parser")
    pipeline = importlib.import_module("macro_data.pipeline")
    req = parser.parse_research_request("查询中国2019年到2024年的月度居民消费价格指数。")
    output = tmp_path / name
    pipeline.run_macro_data_request(
        request=req,
        source_payload=load_json(FIXTURES / "sanitized-live" / "02_china_monthly_cpi.json"),
        output_dir=output,
        input_mode="sanitized-live-replay",
    )
    return output


def test_a17_missing_checksum_invalidates_bundle(tmp_path):
    exporter = importlib.import_module("macro_data.exporter")
    output = _replay_bundle(tmp_path, "missing-checksum")
    manifest_path = output / "run_manifest.json"
    manifest = load_json(manifest_path)
    manifest["artifacts"].pop("data.csv")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert exporter.validate_bundle(output)["valid"] is False


def test_a18_incomplete_provenance_invalidates_bundle(tmp_path):
    exporter = importlib.import_module("macro_data.exporter")
    output = _replay_bundle(tmp_path, "missing-provenance")
    provenance_path = output / "provenance.json"
    provenance = load_json(provenance_path)
    provenance.pop("activities")
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    manifest_path = output / "run_manifest.json"
    manifest = load_json(manifest_path)
    manifest["artifacts"]["provenance.json"] = sha256_file(provenance_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert exporter.validate_bundle(output)["valid"] is False


def test_a19_repeated_runs_have_identical_artifact_checksums(tmp_path):
    first = _replay_bundle(tmp_path, "first")
    second = _replay_bundle(tmp_path, "second")
    assert (
        load_json(first / "run_manifest.json")["artifacts"]
        == load_json(second / "run_manifest.json")["artifacts"]
    )


def test_a20_future_release_is_excluded_from_as_of_output():
    req = request(start="2019", end="2021")
    req["release_or_vintage"] = {"mode": "as_of", "value": "2021-12-31"}
    items = complete_items(req)
    for item in items:
        item["release_date"] = {
            "value": "2021-01-01",
            "status": "source_provided",
        }
        item["vintage"] = {
            "value": "2021-01-01",
            "status": "source_provided",
        }
    bait = candidate("CHN", "FP.CPI.TOTL", "2020", value=999.0)
    bait["release_date"] = {
        "value": "2022-01-01",
        "status": "source_provided",
    }
    bait["vintage"] = {"value": "2022-01-01", "status": "source_provided"}
    result = evaluate(req, [*items, bait])
    assert 999.0 not in {item["value"] for item in result["selected_items"]}
    assert "future_information_excluded" in result["issue_codes"]


def test_a21_partial_entity_success_preserves_request_denominator():
    req = request(entities=(("CHN", "country"), ("USA", "country")))
    items = [candidate("CHN", "FP.CPI.TOTL", str(year)) for year in range(2019, 2022)]
    result = evaluate(req, items)
    assert result["execution_status"] == "partial"
    assert result["source_coverage"] == {
        "complete": False,
        "scope_reduced": False,
        "requested_count": 2,
        "delivered_count": 1,
        "failures": ["USA|FP.CPI.TOTL"],
    }


def test_a22_explicit_unit_scaling_preserves_formula():
    req = request(start="2019", end="2019")
    req["transformation_policy"]["allow_unit_scaling"] = True
    req["transformation_policy"]["requested_transformations"] = ["unit_scale"]
    req["transformation_parameters"] = {
        "unit_scale": {
            "multiplier": 1000,
            "from_unit": "thousand persons",
            "to_unit": "persons",
        }
    }
    item = candidate("CHN", "FP.CPI.TOTL", "2019", value=2.5)
    transformed, records = apply_transformations(req, [item])
    assert transformed[0]["value"] == 2500
    assert records[0]["formula"] == "value * 1000"


def test_a23_confirmed_monthly_flow_downsamples_to_quarter():
    req = request(start="2019-Q1", end="2019-Q1", frequency="Q")
    req["transformation_policy"]["allow_downsampling"] = True
    req["transformation_policy"]["requested_transformations"] = ["downsample"]
    req["transformation_parameters"] = {
        "downsample": {
            "source_frequency": "M",
            "target_frequency": "Q",
            "method": "sum",
        }
    }
    items = [
        candidate(
            "CHN",
            "FP.CPI.TOTL",
            f"2019-{month:02d}",
            value=float(month),
            frequency="M",
        )
        for month in range(1, 4)
    ]
    transformed, records = apply_transformations(req, items)
    assert [(item["time_raw"], item["value"]) for item in transformed] == [("2019Q1", 6.0)]
    assert records == [
        {
            "type": "downsample",
            "source_frequency": "M",
            "target_frequency": "Q",
            "method": "sum",
        }
    ]


def test_a24_annual_to_quarter_upsampling_is_rejected_by_schema():
    req = request()
    req["transformation_policy"]["allow_upsampling"] = True
    with pytest.raises(ValueError, match="allow_upsampling"):
        validate_document("request", req)


def test_a25_missing_upstream_identity_field_fails_contract(tmp_path):
    parser = importlib.import_module("macro_data.request_parser")
    pipeline = importlib.import_module("macro_data.pipeline")
    req = parser.parse_research_request("严格查询世界银行WDI：中国2019年至2019年的年度CPI。")
    payload = {
        "code": 0,
        "msg": "success",
        "dataset_type": "macro",
        "items": [
            {
                "source_system": "WORLD_BANK",
                "dataset_id": "2",
                "dataset_name": "World Development Indicators",
                "entity_code": "CHN",
                "indicator_code": "FP.CPI.TOTL",
                "time_raw": "2019",
                "time_grain": "year",
                "value": 100.0,
            }
        ],
    }
    output = tmp_path / "schema-drift"
    with pytest.raises(ValueError, match="series_key"):
        pipeline.run_macro_data_request(
            request=req,
            source_payload=payload,
            output_dir=output,
            input_mode="synthetic",
        )
    assert not output.exists()
