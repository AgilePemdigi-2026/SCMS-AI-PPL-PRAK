"""
Fixes after Sprint 3 (no browser needed):

* Bug 1 - one submit, one report: the /lapor form carries a one-time token (token_kirim). A second
  POST with the same token (double click while YOLOv8 runs on the CPU) creates no new report and
  points to the first one; a simultaneous duplicate is stopped by the UNIQUE index.
* Bug 2 - PostgreSQL sessions run in UTC, so a container with TZ=Asia/Jakarta no longer shifts
  stored times by 7 hours.
* Change 3 - Penilik Jalan no longer use the Work Order page: GET /work-orders redirects them to
  Tugas Lapangan, the tab is gone from their menu and Dashboard rows link to Tugas Lapangan.
"""
import io
import re

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

import app.services.penyimpanan as modul_penyimpanan
from app.controllers.kontrol_pelaporan import KontrolPelaporan
from app.database import SessionLocal, buat_connect_args, pastikan_kolom_terbaru
from app.main import app
from app.models.entities import Laporan, WorkOrder
from database.seed import seed_data

ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"   # PNL-01, WIL-01
WARGA = "0812xxxxxxx"                           # USR-01
WO_DITUGASKAN = "REP-2026-00298"                # Ditugaskan to PNL-01
WO_DISETUJUI = "REP-2026-00341"                 # Disetujui, no inspector yet


def jpeg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (40, 30), (90, 90, 90)).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    seed_data(verbose=False)
    monkeypatch.setattr(modul_penyimpanan, "DIREKTORI_UNGGAHAN", tmp_path)
    return tmp_path


