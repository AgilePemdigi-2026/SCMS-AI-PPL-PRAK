"""
Regression tests for removing the SLA concept (teaching assistant's review).

Road repairs go through procurement and bureaucracy, so time targets such as
24 jam ... 7x24 jam are not realistic. Urgency is shown by the BR-2 priority
level only (Urgent / Tinggi / Borderline / Rendah). The `sla_rekomendasi`
column stays in the database (no risky migration) but is deprecated: nothing
writes or reads it any more.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.controllers.kontrol_dashboard import WARNA_BORDERLINE, WARNA_TINGGI, WARNA_URGENT, warna_marker
from app.database import SessionLocal
from app.main import app
from app.models.entities import WorkOrder
from app.services import risk_scoring
from database.seed import seed_data

ROOT = Path(__file__).resolve().parents[1]
WARGA = "0812xxxxxxx"
ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"

# "SLA" as a word, or as part of an identifier (sla_rekomendasi, jam_sla, status_sla ...)
POLA_SLA = re.compile(r"(?<![a-z])sla(?![a-z])|_sla|sla_", re.I)
# Time targets that came with the SLA
POLA_TARGET_WAKTU = re.compile(r"\d\s*[x×]\s*24\s*jam|\b24\s*jam\b|tepat waktu|terlambat|melewati sla", re.I)


@pytest.fixture
def db_bersih():
    seed_data(verbose=False)


def klien(identifier=None, password="password123") -> TestClient:
    c = TestClient(app)
    if identifier:
        r = c.post("/Login", data={"identifier": identifier, "password": password}, follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
    return c


# --------------------------------------------------------------------- logic
def test_risk_scoring_tidak_lagi_menghasilkan_sla():
    hasil = risk_scoring.nilai_risiko(8.4, 1, 9.3, "Arteri Primer")
    assert not hasattr(hasil, "sla_rekomendasi")
    assert isinstance(risk_scoring.klasifikasi_prioritas(hasil.risk_score), str)


def test_terapkan_ke_work_order_tidak_mengisi_kolom_usang():
    wo = WorkOrder(severity_score_kasus=8.4, exposure_count=1, vulnerability_score=9.3, kelas_jalan="Arteri Primer",
                   sla_rekomendasi="24 jam")
    risk_scoring.terapkan_ke_work_order(wo)
    assert wo.prioritas == "Urgent"
    assert wo.sla_rekomendasi == "24 jam"  # left untouched: deprecated, neither written nor read


def test_seed_tidak_mengisi_sla(db_bersih):
    db = SessionLocal()
    try:
        assert [wo.sla_rekomendasi for wo in db.query(WorkOrder).all()] == [None] * 5
    finally:
        db.close()


@pytest.mark.parametrize("skor, warna", [(8.4, WARNA_URGENT), (7.5, WARNA_TINGGI), (5.1, WARNA_BORDERLINE)])
def test_warna_peta_tidak_berubah(skor, warna):
    assert warna_marker(WorkOrder(risk_score=skor, status_work_order="Disetujui")) == warna


# ---------------------------------------------------------------------- views
@pytest.mark.parametrize("id_wo, prioritas, warna", [
    ("REP-2026-00341", "Urgent", WARNA_URGENT),
    ("REP-2026-00360", "Tinggi", WARNA_TINGGI),
    ("REP-2026-00355", "Borderline", WARNA_BORDERLINE),
])
def test_panel_work_order_menampilkan_lencana_prioritas_berwarna_peta(db_bersih, id_wo, prioritas, warna):
    html = klien(ADMIN).get(f"/work-orders?select_ticket={id_wo}").text
    lencana = re.search(r'<span id="lencanaPrioritas"[^>]*>(.*?)</span>', html, re.S)
    assert lencana, "lencana prioritas tidak ditemukan"
    assert f'style="background-color: {warna}"' in lencana.group(0)
    assert f"Prioritas Penanganan: {prioritas}" in lencana.group(1)
    assert "Rekomendasi SLA" not in html and "Standar SLA" not in html


@pytest.mark.parametrize("akun, halaman", [
    (ADMIN, "/Dashboard"),
    (ADMIN, "/work-orders"),
    (ADMIN, "/work-orders?select_ticket=REP-2026-00341"),
    (ADMIN, "/verifikasi"),
    (ADMIN, "/verifikasi?ticket_id=REP-2026-00355"),
    (ADMIN, "/master-data"),
    (KABID, "/laporan-kinerja"),
    (PENILIK, "/TugasLapangan"),
    (PENILIK, "/TugasLapangan/REP-2026-00298"),
    (WARGA, "/Beranda"),
    (WARGA, "/lacak?id=LAP-2026-0001"),
    (WARGA, "/lacak?id=LAP-2026-0003"),
    (WARGA, "/notifikasi"),
])
def test_halaman_tanpa_teks_sla(db_bersih, akun, halaman):
    r = klien(akun).get(halaman)
    assert r.status_code == 200, halaman
    teks = re.sub(r"<[^>]+>", " ", r.text)  # visible text and inline scripts, without tag/class names
    assert not POLA_SLA.search(teks), (halaman, POLA_SLA.search(teks).group(0))
    assert not POLA_TARGET_WAKTU.search(teks), (halaman, POLA_TARGET_WAKTU.search(teks).group(0))


def test_laporan_kinerja_menampilkan_durasi_tahap_dan_umur(db_bersih):
    html = klien(KABID).get("/laporan-kinerja").text
    for id_ in ('id="tabelDurasiTahap"', 'id="tabelTiketAktif"', 'id="kpiUmurTertua"', 'id="kpiRating"'):
        assert id_ in html
    for id_lama in ("kpiKepatuhan", "kpiLewatSla", "status-sla", 'data-kolom="kepatuhan"'):
        assert id_lama not in html


# ----------------------------------------------------------------------- code
def _berkas_kode():
    for folder in ("app", "tests", "database"):
        for p in (ROOT / folder).rglob("*"):
            if p.suffix in (".py", ".html", ".js", ".feature") and "__pycache__" not in p.parts \
                    and p.name != Path(__file__).name:
                yield p


def test_kode_tidak_lagi_memakai_sla():
    """Only the deprecated column (and notes saying the SLA was removed) may still mention SLA."""
    sisa = []
    for p in _berkas_kode():
        for no, baris in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not POLA_SLA.search(baris):
                continue
            catatan = re.search(r"deprecated|removed|dihapus|usang", baris, re.I)
            # guards that assert SLA is absent, e.g. assert not any("SLA" in k for k in kolom)
            penjaga = baris.strip().startswith("assert not")
            kolom_usang = "sla_rekomendasi" in baris and not re.search(r"\.sla_rekomendasi\s*=(?!=)", baris)
            if catatan or kolom_usang or penjaga:
                continue
            sisa.append(f"{p.relative_to(ROOT)}:{no}: {baris.strip()}")
    assert not sisa, "\n".join(sisa)


def test_hanya_tes_yang_menyentuh_kolom_usang():
    """Application code never writes or reads sla_rekomendasi; only its column definition remains."""
    pemakai = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "app").rglob("*")
                     if p.suffix in (".py", ".html", ".js") and "__pycache__" not in p.parts
                     and "sla_rekomendasi" in p.read_text(encoding="utf-8"))
    assert pemakai == ["app/models/entities.py"]
