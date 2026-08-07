"""Prefixed, sortable identifiers (ULID-like) used across the platform.

Prefixes make IDs self-describing in logs, events and audit trails:
    org_…, usr_…, proj_…, ds_…, dsv_…, src_…, doc_…, chk_…, run_…,
    agrun_…, evt_…, exp_…, rev_…, key_…, plg_…
"""
from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"  # crockford-ish, lowercase


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_id(prefix: str) -> str:
    ts = _encode(int(time.time() * 1000), 10)
    rand = "".join(secrets.choice(_ALPHABET) for _ in range(14))
    return f"{prefix}_{ts}{rand}"
