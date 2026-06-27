from __future__ import annotations

import re


GENERIC_SUFFIXES = [
    "私募证券投资基金",
    "证券投资基金",
    "私募基金",
    "基金",
]

NOISE_NAMES = {
    "发送时间",
    "到期时间",
}

NOISE_FRAGMENTS = {
    "净值试算",
    "虚拟净值",
    "业绩报酬",
    "请查收",
    "试算结果",
    "净值结果",
    "估值表",
    "估值数据",
    "托管发送",
    "净值播报",
}


def normalize_product_name(text: str) -> str:
    normalized = re.sub(r"\s+", "", text.strip())
    if normalized.endswith("份额") and len(normalized) > 2:
        normalized = normalized[:-2]
    return normalized


def is_noise_name(text: str) -> bool:
    value = normalize_product_name(text)
    if not value or value in NOISE_NAMES:
        return True
    if any(fragment in value for fragment in NOISE_FRAGMENTS):
        return True
    if re.fullmatch(r"[0-9A-Za-z]{1,4}", value):
        return True
    if re.fullmatch(r"\d+", value):
        return True
    if len(value) <= 3 and not re.search(r"[\u4e00-\u9fa5]", value):
        return True
    if value.lower().endswith((".xls", ".xlsx", ".csv")):
        return True
    return False


def product_name_key(text: str) -> str:
    value = normalize_product_name(text)
    value = re.sub(r"[【】\[\]（）()·_.\-]", "", value)
    for suffix in GENERIC_SUFFIXES:
        value = value.replace(suffix, "")
    return value


def is_formal_product_name(text: str) -> bool:
    value = normalize_product_name(text)
    return any(suffix in value for suffix in GENERIC_SUFFIXES)


def looks_like_product_name(text: str) -> bool:
    value = normalize_product_name(text)
    if is_noise_name(value):
        return False
    if any(suffix in value for suffix in GENERIC_SUFFIXES):
        return True
    return len(value) >= 6 and bool(re.search(r"[\u4e00-\u9fa5]", value))


def choose_preferred_display_name(current_name: str, candidate_name: str) -> str:
    current = normalize_product_name(current_name)
    candidate = normalize_product_name(candidate_name)
    if not current:
        return candidate
    if current == candidate:
        return current

    current_formal = is_formal_product_name(current)
    candidate_formal = is_formal_product_name(candidate)

    if candidate_formal and not current_formal:
        return candidate
    if current_formal and not candidate_formal:
        return current
    if len(candidate) > len(current):
        return candidate
    return current
