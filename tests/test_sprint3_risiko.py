"""
Fast tests (no browser) for Sprint 3 / CO-1, PRD 5.3 BR-2: the Risk Score is recalculated after the
field inspection with the field damage level (Ringan/Sedang/Berat/Sangat Berat = 3/5/7/9) instead of
the AI severity, and every later recompute keeps using the field severity.
"""
import pytest
from sqlalchemy import create_engine, inspect, text

from app.controllers.kontrol_inspeksi import KontrolInspeksi
from app.controllers.kontrol_pelaporan import KontrolPelaporan
from app.database import SessionLocal, pastikan_kolom_terbaru
from app.models.entities import Inspeksi, Laporan, RiwayatStatus, WorkOrder
from app.services import risk_scoring
from tests.test_sprint2 import ADMIN, PENILIK, ambil, db_bersih, hitung, jpeg, klien  # noqa: F401 (fixture)

WO = "REP-2026-00298"   # seed: Ditugaskan to Budi Santoso, S 8.0, E 1, V 8.0, Arteri Primer -> 8.0 Urgent
PESAN_TANPA_TINGKAT = "Pilih tingkat kerusakan hasil inspeksi lapangan"


def inspeksi(tingkat="Ringan", kategori="", id_wo=WO, **ubah):
    data = {"dimensi_kerusakan": "1.5m x 1m", "catatan_teknis": "dicek di lokasi", "rekomendasi": "Tambal Hotmix",
            "tingkat_kerusakan": tingkat, "kategori_terkonfirmasi": kategori}
    data.update(ubah)
    return klien(PENILIK).post(f"/TugasLapangan/{id_wo}/inspeksi", data=data,
                               files={"foto_survei": ("survei.jpg", jpeg(), "image/jpeg")})


def riwayat(id_wo=WO):
    db = SessionLocal()
    try:
        return [(r.status, r.keterangan or "") for r in
                db.query(RiwayatStatus).filter_by(id_work_order=id_wo).order_by(RiwayatStatus.id_riwayat)]
    finally:
        db.close()


# ----------------------------------------------------------------- mapping
def test_pemetaan_tingkat_kerusakan_3_5_7_9():
    assert risk_scoring.TINGKAT_KERUSAKAN == {"Ringan": 3.0, "Sedang": 5.0, "Berat": 7.0, "Sangat Berat": 9.0}
    assert set(risk_scoring.KETERANGAN_TINGKAT) == set(risk_scoring.TINGKAT_KERUSAKAN)
    assert risk_scoring.severity_tingkat(" Berat ") == 7.0
    for salah in ("", None, "Parah", "berat", "7"):
        assert risk_scoring.severity_tingkat(salah) is None


@pytest.mark.parametrize("tingkat, skor, prioritas", [
    ("Ringan", 5.5, "Borderline"), ("Sedang", 6.5, "Tinggi"), ("Berat", 7.5, "Tinggi"), ("Sangat Berat", 8.5, "Urgent"),
])
def test_formula_br2_dengan_severity_lapangan(tingkat, skor, prioritas):
    hasil = risk_scoring.nilai_risiko(risk_scoring.severity_tingkat(tingkat), 1, 8.0, "Arteri Primer")
    assert (hasil.risk_score, hasil.prioritas) == (skor, prioritas)


# ------------------------------------------------------------- recompute
@pytest.mark.parametrize("tingkat, skor, prioritas", [("Ringan", 5.5, "Borderline"), ("Sangat Berat", 8.5, "Urgent")])
def test_inspeksi_menghitung_ulang_risk_score_contoh_prd(db_bersih, tingkat, skor, prioritas):
    r = inspeksi(tingkat)
    assert r.status_code == 200 and "Hasil inspeksi berhasil disimpan" in r.text
    wo = ambil(WorkOrder, WO)
    assert (wo.status_work_order, wo.risk_score, wo.prioritas) == ("Terinspeksi", skor, prioritas)
    # field severity replaces the AI severity; E, V, C unchanged; AI severity kept for comparison
    assert wo.severity_score_kasus == risk_scoring.severity_tingkat(tingkat)
    assert (wo.severity_ai, wo.exposure_count, wo.vulnerability_score, wo.kelas_jalan) == (8.0, 1, 8.0, "Arteri Primer")
    db = SessionLocal()
    ins = db.query(Inspeksi).filter_by(id_work_order=WO).one()
    assert (ins.tingkat_kerusakan, ins.severity_lapangan, ins.kategori_terkonfirmasi) == (
        tingkat, risk_scoring.severity_tingkat(tingkat), "Jalan Berlubang")
    db.close()


