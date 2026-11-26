"""Build a part index, retrieve plate candidates, and gate each merge proposal."""

from collections import Counter, defaultdict
from dataclasses import replace
from math import isclose

from .alias_features import ReferenceAlias, hash_plate, rank_parts
from .alias_seed import sample_rows as sample_rows
from .alias_validation import MatchOptions, PlateRecord, validate_options, validate_rows

PROPOSED = "建议归并"
NO_HISTORY = "同厂无历史别名"
LOW_SCORE = "首选低于门槛"
CLOSE_CANDIDATES = "候选件号分差不足"
NO_RELEASE = "厂牌未放行门槛"


def _index(history: list[PlateRecord], settings: MatchOptions) -> dict[str, list[ReferenceAlias]]:
    by_manufacturer: dict[str, list[ReferenceAlias]] = defaultdict(list)
    for record in history:
        vector = hash_plate(record.normalized_plate, settings.dimension, settings.max_ngram)
        by_manufacturer[record.manufacturer_key].append(ReferenceAlias(
            record.record_id, record.plate_text, record.part_number, vector
        ))
    return by_manufacturer


def _match_row(record: PlateRecord, aliases: list[ReferenceAlias], settings: MatchOptions,
               released: bool = True) -> dict:
    query = hash_plate(record.normalized_plate, settings.dimension, settings.max_ngram)
    ranked = rank_parts(query, aliases)
    first = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    margin = first.score - second.score if first and second else None
    if not released:
        reason = NO_RELEASE
    elif first is None:
        reason = NO_HISTORY
    elif first.score < settings.min_score:
        reason = LOW_SCORE
    elif margin is not None and (isclose(margin, 0, abs_tol=1e-12) or margin < settings.min_margin):
        reason = CLOSE_CANDIDATES
    else:
        reason = PROPOSED

    return {
        "待验记录号": record.record_id,
        "来源批次": record.batch_id,
        "铭牌厂牌": record.manufacturer,
        "铭牌原文": record.plate_text,
        "归一化铭牌": record.normalized_plate,
        "首选件号": first.alias.part_number if first else "",
        "命中历史记录": first.alias.record_id if first else "",
        "命中历史铭牌": first.alias.plate_text if first else "",
        "首选相似度": round(first.score, 6) if first else "",
        "次选件号": second.alias.part_number if second else "",
        "次选相似度": round(second.score, 6) if second else "",
        "候选分差": round(margin, 6) if margin is not None else "",
        "处理结果": PROPOSED if reason == PROPOSED else "拒识待复核",
        "判定依据": reason,
        "建议件号": first.alias.part_number if reason == PROPOSED else "",
    }


def _threshold_notes(locked: dict) -> list[str]:
    manufacturers = locked.get("manufacturers", {})
    notes = [
        f"门槛锁定校准版本 #{locked['version']}（数据版本 #{locked['dataset_id']}，{locked['hash_dimension']} 桶、"
        f"片段 {locked['ngram_range']}，模拟新件号误挂率上限 {locked.get('max_false_attach', 0):.0%}），按厂覆盖手动相似度和分差。"
    ]
    for entry in sorted(manufacturers.values(), key=lambda item: item["manufacturer"]):
        if entry.get("released"):
            notes.append(
                f"{entry['manufacturer']}：相似度≥{entry['min_score']:g}、分差≥{entry['min_margin']:g}"
                f"（留批认对 {entry['known_correct']}/{entry['known_usable']}，"
                f"模拟新件号误挂 {entry['new_attached']}/{entry['new_usable']}）。"
            )
        else:
            notes.append(f"{entry['manufacturer']}：{entry['reason']}，未放行建议，该厂铭牌一律转人工复核。")
    notes.append("未列入校准版本的厂牌同样不放行建议。")
    return notes


def compute(rows: list[dict], options: dict, locked: dict | None = None) -> dict:
    settings = validate_options(options)
    manufacturers = None
    if locked:
        settings = replace(settings, dimension=locked["hash_dimension"],
                           max_ngram=int(locked["ngram_range"][-1]))
        manufacturers = locked.get("manufacturers", {})
    history, incoming = validate_rows(rows)
    index = _index(history, settings)
    results = []
    for record in incoming:
        aliases = index.get(record.manufacturer_key, [])
        if manufacturers is None:
            results.append(_match_row(record, aliases, settings))
            continue
        entry = manufacturers.get(record.manufacturer_key)
        if entry and entry.get("released"):
            tuned = replace(settings, min_score=entry["min_score"], min_margin=entry["min_margin"])
            results.append(_match_row(record, aliases, tuned))
        else:
            results.append(_match_row(record, aliases, settings, released=False))
    outcomes = Counter(row["判定依据"] for row in results)
    suggested = outcomes[PROPOSED]
    review = len(incoming) - suggested
    if locked is None:
        threshold_note = (f"首选相似度至少 {settings.min_score:g}，有次选时分差至少 {settings.min_margin:g}。"
                          "同分始终拒识，只有一个同厂件号时仅检查相似度。判定使用舍入前分数。")
        notes = [threshold_note]
    else:
        notes = _threshold_notes(locked) + ["同分始终拒识，只有一个同厂件号时仅检查相似度。判定使用舍入前分数。"]
    return {
        "headline": f"{len(incoming)} 张待验铭牌中，{suggested} 张可提议归并，{review} 张需人工复核",
        "metrics": {
            "历史别名数": len(history),
            "同厂件号组合数": len({(row.manufacturer_key, row.part_number) for row in history}),
            "待验铭牌数": len(incoming),
            "建议归并数": suggested,
            "拒识复核数": review,
            "建议覆盖率（%）": round(100 * suggested / len(incoming), 2),
            "门槛来源": f"校准版本 #{locked['version']}" if locked else "手动参数",
        },
        "rows": results,
        "notes": [
            f"统一全半角、大小写并保留字母和数字，含首尾标记的长度 2–{settings.max_ngram} 字符片段以 BLAKE2b 哈希计入 {settings.dimension} 桶。",
            "仅检索同厂别名。每个规范件号取历史别名的最高余弦相似度，同分历史别名按记录号排序，候选同分时按件号展示。",
            *notes,
            "有限哈希桶可能发生碰撞。建议件号由质检员核对照片后签认，拒识记录留待复拍或补录厂牌。",
        ],
        "chart": {
            "label": "待验铭牌处理结果",
            "unit": "张",
            "points": [
                {"label": outcome, "value": outcomes[outcome]}
                for outcome in (PROPOSED, NO_HISTORY, LOW_SCORE, CLOSE_CANDIDATES, NO_RELEASE)
            ],
        },
        "can_publish": suggested > 0,
    }
