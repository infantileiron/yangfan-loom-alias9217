"""Simulated historical aliases and a receiving batch for the loom workshop."""

PENDING_PART = "待归并"
HISTORY = "历史别名"
INCOMING = "待验铭牌"

# One group represents the plate spellings found in past workshop receipts.
_HISTORY_GROUPS = (
    ("DA-2609-LP", "澜浦织机", "LP-GR-381", ("GR-381", "GR381-A", "LP GR381", "GR381 左")),
    ("DA-2609-LP", "澜浦织机", "LP-GR-382", ("GR-382", "GR382-B", "LP GR382", "GR382 右")),
    ("DA-2610-RH", "荣桓纺机", "RH-SH-072", ("SH-072", "SH072-A", "RH SH072", "SH072 导梭")),
    ("DA-2610-RH", "荣桓纺机", "RH-WB-214", ("WB-214", "WB214-S", "RH WB214", "WB214 卷布")),
    ("DA-2611-HT", "海棠机造", "HT-TN-540", ("TN-540", "TN540-F", "HT TN540", "TN540 经轴")),
    ("DA-2611-HT", "海棠机造", "HT-SC-906", ("SC-906", "SC906-X", "HT SC906", "SC906 梭架")),
)

# Order follows the receiving desk's tag sequence on November 25.
_INCOMING_PLATES = (
    ("澜浦织机", "ＧＲ－３８１"),
    ("澜浦织机", "gr 382-b"),
    ("澜浦织机", "GR-38"),
    ("荣桓纺机", "SH·072"),
    ("荣桓纺机", "wb214 卷布"),
    ("荣桓纺机", "SH072-X"),
    ("荣桓纺机", "ZK-999"),
    ("海棠机造", "TN.540-F"),
    ("海棠机造", "sc906x"),
    ("海棠机造", "HT SC906"),
    ("海棠机造", "tn540 经轴"),
    ("德潭织造", "TN-540"),
)


def sample_rows() -> list[dict]:
    rows = []
    for batch_id, manufacturer, part_number, spellings in _HISTORY_GROUPS:
        for sequence, plate_text in enumerate(spellings, start=1):
            rows.append({
                "record_id": f"DA-{part_number}-{sequence:02d}",
                "batch_id": batch_id,
                "manufacturer": manufacturer,
                "record_type": HISTORY,
                "plate_text": plate_text,
                "part_number": part_number,
            })
    for sequence, (manufacturer, plate_text) in enumerate(_INCOMING_PLATES, start=1):
        rows.append({
            "record_id": f"SK-261125-A-{sequence:02d}",
            "batch_id": "SK-261125-A",
            "manufacturer": manufacturer,
            "record_type": INCOMING,
            "plate_text": plate_text,
            "part_number": PENDING_PART,
        })
    return rows