def test_riwayat_mencatat_hitung_ulang_tanpa_status_baru(db_bersih):
    sebelum = riwayat()
    inspeksi("Ringan")
    baru = riwayat()[len(sebelum):]
    assert len(baru) == 1  # one entry: the existing Ditugaskan -> Terinspeksi transition
    status, ket = baru[0]
    assert status == "Terinspeksi"
    assert "Risk Score diperbarui 8.0 → 5.5 berdasarkan inspeksi" in ket
    assert "tingkat kerusakan Ringan" in ket


def test_kategori_dikoreksi_saat_inspeksi(db_bersih):
    r = inspeksi("Sedang", kategori="Retak Permukaan")
    assert "Hasil inspeksi berhasil disimpan" in r.text
    wo = ambil(WorkOrder, WO)
    assert wo.kategori_kerusakan == "Retak Permukaan"
    assert wo.risk_score == 6.5  # the category does not enter the formula; the field severity does
    assert any("kategori dikoreksi Jalan Berlubang → Retak Permukaan" in k for _, k in riwayat())


def test_kategori_tidak_valid_ditolak(db_bersih):
    r = inspeksi("Sedang", kategori="Jalan Bergelombang")
    assert "Pilih kategori kerusakan yang valid" in r.text
    assert hitung(Inspeksi, id_work_order=WO) == 0
    assert ambil(WorkOrder, WO).status_work_order == "Ditugaskan"


@pytest.mark.parametrize("tingkat", ["", "Parah"])
def test_tanpa_tingkat_kerusakan_ditolak(db_bersih, tingkat):
    r = inspeksi(tingkat)
    assert PESAN_TANPA_TINGKAT in r.text
    wo = ambil(WorkOrder, WO)
    assert (wo.status_work_order, wo.risk_score, wo.prioritas, wo.severity_score_kasus) == ("Ditugaskan", 8.0, "Urgent", 8.0)
    assert hitung(Inspeksi, id_work_order=WO) == 0
    assert hitung(RiwayatStatus, id_work_order=WO, status="Terinspeksi") == 0


def test_controller_tanpa_tingkat_ditolak(db_bersih):
    db = SessionLocal()
    hasil = KontrolInspeksi(db).simpan_inspeksi(WO, "PNL-01", "1m", "", "Tambal Hotmix")
    db.close()
    assert hasil == {"success": False, "message": PESAN_TANPA_TINGKAT}


def test_form_gagal_mempertahankan_isian(db_bersih):
    r = inspeksi("", kategori="Retak Permukaan")
    assert '<option value="Retak Permukaan" selected' in r.text
    r = inspeksi("Berat", rekomendasi="")  # another field missing: the chosen level stays checked
    assert 'value="Berat" class="mt-0.5" checked' in r.text


# ------------------------------------------------- later recomputes (BR-3)
def _gabung_laporan_warga(id_warga="USR-01"):
    db = SessionLocal()
    try:
        return KontrolPelaporan(db).kirim_laporan(
            filename="jalan_berlubang_sudirman_baru.jpg", file_size_mb=1.2, lokasi_jalan="Jl. Sudirman No. 45, Surabaya",
            deskripsi="Jalan berlubang di depan lampu merah Sudirman makin lebar", kategori_pilihan="Jalan Berlubang",
            latitude=-7.26552, longitude=112.74702, id_warga=id_warga)
    finally:
        db.close()


def test_penggabungan_setelah_inspeksi_tetap_memakai_severity_lapangan(db_bersih):
    inspeksi("Ringan")
    hasil = _gabung_laporan_warga()
    assert hasil["success"] and hasil["is_duplicate"] and hasil["ticket_id"] == WO
    wo = ambil(WorkOrder, WO)
    assert wo.exposure_count == 2
    assert wo.severity_score_kasus == 3.0  # not the AI severity of the merged report
    assert wo.risk_score == risk_scoring.nilai_risiko(3.0, 2, 8.0, "Arteri Primer").risk_score == 5.7
    assert wo.prioritas == "Borderline"
    assert wo.severity_ai == max(8.0, hasil["severity_score"])  # AI side still tracked for comparison