def klien(identifier=None) -> TestClient:
    c = TestClient(app)
    if identifier:
        r = c.post("/Login", data={"identifier": identifier, "password": "password123"}, follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
    return c


def lapor(c, token=None, lat="-7.30001", lng="112.70001"):
    data = {"lokasi_jalan": "Jl. Uji Kirim Ganda No. 7, Surabaya", "latitude": lat, "longitude": lng,
            "deskripsi": "Lubang besar baru muncul setelah hujan deras", "kategori_pilihan": "Jalan Berlubang",
            "id_wilayah": "WIL-01"}
    if token is not None:
        data["token_kirim"] = token
    return c.post("/lapor", data=data, files={"foto": ("foto_jalan.jpg", jpeg(), "image/jpeg")},
                  follow_redirects=False)


def jumlah_laporan() -> int:
    db = SessionLocal()
    try:
        return db.query(Laporan).count()
    finally:
        db.close()


def token_di_form(html: str) -> str:
    m = re.search(r'<input type="hidden" id="token_kirim" name="token_kirim" value="([^"]*)">', html)
    assert m, "input token_kirim tidak ada di form /lapor"
    return m.group(1)


def id_laporan_di_kartu(html: str) -> str:
    m = re.search(r'href="/lacak\?id=(LAP-\d{4}-\d+)"', html)
    assert m, "kartu hasil laporan tidak tampil"
    return m.group(1)


# --------------------------------------------------------------------------- #
# Bug 1: one submit = one report
# --------------------------------------------------------------------------- #
def test_form_lapor_berisi_token_baru_di_setiap_render(uploads):
    c = klien(WARGA)
    pertama, kedua = token_di_form(c.get("/lapor").text), token_di_form(c.get("/lapor").text)
    assert pertama and kedua and pertama != kedua
    assert re.fullmatch(r"[0-9a-f-]{36}", pertama)


def test_form_gagal_validasi_tetap_berisi_token(uploads):
    c = klien(WARGA)
    r = c.post("/lapor", data={"lokasi_jalan": "", "deskripsi": "pendek", "token_kirim": "abc"},
               files={"foto": ("foto_jalan.jpg", jpeg(), "image/jpeg")})
    assert "Validasi Gagal" in r.text and token_di_form(r.text)


def test_dua_post_dengan_token_sama_hanya_membuat_satu_laporan(uploads):
    c = klien(WARGA)
    token = token_di_form(c.get("/lapor").text)
    sebelum = jumlah_laporan()

    r1 = lapor(c, token)
    assert r1.status_code == 303 and r1.headers["location"] == "/lapor"
    id_pertama = id_laporan_di_kartu(c.get("/lapor").text)
    assert jumlah_laporan() == sebelum + 1
    assert len(list(uploads.iterdir())) == 1

    r2 = lapor(c, token)  # the second click of the same form
    assert r2.status_code == 303 and r2.headers["location"] == "/lapor"
    kartu = c.get("/lapor").text
    assert "Laporan berhasil dikirim" in kartu and id_laporan_di_kartu(kartu) == id_pertama
    assert jumlah_laporan() == sebelum + 1
    # the photo of the second request is not left behind in the uploads folder
    assert len(list(uploads.iterdir())) == 1
    db = SessionLocal()
    lap = db.get(Laporan, id_pertama)
    assert lap.token_kirim == token and (uploads / lap.url_foto.rsplit("/", 1)[-1]).exists()
    assert db.get(WorkOrder, lap.id_work_order).exposure_count == 1
    db.close()


def test_dua_token_berbeda_membuat_dua_laporan_dan_dedup_br3_tetap(uploads):
    c = klien(WARGA)
    sebelum = jumlah_laporan()
    lapor(c, token_di_form(c.get("/lapor").text))
    id_1 = id_laporan_di_kartu(c.get("/lapor").text)
    lapor(c, token_di_form(c.get("/lapor").text))
    kartu = c.get("/lapor").text
    id_2 = id_laporan_di_kartu(kartu)
    assert id_1 != id_2 and jumlah_laporan() == sebelum + 2
    assert "Laporan Digabungkan" in kartu  # same place: merged into the same ticket (BR-3)
    db = SessionLocal()
    assert db.get(Laporan, id_1).id_work_order == db.get(Laporan, id_2).id_work_order
    db.close()


def test_tanpa_token_tetap_bisa_membuat_laporan(uploads):
    c = klien(WARGA)
    sebelum = jumlah_laporan()
    assert lapor(c).status_code == 303
    assert lapor(c, token="").status_code == 303
    assert jumlah_laporan() == sebelum + 2
    db = SessionLocal()
    assert db.query(Laporan).filter(Laporan.token_kirim.is_(None)).count() >= 2  # many NULLs allowed
    db.close()


def test_token_laporan_warga_lain_tidak_menampilkan_laporannya(uploads):
    c = klien(WARGA)
    token = token_di_form(c.get("/lapor").text)
    lapor(c, token)
    db = SessionLocal()
    hasil = KontrolPelaporan(db).kirim_laporan("foto_jalan.jpg", 1.0, "Jl. Lain No. 1, Surabaya",
                                               "Lubang besar di jalur lambat sekali", id_warga="USR-02",
                                               token_kirim=token)
    db.close()
    assert hasil["success"] is False and "sudah dipakai" in hasil["message"]


def test_request_bersamaan_ditahan_unique_index_dan_foto_dihapus(uploads, monkeypatch):
    """Two requests with the same token that both passed the first check (they ran at the same
    time): the second commit hits the UNIQUE index, is rolled back, its photo is deleted and it
    returns the report of the first request."""
    c = klien(WARGA)
    token = token_di_form(c.get("/lapor").text)
    lapor(c, token)
    id_pertama = id_laporan_di_kartu(c.get("/lapor").text)
    sebelum = jumlah_laporan()

    asli = KontrolPelaporan._hasil_token_terpakai
    panggilan = {"n": 0}

    def belum_terlihat_dua_kali(self, tok, id_warga):
        # the early check and the check inside the first attempt still see no report (race)
        panggilan["n"] += 1
        return None if panggilan["n"] <= 2 else asli(self, tok, id_warga)

    monkeypatch.setattr(KontrolPelaporan, "_hasil_token_terpakai", belum_terlihat_dua_kali)
    commit_gagal = {"n": 0}
    from sqlalchemy.orm import Session
    commit_asli = Session.commit

    def hitung_commit(self):
        try:
            return commit_asli(self)
        except IntegrityError:
            commit_gagal["n"] += 1
            raise

    monkeypatch.setattr(Session, "commit", hitung_commit)
    db = SessionLocal()
    hasil = KontrolPelaporan(db).kirim_laporan(
        "foto_jalan.jpg", 0, "Jl. Uji Kirim Ganda No. 7, Surabaya", "Lubang besar baru muncul setelah hujan deras",
        latitude=-7.30001, longitude=112.70001, id_warga="USR-01", foto_bytes=jpeg(), token_kirim=token)
    db.close()
    assert commit_gagal["n"] == 1  # the UNIQUE index really stopped the second insert
    assert hasil["success"] is True and hasil["id_laporan"] == id_pertama
    assert jumlah_laporan() == sebelum
    assert len(list(uploads.iterdir())) == 1  # only the first request's photo


def test_unique_index_token_dibuat_migrasi_dan_boleh_banyak_null(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'lama.db'}")
    with eng.begin() as conn:  # a laporan table from before token_kirim existed
        conn.execute(text("CREATE TABLE laporan (id_laporan VARCHAR(20) PRIMARY KEY, id_warga VARCHAR(20), "
                          "deskripsi TEXT NOT NULL, url_foto VARCHAR(255) NOT NULL)"))
    pastikan_kolom_terbaru(eng)
    pastikan_kolom_terbaru(eng)  # idempotent
    with eng.begin() as conn:
        for i in range(2):
            conn.execute(text("INSERT INTO laporan (id_laporan, deskripsi, url_foto) VALUES (:i, 'x', 'y')"),
                         {"i": f"L-{i}"})
        conn.execute(text("INSERT INTO laporan (id_laporan, deskripsi, url_foto, token_kirim) VALUES ('L-9', 'x', 'y', 't')"))
    with pytest.raises(IntegrityError):
        with eng.begin() as conn:
            conn.execute(text("INSERT INTO laporan (id_laporan, deskripsi, url_foto, token_kirim) "
                              "VALUES ('L-10', 'x', 'y', 't')"))
    eng.dispose()


def test_form_mengunci_tombol_kirim_saat_submit(uploads):
    html = klien(WARGA).get("/lapor").text
    assert 'id="tombolKirimLaporan"' in html and "Mengirim laporan..." in html
    assert "var sedangKirim = false;" in html and "tombol.disabled = true;" in html
    # a submit cancelled by validation must not lock the button
    assert "checkValidity" in html


# --------------------------------------------------------------------------- #
# Bug 2: PostgreSQL session time zone
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url", ["postgresql://u:p@db:5432/scms", "postgresql+psycopg2://u:p@db/scms",
                                 "postgres://u:p@db/scms"])
