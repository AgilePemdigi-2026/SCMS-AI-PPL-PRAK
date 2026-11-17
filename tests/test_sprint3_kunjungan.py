"""
Fast tests (no browser) for Sprint 3 Bagian 2B / CO-3 (PRD 5.3 "Kunjungan lanjutan", decision 5.9 no. 7):
temporary repair with ONE active follow-up visit (a work plan, not a deadline), recordable early,
blocking "Selesai" until recorded, for both the inspector and the Admin.
"""
import re
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, inspect, text

from app.controllers.kontrol_laporan_kinerja import TAHAP_MENUNGGU_KUNJUNGAN, KontrolLaporanKinerja
from app.controllers.kontrol_lacak import KontrolLacak
from app.controllers.kontrol_penanganan import (
    PESAN_CATATAN_KUNJUNGAN, PESAN_JADWAL_TIDAK_VALID, PESAN_JADWAL_WAJIB, PESAN_KUNJUNGAN_BELUM_DICATAT,
    PESAN_SEMENTARA_BUKAN_SELESAI, PESAN_TANPA_JADWAL, KontrolPenanganan, baca_jadwal_lanjutan, hari_ini_wib,
)
from app.database import SessionLocal, pastikan_kolom_terbaru
from app.models.entities import Perbaikan, PenilikJalan, RiwayatStatus, WorkOrder
from database.seed import pwd_context
from tests.test_sprint2 import (  # noqa: F401 (db_bersih is a fixture)
    ADMIN, KABID, PENILIK, WARGA, ambil, db_bersih, hitung, jpeg, klien, tugaskan,
)

WO = "REP-2026-00341"   # LAP-2026-0001, USR-01


def tanggal(hari):
    return (hari_ini_wib() + timedelta(days=hari)).isoformat()


@pytest.fixture
def dalam_proses(db_bersih):
    """REP-2026-00341 assigned to PNL-01, inspected, SPK issued -> Dalam Proses (Sprint 2 flow)."""
    tugaskan()
    klien(PENILIK).post(f"/TugasLapangan/{WO}/inspeksi", data={
        "dimensi_kerusakan": "2m x 1m", "rekomendasi": "Tambal Hotmix", "tingkat_kerusakan": "Berat"})
    klien(ADMIN).post(f"/work-orders/{WO}/spk", data={"nomor_spk": "SPK/PUPR/XI/2026/001", "tim_pelaksana": "Satgas"})
    assert ambil(WorkOrder, WO).status_work_order == "Dalam Proses"


def progres(akun=PENILIK, **data):
    url = f"/TugasLapangan/{WO}/progres" if akun == PENILIK else f"/work-orders/{WO}/progres"
    isi = {"status_baru": "Dalam Proses", "catatan_progres": "Ditambal sementara dengan cold mix"}
    isi.update(data)
    files = {"foto_selesai": ("selesai.jpg", jpeg(), "image/jpeg")} if isi["status_baru"] == "Selesai" else None
    return klien(akun).post(url, data=isi, files=files)


def jadwalkan(hari=7, akun=PENILIK):
    return progres(akun, perbaikan_sementara="1", jadwal_lanjutan=tanggal(hari))


def kunjungan(akun=PENILIK, catatan="Hotmix permanen sudah dipasang", foto=False):
    url = f"/TugasLapangan/{WO}/kunjungan" if akun == PENILIK else f"/work-orders/{WO}/kunjungan"
    files = {"foto_kunjungan": ("kunjungan.jpg", jpeg(), "image/jpeg")} if foto else None
    return klien(akun).post(url, data={"catatan_kunjungan": catatan}, files=files)


def jadwal():
    db = SessionLocal()
    try:
        return [(p.status_jadwal, p.jadwal_lanjutan) for p in
                db.query(Perbaikan).filter_by(id_work_order=WO).order_by(Perbaikan.id_perbaikan) if p.status_jadwal]
    finally:
        db.close()


def riwayat():
    db = SessionLocal()
    try:
        return [(r.status, r.keterangan or "") for r in
                db.query(RiwayatStatus).filter_by(id_work_order=WO).order_by(RiwayatStatus.id_riwayat)]
    finally:
        db.close()


