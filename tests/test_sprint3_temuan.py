"""
Fast tests (no browser) for Sprint 3 Bagian 2A / CO-2 (PRD 5.3 "Temuan baru", team decisions 5.9 no. 3,
11 and 12): an inspector's finding goes through the citizen report flow without a citizen, never
raises exposure, never notifies anyone by itself, and every page copes with laporan.id_warga = NULL.
"""
import csv
import io
import os
import types

import pytest
from sqlalchemy import create_engine, inspect, text

from app.controllers.kontrol_inspeksi import (
    PESAN_BUKAN_TUGAS, PESAN_FOTO_TEMUAN, PESAN_KATEGORI_TEMUAN, PESAN_STATUS_TEMUAN, PESAN_TITIK_TEMUAN,
    STATUS_BOLEH_TEMUAN, KontrolInspeksi,
)
from app.controllers.kontrol_laporan_kinerja import KontrolLaporanKinerja
from app.controllers.kontrol_pelaporan import KontrolPelaporan
from app.database import SessionLocal, izinkan_id_warga_kosong, pastikan_kolom_terbaru
from app.models.entities import Laporan, Notifikasi, PenilikJalan, RiwayatStatus, WorkOrder
from database.seed import pwd_context
from tests.test_sprint2 import (  # noqa: F401 (db_bersih is a fixture)
    ADMIN, KABID, PENILIK, WARGA, ambil, db_bersih, hitung, jpeg, klien,
)

WO_ASAL = "REP-2026-00298"   # Ditugaskan to PNL-01 (Budi Santoso), Wilayah Gubeng
TITIK_BARU = (-7.26700, 112.74950)          # > 50 m from every active ticket
TITIK_00341 = (-7.27975, 112.76185)         # ~8 m from REP-2026-00341 (Jalan Berlubang, USR-01)


def temuan(kategori="Retak Permukaan", titik=TITIK_BARU, foto=True, nama="temuan_sudirman.jpg",
           deskripsi="Retak memanjang di bahu jalan sekitar 3 meter", id_wo=WO_ASAL, id_penilik="PNL-01"):
    db = SessionLocal()
    try:
        return KontrolInspeksi(db).catat_temuan(
            id_wo, id_penilik, nama, jpeg() if foto is True else foto, kategori, deskripsi,
            titik[0] if titik else None, titik[1] if titik else None, "Jl. Sudirman No. 80, Surabaya")
    finally:
        db.close()


def post_temuan(akun=PENILIK, id_wo=WO_ASAL, **ubah):
    data = {"kategori_temuan": "Retak Permukaan", "deskripsi_temuan": "Retak memanjang di bahu jalan sekitar 3 meter",
            "latitude_temuan": str(TITIK_BARU[0]), "longitude_temuan": str(TITIK_BARU[1]), "lokasi_temuan": "Jl. Sudirman"}
    data.update(ubah)
    return klien(akun).post(f"/TugasLapangan/{id_wo}/temuan", data=data,
                            files={"foto_temuan": ("temuan.jpg", jpeg(), "image/jpeg")}, follow_redirects=False)


def set_status(id_wo, status):
    db = SessionLocal()
    db.get(WorkOrder, id_wo).status_work_order = status
    db.commit()
    db.close()


def jumlah_wo():
    db = SessionLocal()
    try:
        return db.query(WorkOrder).count()
    finally:
        db.close()


# --------------------------------------------------------------- validation
@pytest.mark.parametrize("ubah, pesan", [
    ({"foto": None}, PESAN_FOTO_TEMUAN),
    ({"kategori": ""}, PESAN_KATEGORI_TEMUAN),
    ({"kategori": "Jalan Bergelombang"}, PESAN_KATEGORI_TEMUAN),
    ({"titik": None}, PESAN_TITIK_TEMUAN),
    ({"deskripsi": "retak"}, "Deskripsi laporan minimal harus terdiri dari 10 karakter"),
    ({"foto": b"%PDF bukan gambar"}, "Format harus JPG/PNG dan ukuran maksimal 10MB"),
])
def test_validasi_temuan(db_bersih, ubah, pesan):
    sebelum = jumlah_wo()
    hasil = temuan(**ubah)
    assert hasil == {"success": False, "message": pesan}
    assert jumlah_wo() == sebelum and hitung(Laporan, sumber="Temuan Penilik") == 0