def test_connect_args_postgres_memakai_utc(url):
    assert buat_connect_args(url) == {"options": "-c timezone=UTC"}


@pytest.mark.parametrize("url", ["sqlite:///./scms_dev.db", "sqlite:///:memory:"])
def test_connect_args_sqlite_tanpa_timezone(url):
    args = buat_connect_args(url)
    assert args == {"check_same_thread": False} and "options" not in args


# --------------------------------------------------------------------------- #
# Change 3: Penilik Jalan work from Tugas Lapangan, not the Work Order page
# --------------------------------------------------------------------------- #
def _get(c, url):
    return c.get(url, follow_redirects=False)


def ada_tab_work_order(html: str) -> bool:
    # _layout.html escapes the label ("&amp;"); the separate page headers write "&" directly
    return re.search(r"Penugasan &(amp;)? Work Order \(SPK\)", html) is not None


def test_penilik_work_orders_diarahkan_ke_tugas_lapangan(uploads):
    r = _get(klien(PENILIK), "/work-orders")
    assert r.status_code == 303 and r.headers["location"] == "/TugasLapangan"


def test_penilik_work_orders_tiket_miliknya_ke_detail_tugas(uploads):
    c = klien(PENILIK)
    r = _get(c, f"/work-orders?select_ticket={WO_DITUGASKAN}")
    assert r.status_code == 303 and r.headers["location"] == f"/TugasLapangan/{WO_DITUGASKAN}"
    assert _get(c, r.headers["location"]).status_code == 200


