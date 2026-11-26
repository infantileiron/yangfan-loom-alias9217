"""Validate incoming plate ledgers and the matching configuration."""

from dataclasses import dataclass
from math import isfinite
from re import fullmatch
from unicodedata import normalize

from .alias_features import normalize_text
from .alias_seed import HISTORY, INCOMING, PENDING_PART


@dataclass(frozen=True)
class PlateRecord:
    record_id: str
    batch_id: str
    manufacturer: str
    manufacturer_key: str
    plate_text: str
    normalized_plate: str
    part_number: str


@dataclass(frozen=True)
class MatchOptions:
    dimension: int
    max_ngram: int
    min_score: float
    min_margin: float


def _number(options: dict, key: str, label: str, default: float, lo: float, hi: float) -> float:
    value = options.get(key, default)
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"请将{label}填写为 {lo:g} 到 {hi:g} 之间的数值。") from None
    if not isfinite(number) or not lo <= number <= hi:
        raise ValueError(f"请将{label}调整到 {lo:g} 到 {hi:g} 之间。")
    return number


def validate_options(options: dict) -> MatchOptions:
    dimension = _number(options, "hash_dimension", "哈希桶数", 4096, 32, 16384)
    if not dimension.is_integer():
        raise ValueError("请将哈希桶数填写为 32 到 16384 之间的整数。")
    ngram = options.get("ngram_range", "2-3")
    if ngram not in ("2-3", "2-4"):
        raise ValueError("请选择字符片段范围 2-3 或 2-4。")
    return MatchOptions(
        dimension=int(dimension),
        max_ngram=int(ngram[-1]),
        min_score=_number(options, "min_score", "最低相似度", 0.55, 0.01, 1),
        min_margin=_number(options, "min_margin", "最低候选分差", 0.08, 0, 1),
    )


def _required(row: dict, key: str, label: str, line: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"请补填第 {line} 条记录的{label}。")
    return value.strip()


def validate_rows(rows: list[dict]) -> tuple[list[PlateRecord], list[PlateRecord]]:
    history: list[PlateRecord] = []
    incoming: list[PlateRecord] = []
    record_ids: set[str] = set()
    for line, row in enumerate(rows, start=1):
        record_id = _required(row, "record_id", "记录号", line)
        if record_id in record_ids:
            raise ValueError(f"记录号 {record_id} 重复，请保留一条或重新编号。")
        record_ids.add(record_id)
        batch_id = _required(row, "batch_id", "来源批次", line)
        manufacturer = _required(row, "manufacturer", "铭牌厂牌", line)
        manufacturer_key = normalize_text(manufacturer)
        if not manufacturer_key:
            raise ValueError(f"记录 {record_id} 的厂牌只含符号，请补填可识别的厂牌。")
        record_type = _required(row, "record_type", "记录类别", line)
        plate_text = _required(row, "plate_text", "铭牌转写", line)
        normalized_plate = normalize_text(plate_text)
        if len(normalized_plate) < 2:
            raise ValueError(f"记录 {record_id} 的铭牌转写不足两个有效字符，请对照照片补录。")
        part_number = normalize("NFKC", _required(row, "part_number", "规范件号", line)).upper()
        if record_type == HISTORY:
            if not fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", part_number):
                raise ValueError(f"历史记录 {record_id} 缺少有效规范件号，请从库存台账补填，如 LP-GR-381。")
            target = history
        elif record_type == INCOMING:
            if part_number != PENDING_PART:
                raise ValueError(f"待验记录 {record_id} 的规范件号请填写“{PENDING_PART}”。")
            target = incoming
        else:
            raise ValueError(f"记录 {record_id} 类别无效，请填写“{HISTORY}”或“{INCOMING}”。")
        target.append(PlateRecord(
            record_id, batch_id, manufacturer, manufacturer_key, plate_text, normalized_plate, part_number
        ))
    if not history or not incoming:
        raise ValueError(f"请在同一份台账至少放入一条“{HISTORY}”和一条“{INCOMING}”。")
    return history, incoming