def test_validasi_lewat_form_mempertahankan_isian(db_bersih):
    r = klien(PENILIK).post(f"/TugasLapangan/{WO_ASAL}/temuan", data={
        "kategori_temuan": "Retak Permukaan", "deskripsi_temuan": "Retak memanjang di bahu jalan",
        "latitude_temuan": "-7.267", "longitude_temuan": "112.7495"})
    assert PESAN_FOTO_TEMUAN in r.text and 'id="panelTemuan"' in r.text and " open>" in r.text
    assert "Retak memanjang di bahu jalan" in r.text
    r = post_temuan(latitude_temuan="bukan-angka")
    assert PESAN_TITIK_TEMUAN in r.text


# --------------------------------------------------------------------- RBAC
@pytest.mark.parametrize("akun", [ADMIN, KABID, WARGA])
def test_rbac_selain_penilik_ditolak(db_bersih, akun):
    assert post_temuan(akun).status_code == 403
    assert hitung(Laporan, sumber="Temuan Penilik") == 0


def test_tanpa_login_dialihkan(db_bersih):
    assert post_temuan(None).headers["location"] == "/Login"


def test_penilik_lain_ditolak(db_bersih):
    db = SessionLocal()
    db.add(PenilikJalan(id_penilik="PNL-09", id_wilayah="WIL-01", nama_penilik="Andi Wijaya", nip="199001012020011009",
                        email_penilik="andi.wijaya@dpupr.surabaya.go.id", password_hash=pwd_context.hash("password123"),
                        status_ketersediaan="Tersedia", is_active=True))
    db.commit()
    db.close()
    assert temuan(id_penilik="PNL-09") == {"success": False, "message": PESAN_BUKAN_TUGAS}
    assert post_temuan("andi.wijaya@dpupr.surabaya.go.id").status_code == 404  # not their ticket
    assert 'id="panelTemuan"' not in klien(PENILIK).get("/TugasLapangan/REP-2026-00341").text  # not assigned


@pytest.mark.parametrize("status", ["Disetujui", "Selesai", "Ditutup", "Dilaporkan"])
def test_temuan_hanya_dari_tiket_aktif_yang_dikerjakan(db_bersih, status):
    set_status(WO_ASAL, status)
    assert temuan() == {"success": False, "message": PESAN_STATUS_TEMUAN}
    assert 'id="panelTemuan"' not in klien(PENILIK).get(f"/TugasLapangan/{WO_ASAL}").text


@pytest.mark.parametrize("status", STATUS_BOLEH_TEMUAN)
def test_temuan_boleh_selama_inspeksi_dan_perbaikan(db_bersih, status):
    set_status(WO_ASAL, status)
    assert temuan()["success"] is True
    assert ambil(WorkOrder, WO_ASAL).status_work_order == status  # the inspected ticket keeps its status


# ------------------------------------------------- dedup, exposure, history
def test_temuan_menjadi_tiket_baru_tanpa_warga(db_bersih):
    hasil = temuan()
    assert hasil["success"] and not hasil["is_duplicate"]
    assert hasil["message"].startswith(f"Temuan dicatat sebagai tiket baru {hasil['ticket_id']}")
    wo = ambil(WorkOrder, hasil["ticket_id"])
    assert (wo.status_work_order, wo.exposure_count, wo.id_wilayah, wo.kategori_kerusakan) == (
        "Dilaporkan", 1, "WIL-01", "Retak Permukaan")
    db = SessionLocal()
    lap = db.get(Laporan, hasil["id_laporan"])
    assert (lap.id_warga, lap.sumber, lap.id_penilik_pencatat) == (None, "Temuan Penilik", "PNL-01")
    assert lap.label_pelapor == "Temuan Penilik: Budi Santoso" and db.get(WorkOrder, wo.id_work_order).dari_temuan
    riwayat = [r.keterangan for r in db.query(RiwayatStatus).filter_by(id_work_order=wo.id_work_order)]
    assert riwayat == ["Temuan penilik Budi Santoso diterima sistem"]
    db.close()


