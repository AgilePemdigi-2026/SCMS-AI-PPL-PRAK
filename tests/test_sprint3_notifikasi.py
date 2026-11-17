"""
Fast tests (no browser) for Sprint 3 Bagian 3 / PRD 5.3 BR-8: notification delivery status on the
simulated outside channel, 1 send + max 3 automatic retries, and the Admin's "Kirim Ulang".
The in-app notification is always kept; a failed delivery never undoes the status change.
All writes go to the separate test database (tests/conftest.py).
"""
import random

import pytest
from sqlalchemy import create_engine, inspect, text

from app.controllers.kontrol_notifikasi import (
    PESAN_KIRIM_ULANG_GAGAL, PESAN_KIRIM_ULANG_OK, PESAN_TIDAK_ADA_GAGAL, KontrolNotifikasi,
)
from app.database import SessionLocal, pastikan_kolom_terbaru
from app.models.entities import Laporan, Notifikasi, RiwayatStatus, WorkOrder
from app.services import pengiriman_notifikasi as kanal
from app.services.alur_status import kirim_notifikasi
from app.services.pengiriman_notifikasi import (
    ENV_TINGKAT_GAGAL, KIRIM_GAGAL, KIRIM_TERKIRIM, jalankan_siklus_kirim, tingkat_gagal,
)
from tests.test_sprint2 import (  # noqa: F401 (db_bersih is a fixture)
    ADMIN, KABID, PENILIK, WARGA, WARGA_LAIN, WO, ambil, db_bersih, hitung, jpeg, klien, status,
)
from tests.test_sprint3_temuan import temuan

NTF_GAGAL_SEED = "NTF-SEED-0003"      # LAP-2026-0002 / USR-03, Gagal after 4 attempts
NTF_TERKIRIM_SEED = "NTF-SEED-0001"   # LAP-2026-0001 / USR-01, Terkirim


@pytest.fixture
def tingkat(monkeypatch):
    """tingkat("1") sets SCMS_NOTIF_TINGKAT_GAGAL for this test only."""
    monkeypatch.delenv(ENV_TINGKAT_GAGAL, raising=False)
    return lambda nilai: monkeypatch.setenv(ENV_TINGKAT_GAGAL, nilai)


def notif_tugas(id_laporan="LAP-2026-0001"):
    db = SessionLocal()
    try:
        return db.query(Notifikasi).filter_by(id_laporan=id_laporan, judul="Petugas ditugaskan").one()
    finally:
        db.close()


def tugaskan_admin():
    return klien(ADMIN).post(f"/work-orders/{WO}/assign", data={"nama_penilik": "PNL-01"})


def kirim_ulang(akun=ADMIN, id_notifikasi=NTF_GAGAL_SEED, **opsi):
    return klien(akun).post(f"/notifikasi-gagal/{id_notifikasi}/kirim-ulang", **opsi)


# ------------------------------------------------------------ failure rate from the environment
@pytest.mark.parametrize("nilai, harapan", [
    (None, 0.0), ("", 0.0), ("0", 0.0), ("0.25", 0.25), ("1", 1.0), (" 1.0 ", 1.0),
    ("abc", 0.0), ("-0.5", 0.0), ("1.5", 0.0), ("nan", 0.0), ("inf", 0.0),
])
def test_tingkat_gagal_dari_env(tingkat, nilai, harapan):
    if nilai is not None:
        tingkat(nilai)
    assert tingkat_gagal() == harapan


def test_env_dibaca_saat_pengiriman_bukan_saat_import(db_bersih, tingkat):
    tingkat("1")
    assert tingkat_gagal() == 1.0
    tingkat("0")
    assert tingkat_gagal() == 0.0


# ------------------------------------------------------------ one send cycle through ubah_status()
def test_tingkat_gagal_0_terkirim_dalam_1_percobaan(db_bersih, tingkat):
    tingkat("0")
    tugaskan_admin()
    n = notif_tugas()
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_TERKIRIM, 1)
    assert n.waktu_percobaan_terakhir is not None


def test_tingkat_gagal_1_gagal_setelah_4_percobaan_dan_status_tiket_tetap_berubah(db_bersih, tingkat):
    tingkat("1")
    r = tugaskan_admin()
    assert r.status_code == 200
    assert status() == "Ditugaskan"
    assert ambil(Laporan, "LAP-2026-0001").status == "Ditugaskan"
    assert hitung(RiwayatStatus, id_work_order=WO, status="Ditugaskan") == 1
    n = notif_tugas()
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_GAGAL, 4)
    assert n.status_baca is False  # the in-app notification is still saved and unread