@pytest.mark.parametrize("tiket", [WO_DISETUJUI, "REP-TIDAK-ADA"])
def test_penilik_work_orders_tiket_bukan_miliknya_ke_daftar_tugas(uploads, tiket):
    r = _get(klien(PENILIK), f"/work-orders?select_ticket={tiket}")
    assert r.status_code == 303 and r.headers["location"] == "/TugasLapangan"


@pytest.mark.parametrize("akun", [ADMIN, KABID])
def test_admin_dan_kabid_tetap_membuka_work_order(uploads, akun):
    c = klien(akun)
    assert _get(c, "/work-orders").status_code == 200
    r = _get(c, f"/work-orders?select_ticket={WO_DITUGASKAN}")
    assert r.status_code == 200 and 'id="infoSudahDitugaskan"' in r.text


@pytest.mark.parametrize("halaman", ["/TugasLapangan", f"/TugasLapangan/{WO_DITUGASKAN}", "/Dashboard"])
def test_menu_penilik_tanpa_tab_work_order(uploads, halaman):
    html = _get(klien(PENILIK), halaman).text
    assert not ada_tab_work_order(html) and 'href="/work-orders' not in html
    assert 'href="/TugasLapangan"' in html and 'href="/Dashboard"' in html


@pytest.mark.parametrize("akun", [ADMIN, KABID])
@pytest.mark.parametrize("halaman", ["/Dashboard", "/work-orders", "/master-data", f"/verifikasi?ticket_id={WO_DISETUJUI}"])
def test_menu_admin_dan_kabid_tetap_ada_tab_work_order(uploads, akun, halaman):
    html = _get(klien(akun), halaman).text
    assert ada_tab_work_order(html) and 'href="/work-orders"' in html
    assert 'href="/TugasLapangan"' not in html


def test_dashboard_penilik_menautkan_tugas_miliknya_ke_tugas_lapangan(uploads):
    html = _get(klien(PENILIK), "/Dashboard").text
    assert f'href="/TugasLapangan/{WO_DITUGASKAN}"' in html
    assert "/work-orders?select_ticket=" not in html
    # a ticket of their region that is not assigned to them gets no button
    baris = re.search(rf'<tr[^>]*data-tiket="{WO_DISETUJUI}".*?</tr>', html, re.S)
    assert baris and "tombol-tugas-lapangan" not in baris.group(0)


def test_dashboard_admin_tetap_menautkan_work_order(uploads):
    html = _get(klien(ADMIN), "/Dashboard").text
    assert f'href="/work-orders?select_ticket={WO_DITUGASKAN}"' in html
    assert "/TugasLapangan/" not in html


@pytest.mark.parametrize("url,data", [
    (f"/work-orders/{WO_DISETUJUI}/assign", {"nama_penilik": "PNL-01"}),
    (f"/work-orders/{WO_DITUGASKAN}/spk", {"nomor_spk": "SPK/1", "tim_pelaksana": "Satgas Rayon Gubeng"}),
    (f"/work-orders/{WO_DITUGASKAN}/progres", {"status_baru": "Selesai"}),
    (f"/work-orders/{WO_DITUGASKAN}/kunjungan", {"catatan_kunjungan": "x"}),
])
def test_post_work_order_oleh_penilik_tetap_403(uploads, url, data):
    assert klien(PENILIK).post(url, data=data, follow_redirects=False).status_code == 403
