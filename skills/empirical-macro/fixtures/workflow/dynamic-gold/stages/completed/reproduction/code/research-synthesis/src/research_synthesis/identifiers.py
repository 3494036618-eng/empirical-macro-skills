"""生成稳定 scientific IDs 和物理 checksums。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RUNTIME_FIELDS = {
    "duration_seconds",
    "execution_error",
    "generated_at",
    "stderr",
    "stdout",
}


def canonical_json_bytes(value: object) -> bytes:
    """按跨模块冻结规则序列化 JSON-compatible value。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    """计算 canonical JSON SHA-256。"""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def content_id(prefix: str, value: object) -> str:
    """生成包含全部字段的内容 ID。"""
    return f"{prefix}-{canonical_sha256(value)[:32]}"


def without_runtime_fields(value: object) -> object:
    """递归移除不应进入 scientific identity 或交付包的运行时字段。"""
    if isinstance(value, dict):
        return {
            key: without_runtime_fields(item)
            for key, item in value.items()
            if key not in RUNTIME_FIELDS
        }
    if isinstance(value, list):
        return [without_runtime_fields(item) for item in value]
    return value


def runtime_sanitized_json_bytes(value: object) -> bytes:
    """序列化剥离 runtime fields 后的稳定、可交付 JSON。"""
    return (
        json.dumps(
            without_runtime_fields(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def scientific_sha256(value: object) -> str:
    """计算排除运行时噪声的 canonical JSON SHA-256。"""
    return canonical_sha256(without_runtime_fields(value))


def scientific_content_id(prefix: str, value: object) -> str:
    """生成排除运行时噪声的 scientific ID。"""
    return f"{prefix}-{scientific_sha256(value)[:32]}"


def sha256_file(path: Path) -> str:
    """计算文件物理字节 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()
