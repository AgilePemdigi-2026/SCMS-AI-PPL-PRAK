"""
Multi-Factor Risk Scoring Engine (PRD BR-2).

    Risk Score = clip(round(w_s*Severity + w_e*ln(Exposure + 1) + w_v*Vulnerability + w_c*Criticality, 1), 0.0, 10.0)

All inputs except Exposure are on a 0-10 scale. Exposure is the number of
citizen reports merged into the Work Order (>= 1). The log keeps exposure
from dominating: going from 1 to 10 reporters adds about 0.8 points.

Urgency is shown only by the priority level (Urgent / Tinggi / Borderline /
Rendah). There is no completion-time target (SLA): it was removed after the
teaching assistant's review, because real road repairs go through procurement
and bureaucracy, so fixed targets such as 24 jam or 7x24 jam are not realistic.

The weights below are a starting point for the team to calibrate with the
Dinas; change them here and every new or merged ticket uses the new values.
"""
import math
from dataclasses import dataclass

BOBOT_SEVERITY = 0.50
BOBOT_EXPOSURE = 0.45
BOBOT_VULNERABILITY = 0.15
BOBOT_CRITICALITY = 0.25

# Criticality is derived from road class (kelas jalan): busier roads matter more.
CRITICALITY_KELAS_JALAN = {
    "Arteri Primer": 10.0,
    "Arteri Sekunder": 8.5,
    "Kolektor": 7.0,
    "Lokal": 5.0,
    "Lingkungan": 3.0,
}
KELAS_JALAN_DEFAULT = "Kolektor"

# Vulnerability (location: schools, hospitals, flood-prone, etc.) has no data
# source yet, so new reports get this neutral default until a field
# inspection or master data provides a real value.
VULNERABILITY_DEFAULT = 6.0


# Field damage level chosen by the Penilik Jalan during inspection (PRD 5.3 BR-2). Its severity
# replaces the AI severity in the same formula; E, V and C stay as they are.
TINGKAT_KERUSAKAN = {
    "Ringan": 3.0,
    "Sedang": 5.0,
    "Berat": 7.0,
    "Sangat Berat": 9.0,
}
KETERANGAN_TINGKAT = {
    "Ringan": "Retak rambut / lubang dangkal, belum mengganggu lalu lintas",
    "Sedang": "Lubang atau retak jelas, kendaraan perlu melambat",
    "Berat": "Lubang dalam / amblas, membahayakan pengendara motor",
    "Sangat Berat": "Badan jalan rusak parah atau amblas, berisiko kecelakaan tinggi",
}


def severity_tingkat(tingkat: str):
    """Severity of a field damage level, or None for an unknown/empty level."""
    return TINGKAT_KERUSAKAN.get((tingkat or "").strip())


@dataclass(frozen=True)
class HasilRisiko:
    risk_score: float
    prioritas: str


def criticality_dari_kelas(kelas_jalan: str) -> float:
    return CRITICALITY_KELAS_JALAN.get(kelas_jalan, CRITICALITY_KELAS_JALAN[KELAS_JALAN_DEFAULT])


def hitung_risk_score(severity: float, exposure: int, vulnerability: float, criticality: float) -> float:
    exposure = max(1, int(exposure or 1))
    nilai = (
        BOBOT_SEVERITY * float(severity or 0.0)
        + BOBOT_EXPOSURE * math.log(exposure + 1)
        + BOBOT_VULNERABILITY * float(vulnerability or 0.0)
        + BOBOT_CRITICALITY * float(criticality or 0.0)
    )
    return min(10.0, max(0.0, round(nilai, 1)))


def klasifikasi_prioritas(risk_score: float) -> str:
    """Priority level from PRD BR-2: >= 8.0 Urgent, >= 6.0 Tinggi, >= 4.0 Borderline, else Rendah."""
    if risk_score >= 8.0:
        return "Urgent"
    if risk_score >= 6.0:
        return "Tinggi"
    if risk_score >= 4.0:
        return "Borderline"
    return "Rendah"


def skor_ambigu(risk_score) -> bool:
    """Ambiguous score for verification (UC-B): exactly the Borderline band of BR-2,
    4.0 <= score < 6.0. A score of 6.0 is a clear (Tinggi) score."""
    return risk_score is not None and klasifikasi_prioritas(float(risk_score)) == "Borderline"


def nilai_risiko(severity: float, exposure: int, vulnerability: float, kelas_jalan: str) -> HasilRisiko:
    skor = hitung_risk_score(severity, exposure, vulnerability, criticality_dari_kelas(kelas_jalan))
    return HasilRisiko(risk_score=skor, prioritas=klasifikasi_prioritas(skor))


def terapkan_ke_work_order(wo) -> HasilRisiko:
    """Recompute and store risk score and priority on a WorkOrder.
    The deprecated SLA column of WorkOrder is no longer written."""
    hasil = nilai_risiko(wo.severity_score_kasus, wo.exposure_count, wo.vulnerability_score, wo.kelas_jalan)
    wo.risk_score = hasil.risk_score
    wo.prioritas = hasil.prioritas
    return hasil
