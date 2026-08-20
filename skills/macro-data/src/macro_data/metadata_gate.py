"""Research-use-specific metadata qualification rules."""

from __future__ import annotations

from typing import Any

from macro_data.product_authorization import authorization_issues

_DOCUMENTED = {"source_provided", "source_documented", "transformed"}
_DOCUMENTED_OR_NA = _DOCUMENTED | {"not_applicable"}


def is_documented_status(
    status: str | None,
    *,
    allow_not_applicable: bool = False,
) -> bool:
    accepted = _DOCUMENTED_OR_NA if allow_not_applicable else _DOCUMENTED
    return status in accepted


def _license_or_use_authorization_allows(
    request: dict[str, Any],
    item: dict[str, Any],
) -> bool:
    license_document = item.get("license")
    license_allowed = (
        isinstance(license_document, dict)
        and license_document.get("use_status") == "allowed"
        and license_document.get("allows_requested_use") is True
    )
    if license_allowed:
        return True
    return item.get("provider") == "datapro" and not authorization_issues(request, item)


def metadata_issues(
    request: dict[str, Any],
    selected: list[dict[str, Any]],
) -> set[str]:
    research_use = request["research_use"]
    issues: set[str] = set()

    if any(
        not is_documented_status(
            item["unit"]["status"],
            allow_not_applicable=True,
        )
        for item in selected
    ):
        issues.add("unit_unknown")
    if any(
        not is_documented_status(
            item["seasonal_adjustment"]["status"],
            allow_not_applicable=True,
        )
        for item in selected
    ):
        issues.add("seasonal_adjustment_unknown")
    if any(not is_documented_status(item["definition"]["status"]) for item in selected):
        issues.add("definition_unknown")
    if any(not _license_or_use_authorization_allows(request, item) for item in selected):
        issues.add("license_unresolved")

    vintage_mode = request["release_or_vintage"]["mode"]
    requires_point_in_time = research_use in {
        "forecasting",
        "real_time",
    } or vintage_mode in {"as_of", "specific_vintage"}
    if requires_point_in_time:
        if any(item["release_date"]["status"] != "source_provided" for item in selected):
            issues.add("release_date_required")
        if any(item["vintage"]["status"] != "source_provided" for item in selected):
            issues.add("vintage_required")
    if research_use == "real_time" and vintage_mode == "latest":
        issues.add("as_of_required")

    return issues
