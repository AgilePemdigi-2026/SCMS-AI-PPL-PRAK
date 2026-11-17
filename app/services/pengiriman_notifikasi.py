"""Delivery of a notification to an outside channel (PRD 5.3 BR-8, Sprint 3).

The in-app notification (the `notifikasi` row shown on the citizen's /notifikasi page) is always
saved. `status_kirim` only describes the simulated outside channel (e.g. SMS/WhatsApp):

  * Menunggu  — created, not sent yet,
  * Terkirim  — one attempt succeeded,
  * Gagal     — 1 initial send + 3 automatic retries all failed (Admin can "Kirim Ulang").

The simulated channel fails when random.random() < SCMS_NOTIF_TINGKAT_GAGAL (0.0–1.0, default 0;
an invalid value counts as 0). The variable is read on every send, so tests can change it.
Retries are synchronous and without sleep. Sending never raises: a delivery failure must not
undo the ticket status change that created the notification.
"""
import logging
import math
import os
import random
from datetime import datetime, timezone

from app.models.entities import Notifikasi

logger = logging.getLogger("scms")

KIRIM_MENUNGGU = "Menunggu"
KIRIM_TERKIRIM = "Terkirim"
KIRIM_GAGAL = "Gagal"
STATUS_KIRIM = (KIRIM_MENUNGGU, KIRIM_TERKIRIM, KIRIM_GAGAL)

ENV_TINGKAT_GAGAL = "SCMS_NOTIF_TINGKAT_GAGAL"
PERCOBAAN_ULANG_MAKS = 3                      # automatic retries after the initial send
PERCOBAAN_PER_SIKLUS = 1 + PERCOBAAN_ULANG_MAKS


def tingkat_gagal() -> float:
    """Failure rate of the simulated channel from the environment; anything invalid is 0."""
    teks = (os.environ.get(ENV_TINGKAT_GAGAL) or "").strip()
    try:
        nilai = float(teks)
    except ValueError:
        return 0.0
    if math.isnan(nilai) or not 0.0 <= nilai <= 1.0:
        return 0.0
    return nilai


def kirim_ke_kanal(notif: Notifikasi) -> bool:
    """One attempt on the simulated outside channel. True = delivered."""
    return not (random.random() < tingkat_gagal())


def jalankan_siklus_kirim(notif: Notifikasi) -> bool:
    """One send cycle: the initial send plus at most 3 automatic retries.

    Every attempt adds 1 to `jumlah_percobaan` and sets `waktu_percobaan_terakhir`. Ends as
    Terkirim on the first success, or Gagal after 4 failed attempts. Never raises."""
    for _ in range(PERCOBAAN_PER_SIKLUS):
        notif.jumlah_percobaan = (notif.jumlah_percobaan or 0) + 1
        notif.waktu_percobaan_terakhir = datetime.now(timezone.utc)
        try:
            berhasil = kirim_ke_kanal(notif)
        except Exception:  # a broken channel is a failed attempt, never an error for the caller
            logger.exception("Pengiriman notifikasi %s gagal karena galat kanal", notif.id_notifikasi)
            berhasil = False
        if berhasil:
            notif.status_kirim = KIRIM_TERKIRIM
            return True
    notif.status_kirim = KIRIM_GAGAL
    logger.warning("Notifikasi %s gagal dikirim setelah %s percobaan", notif.id_notifikasi, notif.jumlah_percobaan)
    return False