def test_penggabungan_sebelum_inspeksi_tetap_memakai_severity_ai(db_bersih):
    hasil = _gabung_laporan_warga()
    wo = ambil(WorkOrder, WO)
    tertinggi = max(8.0, hasil["severity_score"])
    assert (wo.severity_score_kasus, wo.severity_ai, wo.exposure_count) == (tertinggi, tertinggi, 2)
    assert wo.risk_score == risk_scoring.nilai_risiko(tertinggi, 2, 8.0, "Arteri Primer").risk_score


def test_laporan_baru_menyimpan_severity_ai(db_bersih):
    db = SessionLocal()
    hasil = KontrolPelaporan(db).kirim_laporan(
        filename="jalan_berlubang_kenjeran.jpg", file_size_mb=1.0, lokasi_jalan="Jl. Kenjeran No. 300, Surabaya",
        deskripsi="Lubang lebar di jalur lambat Kenjeran", latitude=-7.2480, longitude=112.7900)
    wo = db.get(WorkOrder, hasil["ticket_id"])
    assert not hasil["is_duplicate"]
    assert wo.severity_ai == wo.severity_score_kasus == hasil["severity_score"]
    db.close()


# ------------------------------------------------------------- display
def test_detail_menampilkan_severity_ai_dan_lapangan(db_bersih):
    halaman = {
        "tugas": (PENILIK, f"/TugasLapangan/{WO}"),
        "work_order": (ADMIN, f"/work-orders?select_ticket={WO}"),
        "verifikasi": (ADMIN, f"/verifikasi?ticket_id={WO}"),
    }
    for akun, url in halaman.values():
        html = klien(akun).get(url).text
        assert 'id="severityAi" ' in html and 'data-nilai="8.0"' in html, url
        assert 'id="severityLapangan"' in html and "Belum diinspeksi" in html, url
    inspeksi("Ringan")
    for akun, url in halaman.values():
        html = klien(akun).get(url).text
        assert 'id="severityLapangan" class' in html and 'data-nilai="3.0"' in html, url
        assert "Ringan &middot; dipakai Risk Score" in html, url
        assert 'data-prioritas="Borderline"' in html, url


def test_form_inspeksi_berisi_kategori_dan_empat_tingkat(db_bersih):
    html = klien(PENILIK).get(f"/TugasLapangan/{WO}").text
    assert '<option value="Jalan Berlubang" selected' in html  # pre-filled with the ticket category
    for i, (nama, keterangan) in enumerate(risk_scoring.KETERANGAN_TINGKAT.items(), 1):
        assert f'id="tingkat-{i}" name="tingkat_kerusakan" value="{nama}"' in html
        assert keterangan in html
    assert 'name="tingkat_kerusakan" value="Ringan" class="mt-0.5" checked' not in html  # no default choice


# ------------------------------------------------------------ old database
def test_database_lama_mendapat_kolom_sprint3_dan_severity_ai(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'lama.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE work_order (id_work_order VARCHAR(20) PRIMARY KEY, severity_score_kasus FLOAT)"))
        conn.execute(text("CREATE TABLE inspeksi (id_inspeksi VARCHAR(20) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO work_order VALUES ('REP-LAMA-1', 6.5), ('REP-LAMA-2', 4.0)"))
    pastikan_kolom_terbaru(eng)
    kolom = {t: {c["name"] for c in inspect(eng).get_columns(t)} for t in ("work_order", "inspeksi")}
    assert "severity_ai" in kolom["work_order"]
    assert {"kategori_terkonfirmasi", "tingkat_kerusakan", "severity_lapangan"} <= kolom["inspeksi"]
    with eng.begin() as conn:
        conn.execute(text("UPDATE work_order SET severity_ai = 9.9 WHERE id_work_order = 'REP-LAMA-2'"))
    pastikan_kolom_terbaru(eng)  # idempotent: a filled value is never overwritten
    with eng.connect() as conn:
        assert dict(conn.execute(text("SELECT id_work_order, severity_ai FROM work_order")).all()) == {
            "REP-LAMA-1": 6.5, "REP-LAMA-2": 9.9}


def test_seed_mengisi_severity_ai(db_bersih):
    db = SessionLocal()
    assert all(wo.severity_ai == wo.severity_score_kasus for wo in db.query(WorkOrder).all())
    assert db.query(Laporan).count() == 3
    db.close()