def test_riwayat_tiket_asal_mencatat_temuan(db_bersih):
    hasil = temuan()
    db = SessionLocal()
    entri = [r for r in db.query(RiwayatStatus).filter_by(id_work_order=WO_ASAL)
             if (r.keterangan or "").startswith("Penilik mencatat temuan baru")]
    db.close()
    assert [(e.status, e.keterangan, e.aktor) for e in entri] == [
        ("Ditugaskan", f"Penilik mencatat temuan baru {hasil['ticket_id']} / {hasil['id_laporan']}", "Budi Santoso")]


def test_temuan_digabung_tidak_menambah_exposure_dan_tidak_memberi_notifikasi(db_bersih):
    sebelum = ambil(WorkOrder, "REP-2026-00341")
    notif_awal = hitung(Notifikasi)
    hasil = temuan(kategori="Jalan Berlubang", titik=TITIK_00341, nama="temuan_kertajaya.jpg")
    assert hasil["success"] and hasil["is_duplicate"] and hasil["ticket_id"] == "REP-2026-00341"
    assert hasil["message"] == "Temuan digabungkan dengan tiket aktif REP-2026-00341"
    sesudah = ambil(WorkOrder, "REP-2026-00341")
    assert sesudah.exposure_count == sebelum.exposure_count == 1
    assert hitung(Notifikasi) == notif_awal  # neither the inspector nor the ticket's citizen is notified


def test_tiket_temuan_murni_tidak_pernah_mengirim_notifikasi(db_bersih):
    hasil = temuan()
    klien(ADMIN).post(f"/verifikasi/{hasil['ticket_id']}/skip-inspection")  # Retak 4.5: ambiguous score
    assert ambil(WorkOrder, hasil["ticket_id"]).status_work_order == "Disetujui"
    assert hitung(Notifikasi, id_laporan=hasil["id_laporan"]) == 0
    db = SessionLocal()
    assert db.query(Notifikasi).filter(Notifikasi.id_warga.is_(None)).count() == 0
    db.close()


def test_warga_yang_bergabung_ke_tiket_temuan_mendapat_notifikasi(db_bersih):
    hasil = temuan()
    db = SessionLocal()
    warga = KontrolPelaporan(db).kirim_laporan(
        filename="retak_bahu_sudirman.jpg", file_size_mb=0.1, lokasi_jalan="Jl. Sudirman No. 80",
        deskripsi="Retak memanjang di bahu jalan Sudirman", kategori_pilihan="Retak Permukaan",
        latitude=TITIK_BARU[0] + 0.00002, longitude=TITIK_BARU[1] + 0.00002, id_warga="USR-01")
    db.close()
    assert warga["is_duplicate"] and warga["ticket_id"] == hasil["ticket_id"]
    assert warga["exposure_count"] == 2  # team decision 5.9 no. 11: the finding counts as one source
    assert hitung(Notifikasi, id_laporan=warga["id_laporan"], judul="Laporan digabungkan") == 1
    klien(ADMIN).post(f"/verifikasi/{hasil['ticket_id']}/skip-inspection")
    assert hitung(Notifikasi, id_laporan=warga["id_laporan"], judul="Laporan diverifikasi") == 1
    assert hitung(Notifikasi, id_laporan=hasil["id_laporan"]) == 0


def test_temuan_memakai_analisis_ai_yang_sama(db_bersih):
    hasil = temuan(nama="kucing_di_bahu_jalan.jpg")  # simulation: not recognised -> manual review (BR-1)
    assert hasil["success"] and hasil["perlu_tinjauan_manual"]
    assert ambil(WorkOrder, hasil["ticket_id"]).perlu_tinjauan_manual is True
    hasil2 = temuan(kategori="Retak Permukaan", nama="retak_bahu.jpg", titik=(-7.2600, 112.7400))
    assert hasil2["severity_score"] == 5.4 and not hasil2["perlu_tinjauan_manual"]  # AI category kept


