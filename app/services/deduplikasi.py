"""
Spatial-semantic deduplication (PRD BR-3).

Candidates are active Work Orders (status is not "Selesai" or "Ditutup") with the same damage
category. A candidate is a duplicate in one of two tiers:
  Tier 1 - both have coordinates and the distance is <= RADIUS_PASTI_SAMA_M (15 m):
           duplicate without any description check. Phone GPS is only accurate to
           about 5-10 m and citizen descriptions are often uninformative, so reports
           of the same category this close almost surely describe the same damage
           (an officer still verifies every ticket).
  Tier 2 - same spot by the old rule:
             - both have coordinates  -> distance <= RADIUS_DUPLIKAT_M (50 m), or
             - otherwise              -> same normalised street name + house number,
           AND the new description is similar enough to at least one report already
           in that Work Order (threshold depends on the NLP backend).
Beyond 50 m it is never a duplicate.
With several matches: the nearest Tier-1 candidate wins; if there is none, the most
similar (then nearest) Tier-2 candidate wins, as before.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Laporan, WorkOrder
from app.services.ai_service import AIService

RADIUS_PASTI_SAMA_M = 15.0   # tier 1: same spot within phone-GPS error, no text check
RADIUS_DUPLIKAT_M = 50.0     # tier 2: needs description similarity as well
DASAR_JARAK = "jarak <= 15 m"
DASAR_JARAK_DAN_KEMIRIPAN = "jarak + kemiripan deskripsi"
# final statuses (alur_status.STATUS_FINAL): a closed ticket (PRD 5.3 BR-4) is never a merge target
STATUS_TIDAK_AKTIF = ("Selesai", "Ditutup")


@dataclass
class KandidatDuplikat:
    work_order: WorkOrder
    jarak_m: Optional[float]
    kemiripan: Optional[float]   # None for tier 1 (description not compared)
    dasar: str = DASAR_JARAK_DAN_KEMIRIPAN   # why it was merged, for tracing


def jarak_meter(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in metres."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def normalisasi_alamat(alamat: str) -> str:
    """'Jl. Sudirman No. 45, Surabaya' -> 'sudirman 45' (street + number only)."""
    bagian = (alamat or "").split(",")[0].lower()
    bagian = re.sub(r"\b(jl|jln|jalan|no|nomor)\b\.?", " ", bagian)
    bagian = re.sub(r"[^a-z0-9]+", " ", bagian)
    return " ".join(bagian.split())


def _lokasi_sama(wo: WorkOrder, lokasi: str, lat: Optional[float], lng: Optional[float]) -> tuple[bool, Optional[float]]:
    if lat is not None and lng is not None and wo.latitude is not None and wo.longitude is not None:
        jarak = jarak_meter(lat, lng, wo.latitude, wo.longitude)
        return jarak <= RADIUS_DUPLIKAT_M, jarak
    alamat_baru = normalisasi_alamat(lokasi)
    return bool(alamat_baru) and alamat_baru == normalisasi_alamat(wo.lokasi_jalan), None


def cari_duplikat(
    db: Session,
    ai: AIService,
    kategori: str,
    lokasi: str,
    deskripsi: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Optional[KandidatDuplikat]:
    kandidat_aktif = db.query(WorkOrder).filter(
        WorkOrder.kategori_kerusakan == kategori,
        WorkOrder.status_work_order.notin_(STATUS_TIDAK_AKTIF),
    ).all()

    terdekat: Optional[KandidatDuplikat] = None   # best tier-1 match
    terbaik: Optional[KandidatDuplikat] = None    # best tier-2 match
    for wo in kandidat_aktif:
        cocok, jarak = _lokasi_sama(wo, lokasi, latitude, longitude)
        if not cocok:
            continue
        if jarak is not None and jarak <= RADIUS_PASTI_SAMA_M:
            if terdekat is None or jarak < terdekat.jarak_m:
                terdekat = KandidatDuplikat(wo, jarak, None, DASAR_JARAK)
            continue
        if terdekat is not None:
            continue  # a tier-1 match always wins, no need to compare descriptions
        laporan = db.query(Laporan).filter_by(id_work_order=wo.id_work_order).all()
        kemiripan = max((ai.kemiripan_deskripsi(deskripsi, lap.deskripsi or "") for lap in laporan), default=0.0)
        if kemiripan < ai.ambang_duplikat:
            continue
        kandidat = KandidatDuplikat(wo, jarak, kemiripan, DASAR_JARAK_DAN_KEMIRIPAN)
        if terbaik is None or (kandidat.kemiripan, -(jarak or 0.0)) > (terbaik.kemiripan, -(terbaik.jarak_m or 0.0)):
            terbaik = kandidat
    return terdekat or terbaik