@pytest.mark.parametrize("nilai", ["abc", "-1", "2", ""])
def test_env_tidak_valid_dianggap_0(db_bersih, tingkat, nilai):
    tingkat(nilai)
    tugaskan_admin()
    n = notif_tugas()
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_TERKIRIM, 1)


def test_berhasil_pada_percobaan_ulang_ketiga(tingkat, monkeypatch):
    tingkat("0.5")
    urutan = iter([0.1, 0.2, 0.9])  # fail, fail, success
    monkeypatch.setattr(random, "random", lambda: next(urutan))
    n = Notifikasi(id_notifikasi="NTF-X", jumlah_percobaan=0)
    assert jalankan_siklus_kirim(n) is True
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_TERKIRIM, 3)


def test_kanal_rusak_tidak_melempar_exception_dan_tidak_membatalkan_status(db_bersih, monkeypatch):
    def rusak(_notif):
        raise ConnectionError("gateway SMS mati")
    monkeypatch.setattr(kanal, "kirim_ke_kanal", rusak)
    tugaskan_admin()
    assert status() == "Ditugaskan"
    n = notif_tugas()
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_GAGAL, 4)


def test_jalur_laporan_diterima_ikut_tercatat(db_bersih, tingkat):
    """kontrol_pelaporan's "Laporan diterima" goes through kirim_notifikasi() too."""
    tingkat("1")
    r = klien(WARGA).post("/lapor", data={"lokasi_jalan": "Jl. Manyar Kertoarjo No. 7",
                                          "deskripsi": "Lubang besar di jalur lambat",
                                          "kategori_pilihan": "Jalan Berlubang", "id_wilayah": "WIL-01"},
                          files={"foto": ("a.jpg", jpeg(), "image/jpeg")})
    assert "LAP-2026-0004" in r.text
    db = SessionLocal()
    n = db.query(Notifikasi).filter_by(id_laporan="LAP-2026-0004", judul="Laporan diterima").one()
    db.close()
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_GAGAL, 4)


def test_tiket_temuan_murni_tidak_membuat_notifikasi(db_bersih, tingkat):
    tingkat("1")
    awal = hitung(Notifikasi)
    hasil = temuan()
    assert hasil["success"]
    klien(ADMIN).post(f"/verifikasi/{hasil['ticket_id']}/skip-inspection")
    assert ambil(WorkOrder, hasil["ticket_id"]).status_work_order == "Disetujui"
    assert hitung(Notifikasi, id_laporan=hasil["id_laporan"]) == 0
    assert hitung(Notifikasi) == awal
    db = SessionLocal()
    try:
        assert kirim_notifikasi(db, db.get(Laporan, hasil["id_laporan"]), "x", "y") is None
    finally:
        db.close()


# ------------------------------------------------------------ citizen still sees it in-app
def test_notifikasi_gagal_tetap_tampil_di_halaman_notifikasi_warga(db_bersih, tingkat):
    halaman = klien(WARGA_LAIN).get("/notifikasi").text
    assert f'id="notif-{NTF_GAGAL_SEED}"' in halaman
    tingkat("1")
    tugaskan_admin()
    n = notif_tugas()
    assert n.status_kirim == KIRIM_GAGAL
    assert f'id="notif-{n.id_notifikasi}"' in klien(WARGA).get("/notifikasi").text


# ------------------------------------------------------------ Notifikasi Gagal page & Kirim Ulang
def test_admin_melihat_daftar_dan_tombol_kirim_ulang(db_bersih):
    r = klien(ADMIN).get("/notifikasi-gagal")
    assert r.status_code == 200
    assert f'data-notifikasi="{NTF_GAGAL_SEED}"' in r.text and 'data-laporan="LAP-2026-0002"' in r.text
    for teks in ("REP-2026-00298", "Ibu Sari Rahayu", "Laporan diverifikasi", 'data-percobaan="4"', "WIB"):
        assert teks in r.text
    assert f'id="kirimUlang-{NTF_GAGAL_SEED}"' in r.text
    assert f'data-notifikasi="{NTF_TERKIRIM_SEED}"' not in r.text  # only Gagal is listed


def test_kirim_ulang_berhasil(db_bersih, tingkat):
    tingkat("0")
    r = kirim_ulang()
    assert r.status_code == 200 and str(r.url).endswith("/notifikasi-gagal")
    assert PESAN_KIRIM_ULANG_OK in r.text
    n = ambil(Notifikasi, NTF_GAGAL_SEED)
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_TERKIRIM, 5)  # 4 earlier + 1 new attempt
    assert f'data-notifikasi="{NTF_GAGAL_SEED}"' not in r.text
    assert PESAN_TIDAK_ADA_GAGAL in r.text and 'id="badgeNotifGagal"' not in r.text


