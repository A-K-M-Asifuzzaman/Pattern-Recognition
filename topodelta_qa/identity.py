"""Public identifiers require an evaluator-only key, not a guessable parent/index hash."""
import copy
import hashlib
import hmac
import json
from pathlib import Path

POLICY = "hmac-sha256-96-v1"


def read_key(path: Path) -> str:
    key = json.loads(path.read_text())["key_hex"]
    if not isinstance(key, str) or len(key) != 64:
        raise ValueError("Identity key must be 32 bytes encoded as 64 hex characters")
    try:
        if len(bytes.fromhex(key)) != 32:
            raise ValueError("Identity key must decode to 32 bytes")
    except ValueError as exc:
        raise ValueError("Invalid identity key encoding") from exc
    return key


def public_id(value: str, key: str) -> str:
    return hmac.new(bytes.fromhex(key), value.encode(), hashlib.sha256).hexdigest()[:24]


def remap_group(group: dict, key: str) -> dict:
    result = copy.deepcopy(group)
    qids = {q["id"]: public_id(q["id"], key) for q in result["questions"]}
    result["id"] = public_id(result["id"], key)
    for q in result["questions"]:
        q["id"] = qids[q["id"]]
    for v in result["variants"]:
        old = v["id"]
        v["id"] = public_id(old, key)
        v["assets"] = {ext: f'images/{v["id"]}.{ext}' for ext in ("png", "svg")}
        for field in ("answers", "certificates", "relevance"):
            v[field] = {qids[q]: value for q, value in v[field].items()}
        if "pixel_diff" in v:
            v["pixel_diff"]["path"] = f'gold/pixel_diffs/{v["id"]}.png'
    return result