# ------------------------------------------------------------ date rule
@pytest.mark.parametrize("hari, pesan", [(-1, PESAN_JADWAL_TIDAK_VALID), (0, PESAN_JADWAL_TIDAK_VALID),
                                         (1, None), (30, None)])
def test_jadwal_harus_setelah_hari_ini(hari, pesan):
    hasil, galat = baca_jadwal_lanjutan(tanggal(hari))
    assert galat == pesan
    assert (hasil is None) == (pesan is not None)


@pytest.mark.parametrize("teks, pesan", [("", PESAN_JADWAL_WAJIB), ("17-11-2026", PESAN_JADWAL_TIDAK_VALID),
                                        ("besok", PESAN_JADWAL_TIDAK_VALID)])
def test_jadwal_kosong_atau_format_salah(teks, pesan):
    assert baca_jadwal_lanjutan(teks) == (None, pesan)


@pytest.mark.parametrize("hari", [0, -1])
@pytest.mark.parametrize("akun", [PENILIK, ADMIN])
def test_tanggal_hari_ini_dan_lampau_ditolak(dalam_proses, hari, akun):
    r = jadwalkan(hari, akun)
    assert PESAN_JADWAL_TIDAK_VALID in r.text
    assert jadwal() == [] and ambil(WorkOrder, WO).status_work_order == "Dalam Proses"


def test_perbaikan_sementara_tanpa_tanggal_dan_tidak_bisa_langsung_selesai(dalam_proses):
    assert PESAN_JADWAL_WAJIB in progres(perbaikan_sementara="1").text
    r = progres(perbaikan_sementara="1", jadwal_lanjutan=tanggal(7), status_baru="Selesai")
    assert PESAN_SEMENTARA_BUKAN_SELESAI in r.text and jadwal() == []


# ------------------------------------------------- scheduling and visit
def test_jadwal_tercatat_tanpa_transisi_status(dalam_proses):
    sebelum = riwayat()
    r = jadwalkan(7)
    assert "Perbaikan sementara tercatat; kunjungan lanjutan dijadwalkan" in r.text
    assert jadwal() == [("Aktif", tanggal(7))]
    baru = riwayat()[len(sebelum):]
    tampil = (hari_ini_wib() + timedelta(days=7)).strftime("%d/%m/%Y")
    assert baru == [("Dalam Proses", f"Perbaikan sementara: Ditambal sementara dengan cold mix; "
                                     f"Kunjungan lanjutan dijadwalkan {tampil}")]
    db = SessionLocal()
    p = db.get(WorkOrder, WO).jadwal_lanjutan_aktif
    assert p.perbaikan_sementara is True and p.status_perbaikan == "Dalam Proses"
    db.close()


@pytest.mark.parametrize("akun", [PENILIK, ADMIN])
def test_jadwal_ulang_menyisakan_satu_jadwal_aktif(dalam_proses, akun):
    jadwalkan(7)
    jadwalkan(14, akun)
    jadwalkan(21, akun)
    assert jadwal() == [("Diganti", tanggal(7)), ("Diganti", tanggal(14)), ("Aktif", tanggal(21))]
    assert sum(1 for _, k in riwayat() if "Kunjungan lanjutan dijadwalkan ulang" in k) == 2


@pytest.mark.parametrize("akun", [PENILIK, ADMIN])
def test_catat_kunjungan_lebih_awal_boleh(dalam_proses, akun):
    jadwalkan(7)
    r = kunjungan(akun, foto=True)
    assert "Kunjungan lanjutan berhasil dicatat" in r.text
    db = SessionLocal()
    p = db.query(Perbaikan).filter_by(id_work_order=WO, status_jadwal="Tercatat").one()
    assert p.kunjungan_dicatat_pada is not None and p.tanggal_lanjutan > hari_ini_wib()  # before the planned date
    assert p.catatan_kunjungan == "Hotmix permanen sudah dipasang" and p.foto_kunjungan
    assert db.get(WorkOrder, WO).jadwal_lanjutan_aktif is None
    db.close()
    assert any(k.startswith("Kunjungan lanjutan dicatat") for _, k in riwayat())
    # a later temporary repair may be scheduled again when really needed
    jadwalkan(10)
    assert jadwal()[-1] == ("Aktif", tanggal(10))