# ------------------------------------------- pages and CSV with id_warga NULL
def test_halaman_dan_csv_aman_tanpa_id_warga(db_bersih):
    hasil = temuan()
    id_wo = hasil["ticket_id"]
    halaman = [
        (ADMIN, f"/verifikasi?ticket_id={id_wo}"), (KABID, "/verifikasi"), (ADMIN, "/Dashboard"),
        (ADMIN, f"/work-orders?select_ticket={id_wo}"), (KABID, "/laporan-kinerja"),
        (PENILIK, f"/TugasLapangan/{WO_ASAL}"), (PENILIK, "/TugasLapangan"), (PENILIK, "/Dashboard"),
        (WARGA, "/Beranda"), (WARGA, "/notifikasi"), (WARGA, "/lacak?id=LAP-2026-0001"),
        (ADMIN, "/master-data"),
    ]
    for akun, url in halaman:
        r = klien(akun).get(url)
        assert r.status_code == 200, url
    verifikasi = klien(ADMIN).get(f"/verifikasi?ticket_id={id_wo}").text
    assert "label-sumber-temuan" in verifikasi and "Pelapor: Temuan Penilik: Budi Santoso" in verifikasi
    assert "Pelapor: Temuan Penilik: Budi Santoso" in klien(ADMIN).get(f"/work-orders?select_ticket={id_wo}").text
    assert "label-sumber-temuan" in klien(ADMIN).get("/Dashboard").text
    # the finding's report ID is "not found" for every citizen (it belongs to no citizen)
    assert "tidak ditemukan" in klien(WARGA).get(f"/lacak?id={hasil['id_laporan']}").text
    db = SessionLocal()
    k = KontrolLaporanKinerja(db)
    data = k.rekap()
    assert id_wo in [b["id_work_order"] for b in data["tiket"]]
    baris = list(csv.reader(io.StringIO(k.csv_per_tiket(data).lstrip("﻿"))))
    assert any(b[0] == id_wo for b in baris[1:])
    assert k.csv_per_wilayah(data)
    db.close()
    for jenis in ("wilayah", "tiket"):
        assert klien(KABID).get(f"/laporan-kinerja/unduh?jenis={jenis}").status_code == 200


def test_tugas_lapangan_menampilkan_pelapor_dan_form_temuan(db_bersih):
    html = klien(PENILIK).get(f"/TugasLapangan/{WO_ASAL}").text
    assert 'id="bukaFormTemuan"' in html and "Catat Temuan Baru" in html and 'id="petaTemuan"' in html
    assert "/static/js/peta_lokasi.js" in html and "Pelapor: Ibu Sari Rahayu" in html


