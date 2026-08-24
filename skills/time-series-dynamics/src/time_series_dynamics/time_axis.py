"""Frequency-aware labels for dynamic-path outputs."""

from __future__ import annotations


def horizon_unit(frequency: str) -> str:
    try:
        return {"M": "months", "Q": "quarters"}[frequency]
    except KeyError as error:
        raise ValueError(f"unsupported frequency: {frequency}") from error


def horizon_unit_zh(frequency: str) -> str:
    try:
        return {"M": "个月", "Q": "个季度"}[frequency]
    except KeyError as error:
        raise ValueError(f"unsupported frequency: {frequency}") from error