def test_catat_kunjungan_butuh_catatan_dan_jadwal(dalam_proses):
    assert PESAN_TANPA_JADWAL in kunjungan().text
    jadwalkan(7)
    assert PESAN_CATATAN_KUNJUNGAN in kunjungan(catatan="  ").text
    assert jadwal() == [("Aktif", tanggal(7))]


# ------------------------------------------------------- Selesai blocked
@pytest.mark.parametrize("akun", [PENILIK, ADMIN])
def test_selesai_diblok_selama_jadwal_aktif(dalam_proses, akun):
    jadwalkan(7)
    r = progres(akun, status_baru="Selesai", catatan_progres="Selesai")
    assert PESAN_KUNJUNGAN_BELUM_DICATAT in r.text
    assert ambil(WorkOrder, WO).status_work_order == "Dalam Proses"
    kunjungan(akun)
    progres(akun, status_baru="Selesai", catatan_progres="Hotmix permanen")
    assert ambil(WorkOrder, WO).status_work_order == "Selesai"


@pytest.mark.parametrize("akun, url", [(PENILIK, f"/TugasLapangan/{WO}"), (ADMIN, f"/work-orders?select_ticket={WO}")])
def test_ui_menonaktifkan_selesai_dan_menampilkan_jadwal(dalam_proses, akun, url):
    html = klien(akun).get(url).text
    assert re.search(r'<option value="Selesai"\s*>Selesai</option>', html)
    assert 'id="perbaikan_sementara"' in html and 'id="jadwal_lanjutan"' in html and 'id="formKunjungan"' not in html
    jadwalkan(7)
    html = klien(akun).get(url).text
    assert '<option value="Selesai"  disabled>Selesai (catat kunjungan lanjutan dulu)</option>' in html
    assert "Kunjungan lanjutan dijadwalkan " + (hari_ini_wib() + timedelta(days=7)).strftime("%d/%m/%Y") in html
    assert 'id="formKunjungan"' in html and 'id="catatKunjungan"' in html


def test_kabid_melihat_jadwal_tanpa_form(dalam_proses):
    jadwalkan(7)
    html = klien(KABID).get(f"/work-orders?select_ticket={WO}").text
    assert 'id="infoJadwalAktifWo"' in html and 'id="formKunjungan"' not in html and 'id="formProgresAdmin"' not in html


def test_daftar_tugas_lapangan_menampilkan_jadwal_aktif(dalam_proses):
    jadwalkan(7)
    html = klien(PENILIK).get("/TugasLapangan").text
    assert f'data-tanggal="{tanggal(7)}"' in html


# ------------------------------------------------------------------ RBAC
@pytest.mark.parametrize("akun", [KABID, WARGA])
def test_rbac_kabid_dan_warga_ditolak(dalam_proses, akun):
    assert klien(akun).post(f"/work-orders/{WO}/progres", data={
        "status_baru": "Dalam Proses", "catatan_progres": "x", "perbaikan_sementara": "1",
        "jadwal_lanjutan": tanggal(7)}).status_code == 403
    assert klien(akun).post(f"/work-orders/{WO}/kunjungan", data={"catatan_kunjungan": "x"}).status_code == 403
    assert klien(akun).post(f"/TugasLapangan/{WO}/kunjungan", data={"catatan_kunjungan": "x"}).status_code == 403
    assert jadwal() == []


def test_penilik_lain_ditolak(dalam_proses):
    db = SessionLocal()
    db.add(PenilikJalan(id_penilik="PNL-09", id_wilayah="WIL-01", nama_penilik="Andi Wijaya", nip="199001012020011009",
                        email_penilik="andi.wijaya@dpupr.surabaya.go.id", password_hash=pwd_context.hash("password123"),
                        status_ketersediaan="Tersedia", is_active=True))
    db.commit()
    db.close()
    jadwalkan(7)
    lain = klien("andi.wijaya@dpupr.surabaya.go.id")
    assert lain.post(f"/TugasLapangan/{WO}/kunjungan", data={"catatan_kunjungan": "x"}).status_code == 404
    assert lain.post(f"/TugasLapangan/{WO}/progres", data={
        "status_baru": "Dalam Proses", "catatan_progres": "x", "perbaikan_sementara": "1",
        "jadwal_lanjutan": tanggal(9)}).status_code == 404
    assert jadwal() == [("Aktif", tanggal(7))]


