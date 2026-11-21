"""
C-03: limit failed logins (in memory, thread-safe).

* Per identifier (email / phone / NIK / NIP, case-insensitive): SCMS_LOGIN_MAKS_GAGAL failures
  (default 5) within SCMS_LOGIN_JEDA_MENIT minutes (default 15). The next attempt is refused with
  HTTP 429 before the password is even checked.
* Per client IP, looser: SCMS_LOGIN_MAKS_GAGAL_IP failures (default 20) in the same window, so one
  address cannot try many identifiers.
* A successful login resets the counter of that identifier.

Settings are read on every call (monkeypatch.setenv works in tests). The state lives in this
process only: a restart clears it, and with several workers each counts on its own, which is
still a hard ceiling on guessing speed. `reset_semua()` is for the test suite.
"""
import math
import os
import threading
import time
from collections import deque
from typing import Optional

from fastapi import Request

MAKS_GAGAL_BAWAAN = 5
MAKS_GAGAL_IP_BAWAAN = 20
JEDA_MENIT_BAWAAN = 15
_BATAS_KUNCI = 10_000  # above this many tracked keys, expired ones are swept

_kunci = threading.Lock()
_gagal: dict = {}  # ("id" | "ip", value) -> deque of failure timestamps (time.monotonic)


def _angka_env(nama: str, bawaan: int) -> int:
    try:
        nilai = int(os.getenv(nama, bawaan))
    except (TypeError, ValueError):
        return bawaan
    return nilai if nilai >= 1 else bawaan


def maks_gagal() -> int:
    return _angka_env("SCMS_LOGIN_MAKS_GAGAL", MAKS_GAGAL_BAWAAN)


def maks_gagal_ip() -> int:
    return _angka_env("SCMS_LOGIN_MAKS_GAGAL_IP", MAKS_GAGAL_IP_BAWAAN)


def jeda_detik() -> int:
    return _angka_env("SCMS_LOGIN_JEDA_MENIT", JEDA_MENIT_BAWAAN) * 60


def ip_klien(request: Request) -> str:
    """Client IP behind Cloudflare and Coolify: CF-Connecting-IP, then the first
    X-Forwarded-For entry, then the socket peer."""
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf:
        return cf
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff
    return request.client.host if request.client else "-"


def _kunci_id(identifier: str) -> tuple:
    return ("id", (identifier or "").strip().lower())


def _bersihkan(antrean: deque, sekarang: float, jeda: int) -> None:
    while antrean and antrean[0] <= sekarang - jeda:
        antrean.popleft()


def _sisa_detik(kunci: tuple, maks: int, sekarang: float, jeda: int) -> float:
    antrean = _gagal.get(kunci)
    if not antrean:
        return 0
    _bersihkan(antrean, sekarang, jeda)
    if len(antrean) < maks:
        return 0
    # locked until enough failures leave the window to drop below the maximum
    return antrean[len(antrean) - maks] + jeda - sekarang


def menit_terkunci(identifier: str, ip: str) -> Optional[int]:
    """Whole minutes until a login for this identifier/IP is allowed again, or None if allowed."""
    jeda, sekarang = jeda_detik(), time.monotonic()
    with _kunci:
        sisa = max(_sisa_detik(_kunci_id(identifier), maks_gagal(), sekarang, jeda),
                   _sisa_detik(("ip", ip), maks_gagal_ip(), sekarang, jeda))
    return max(1, math.ceil(sisa / 60)) if sisa > 0 else None


def catat_gagal(identifier: str, ip: str) -> None:
    jeda, sekarang = jeda_detik(), time.monotonic()
    with _kunci:
        if len(_gagal) > _BATAS_KUNCI:
            for k in [k for k, a in _gagal.items() if not a or a[-1] <= sekarang - jeda]:
                del _gagal[k]
        for kunci in (_kunci_id(identifier), ("ip", ip)):
            antrean = _gagal.setdefault(kunci, deque())
            _bersihkan(antrean, sekarang, jeda)
            antrean.append(sekarang)


def reset_identifier(identifier: str) -> None:
    with _kunci:
        _gagal.pop(_kunci_id(identifier), None)


def reset_semua() -> None:
    with _kunci:
        _gagal.clear()