def test_kirim_ulang_masih_gagal(db_bersih, tingkat):
    tingkat("1")
    r = kirim_ulang()
    assert PESAN_KIRIM_ULANG_GAGAL in r.text
    n = ambil(Notifikasi, NTF_GAGAL_SEED)
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_GAGAL, 8)  # one more cycle of 4
    assert f'data-notifikasi="{NTF_GAGAL_SEED}"' in r.text


def test_notifikasi_yang_bukan_gagal_tidak_dikirim_ulang(db_bersih, tingkat):
    tingkat("0")
    r = kirim_ulang(id_notifikasi=NTF_TERKIRIM_SEED)
    assert "bukan Gagal" in r.text and "tidak dikirim ulang" in r.text
    n = ambil(Notifikasi, NTF_TERKIRIM_SEED)
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_TERKIRIM, 1)


def test_kirim_ulang_dua_kali_hanya_sekali_dikirim(db_bersih, tingkat):
    tingkat("0")
    db = SessionLocal()
    try:
        assert KontrolNotifikasi(db).kirim_ulang(NTF_GAGAL_SEED)["success"] is True
        kedua = KontrolNotifikasi(db).kirim_ulang(NTF_GAGAL_SEED)
    finally:
        db.close()
    assert kedua["success"] is False and kedua["jenis"] == "peringatan"
    assert ambil(Notifikasi, NTF_GAGAL_SEED).jumlah_percobaan == 5


def test_kirim_ulang_notifikasi_tidak_dikenal_404(db_bersih):
    assert kirim_ulang(id_notifikasi="NTF-TIDAK-ADA").status_code == 404


# ------------------------------------------------------------ access rights (PRD 5.3 table)
def test_kabid_melihat_daftar_tanpa_tombol_dan_post_403(db_bersih, tingkat):
    tingkat("0")
    r = klien(KABID).get("/notifikasi-gagal")
    assert r.status_code == 200
    assert f'data-notifikasi="{NTF_GAGAL_SEED}"' in r.text
    assert "tombol-kirim-ulang" not in r.text and "Kirim Ulang</button>" not in r.text
    assert kirim_ulang(KABID, follow_redirects=False).status_code == 403
    n = ambil(Notifikasi, NTF_GAGAL_SEED)
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_GAGAL, 4)


@pytest.mark.parametrize("akun", [WARGA, PENILIK])
def test_warga_dan_penilik_ditolak(db_bersih, akun):
    assert klien(akun).get("/notifikasi-gagal", follow_redirects=False).status_code == 403
    assert kirim_ulang(akun, follow_redirects=False).status_code == 403
    assert ambil(Notifikasi, NTF_GAGAL_SEED).jumlah_percobaan == 4


def test_tamu_diarahkan_ke_login(db_bersih):
    r = klien().get("/notifikasi-gagal", follow_redirects=False)
    assert r.status_code in (302, 303) and "/Login" in r.headers["location"]


def test_menu_dan_badge_hanya_untuk_admin_dan_kabid(db_bersih):
    for akun in (ADMIN, KABID):
        for halaman in ("/Dashboard", "/work-orders", "/verifikasi", "/master-data", "/laporan-kinerja"):
            teks = klien(akun).get(halaman).text
            assert 'id="menuNotifikasiGagal"' in teks, (akun, halaman)
            assert 'id="badgeNotifGagal"' in teks and ">1</span>" in teks, (akun, halaman)
    for akun, halaman in ((PENILIK, "/TugasLapangan"), (WARGA, "/Beranda")):
        assert 'id="menuNotifikasiGagal"' not in klien(akun).get(halaman).text


# ------------------------------------------------------------ seed & old database
def test_seed_notifikasi_status_kirim(db_bersih):
    for id_n in ("NTF-SEED-0001", "NTF-SEED-0002"):
        n = ambil(Notifikasi, id_n)
        assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_TERKIRIM, 1)
    n = ambil(Notifikasi, NTF_GAGAL_SEED)
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_GAGAL, 4)


def test_database_lama_mendapat_kolom_percobaan(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'lama.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE notifikasi (id_notifikasi VARCHAR(20) PRIMARY KEY, "
                          "status_kirim VARCHAR(20), judul VARCHAR(100), waktu_kirim TIMESTAMP)"))
        conn.execute(text("INSERT INTO notifikasi (id_notifikasi, status_kirim) VALUES ('NTF-1', 'Terkirim')"))
    pastikan_kolom_terbaru(eng)
    kolom = {c["name"] for c in inspect(eng).get_columns("notifikasi")}
    assert {"jumlah_percobaan", "waktu_percobaan_terakhir"} <= kolom
    with eng.connect() as conn:
        assert conn.execute(text("SELECT jumlah_percobaan FROM notifikasi")).scalar() == 0
    pastikan_kolom_terbaru(eng)  # idempotent