# -------------------------------------------------------------- schema
def _db_lama(path):
    """A Sprint 1/2 database: laporan.id_warga NOT NULL, with rows, an index and foreign keys."""
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE warga (id_warga VARCHAR(20) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE work_order (id_work_order VARCHAR(20) PRIMARY KEY)"))
        conn.execute(text(
            "CREATE TABLE laporan (id_laporan VARCHAR(20) NOT NULL, id_work_order VARCHAR(20), "
            "id_warga VARCHAR(20) NOT NULL, deskripsi TEXT NOT NULL, url_foto VARCHAR(255) NOT NULL, "
            "PRIMARY KEY (id_laporan), FOREIGN KEY(id_work_order) REFERENCES work_order (id_work_order), "
            "FOREIGN KEY(id_warga) REFERENCES warga (id_warga))"))
        conn.execute(text("CREATE INDEX ix_laporan_id_laporan ON laporan (id_laporan)"))
        conn.execute(text("CREATE TABLE notifikasi (id_notifikasi VARCHAR(20) PRIMARY KEY, id_laporan VARCHAR(20) "
                          "REFERENCES laporan (id_laporan))"))
        conn.execute(text("INSERT INTO warga VALUES ('USR-01')"))
        conn.execute(text("INSERT INTO work_order VALUES ('REP-1')"))
        for i in range(1, 4):
            conn.execute(text(f"INSERT INTO laporan VALUES ('LAP-{i}', 'REP-1', 'USR-01', 'deskripsi {i}', 'u{i}.jpg')"))
        conn.execute(text("INSERT INTO notifikasi VALUES ('NTF-1', 'LAP-1')"))
    return eng


def test_sqlite_lama_dibangun_ulang_tanpa_kehilangan_data(tmp_path):
    eng = _db_lama(tmp_path / "lama.db")
    pastikan_kolom_terbaru(eng)
    kolom = {c["name"]: c for c in inspect(eng).get_columns("laporan")}
    assert kolom["id_warga"]["nullable"] is True and kolom["deskripsi"]["nullable"] is False
    assert {"sumber", "id_penilik_pencatat", "perlu_tinjauan_manual"} <= set(kolom)
    with eng.connect() as conn:
        assert conn.execute(text("SELECT id_laporan, id_warga, deskripsi, sumber FROM laporan ORDER BY 1")).all() == [
            (f"LAP-{i}", "USR-01", f"deskripsi {i}", "Warga") for i in range(1, 4)]
        indeks = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='laporan'"))}
        assert "ix_laporan_id_laporan" in indeks
        fk = {(r[2], r[3]) for r in conn.execute(text("PRAGMA foreign_key_list(laporan)"))}
        assert {("warga", "id_warga"), ("work_order", "id_work_order")} <= fk
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
        assert conn.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE name='laporan__baru'")).scalar() == 0
        conn.execute(text("INSERT INTO laporan (id_laporan, id_warga, deskripsi, url_foto, sumber) "
                          "VALUES ('LAP-T', NULL, 'temuan penilik', 't.jpg', 'Temuan Penilik')"))
    pastikan_kolom_terbaru(eng)  # idempotent: second run leaves the table and its rows alone
    with eng.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM laporan")).scalar() == 3


def test_migrasi_non_sqlite_memakai_drop_not_null(monkeypatch):
    """PostgreSQL path without a server: the statement must be ALTER COLUMN ... DROP NOT NULL."""
    import sqlalchemy
    dijalankan = []
    kolom = {"nullable": False}
    monkeypatch.setattr(sqlalchemy, "inspect", lambda _: types.SimpleNamespace(
        get_columns=lambda t: [{"name": "id_warga", **kolom}]))
    conn = types.SimpleNamespace(dialect=types.SimpleNamespace(name="postgresql"),
                                 execute=lambda stmt: dijalankan.append(str(stmt)))
    izinkan_id_warga_kosong(conn)
    assert dijalankan == ["ALTER TABLE laporan ALTER COLUMN id_warga DROP NOT NULL"]
    kolom["nullable"] = True
    izinkan_id_warga_kosong(conn)  # already nullable: nothing to do
    assert len(dijalankan) == 1


@pytest.mark.skipif(not os.getenv("SCMS_TEST_POSTGRES_URL"),
                    reason="set SCMS_TEST_POSTGRES_URL to a disposable PostgreSQL database to run this check")
def test_migrasi_postgresql_sungguhan():
    """Runs in its own temporary schema, so the real tables of that database are not touched."""
    eng = create_engine(os.environ["SCMS_TEST_POSTGRES_URL"])
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS scms_uji_migrasi CASCADE"))
        conn.execute(text("CREATE SCHEMA scms_uji_migrasi"))
        conn.execute(text("SET search_path TO scms_uji_migrasi"))
        conn.execute(text("CREATE TABLE laporan (id_laporan VARCHAR(20) PRIMARY KEY, id_warga VARCHAR(20) NOT NULL)"))
        conn.execute(text("INSERT INTO laporan VALUES ('LAP-1', 'USR-01')"))
        izinkan_id_warga_kosong(conn)
        izinkan_id_warga_kosong(conn)
        kolom = {c["name"]: c for c in inspect(conn).get_columns("laporan", schema="scms_uji_migrasi")}
        assert kolom["id_warga"]["nullable"] is True
        assert conn.execute(text("SELECT COUNT(*) FROM laporan")).scalar() == 1
        conn.execute(text("DROP SCHEMA scms_uji_migrasi CASCADE"))