# ------------------------------------------------- timeline and reports
def test_linimasa_lacak_menampilkan_jadwal(dalam_proses):
    jadwalkan(7)
    db = SessionLocal()
    tahapan = KontrolLacak(db).detail_lacak("LAP-2026-0001", "USR-01")["tahapan"]
    db.close()
    label = [t["label"] for t in tahapan]
    tampil = (hari_ini_wib() + timedelta(days=7)).strftime("%d/%m/%Y")
    i = label.index("Perbaikan Berjalan")
    assert label[i + 1] == f"Kunjungan lanjutan dijadwalkan {tampil}" and tahapan[i + 1]["lanjutan"]
    assert "tahap-lanjutan" in klien(WARGA).get("/lacak?id=LAP-2026-0001").text
    kunjungan()
    db = SessionLocal()
    assert not any(t.get("lanjutan") for t in KontrolLacak(db).detail_lacak("LAP-2026-0001", "USR-01")["tahapan"])
    db.close()


def test_laporan_kinerja_tahap_menunggu_kunjungan_dan_durasi_perbaikan(dalam_proses):
    jadwalkan(7)
    db = SessionLocal()
    data = KontrolLaporanKinerja(db).rekap()
    baris = next(b for b in data["tiket_aktif"] if b["id_work_order"] == WO)
    assert baris["tahap_saat_ini"] == TAHAP_MENUNGGU_KUNJUNGAN
    assert baris["durasi_tahap"]["perbaikan"] is None  # still running until Selesai
    db.close()
    kunjungan()
    progres(status_baru="Selesai", catatan_progres="Hotmix permanen")
    db = SessionLocal()
    selesai = next(b for b in KontrolLaporanKinerja(db).rekap()["tiket"] if b["id_work_order"] == WO)
    db.close()
    assert selesai["tahap_saat_ini"] == "Selesai" and selesai["durasi_tahap"]["perbaikan"] is not None


def test_tanpa_istilah_tenggat_di_halaman(dalam_proses):
    jadwalkan(7)
    pola = re.compile(r"tenggat|terlambat|batas waktu|deadline|(?<![a-z])sla(?![a-z])", re.I)  # istilah yang dihapus
    for akun, url in [(PENILIK, f"/TugasLapangan/{WO}"), (PENILIK, "/TugasLapangan"), (ADMIN, f"/work-orders?select_ticket={WO}"),
                      (WARGA, "/lacak?id=LAP-2026-0001"), (KABID, "/laporan-kinerja")]:
        teks = re.sub(r"<[^>]+>", " ", klien(akun).get(url).text)
        assert not pola.search(teks), (url, pola.search(teks))


# ------------------------------------------------------ Sprint 2 flow kept
def test_alur_sprint2_tanpa_perbaikan_sementara_tetap_jalan(dalam_proses):
    progres(catatan_progres="Pengaspalan 50%")
    progres(status_baru="Selesai", catatan_progres="Lubang sudah ditambal")
    assert ambil(WorkOrder, WO).status_work_order == "Selesai" and jadwal() == []


# ------------------------------------------------------------ old database
def test_database_lama_mendapat_kolom_kunjungan(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'lama.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE perbaikan (id_perbaikan VARCHAR(20) PRIMARY KEY, jadwal_lanjutan VARCHAR(50))"))
        conn.execute(text("INSERT INTO perbaikan VALUES ('PRB-1', NULL)"))
    pastikan_kolom_terbaru(eng)
    kolom = {c["name"] for c in inspect(eng).get_columns("perbaikan")}
    assert {"perbaikan_sementara", "status_jadwal", "kunjungan_dicatat_pada", "catatan_kunjungan",
            "foto_kunjungan"} <= kolom
    with eng.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM perbaikan")).scalar() == 1
