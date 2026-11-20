"""
Fast tests (no browser) for the Bantuan page and the responsive/accessibility markup fixes:
- GET /bantuan: every logged-in role gets 200, guests are redirected to /Login.
- The footer links to /bantuan on layout pages and on the stand-alone pages.
- Labels are linked to their inputs (for/id) on /lapor, the Dashboard and Work Order filters.
- Indonesian step labels on /lapor, no "Live Sync" text in the staff headers.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from database.seed import seed_data
from tests.test_tanpa_sla import POLA_SLA, POLA_TARGET_WAKTU  # guard patterns for the removed SLA concept

WARGA = "0812xxxxxxx"
ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"

STATUS_TIKET = ("Dilaporkan", "Disetujui", "Menunggu Inspeksi", "Menunggu Penugasan", "Ditugaskan",
                "Terinspeksi", "Dalam Proses", "Selesai", "Ditutup")


@pytest.fixture(scope="module", autouse=True)
def db_seed():
    seed_data(verbose=False)


def klien(identifier=None, password="password123") -> TestClient:
    c = TestClient(app)
    if identifier:
        r = c.post("/Login", data={"identifier": identifier, "password": password}, follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
    return c


def _teks(html: str) -> str:
    """Visible text only: drop scripts, styles and comments, then the tags."""
    html = re.sub(r"<(script|style)\b.*?</\1>|<!--.*?-->", " ", html, flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", html)


@pytest.mark.parametrize("akun, peran, kunci", [
    (WARGA, "Warga", "warga"),
    (ADMIN, "Admin", "admin"),
    (PENILIK, "Penilik Jalan", "penilik"),
    (KABID, "Kepala Bidang", "kabid"),
])
def test_bantuan_terbuka_untuk_setiap_peran(akun, peran, kunci):
    r = klien(akun).get("/bantuan")
    assert r.status_code == 200
    html = r.text
    assert 'id="halamanBantuan"' in html
    # one flow section per role, the viewer's own role is highlighted
    for nama in ("Warga", "Admin", "Penilik Jalan", "Kepala Bidang"):
        assert f'data-peran="{nama}"' in html
    bagian = re.search(rf'<section id="bantuan-{kunci}".*?</section>', html, re.S).group(0)
    assert "Peran Anda" in bagian and html.count("Peran Anda") == 1
    # every ticket status is explained
    for status in STATUS_TIKET:
        assert f'data-status="{status}"' in html, status


def test_bantuan_tanpa_login_dialihkan_ke_login():
    r = klien().get("/bantuan", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/Login")
    assert "next=%2Fbantuan" in r.headers["location"]


def test_bantuan_tanpa_target_waktu():
    teks = _teks(klien(KABID).get("/bantuan").text)
    assert not POLA_SLA.search(teks) and not POLA_TARGET_WAKTU.search(teks)


@pytest.mark.parametrize("akun, halaman", [
    (WARGA, "/Beranda"), (WARGA, "/lacak"), (WARGA, "/lapor"),
    (ADMIN, "/Dashboard"), (ADMIN, "/work-orders"), (ADMIN, "/verifikasi"),
    (KABID, "/laporan-kinerja"), (PENILIK, "/TugasLapangan"),
])
def test_footer_menautkan_halaman_bantuan(akun, halaman):
    r = klien(akun).get(halaman)
    assert r.status_code == 200, halaman
    footer = re.search(r"<footer.*?</footer>", r.text, re.S).group(0)
    assert 'href="/bantuan"' in footer, halaman


def _label_terhubung(html: str, id_input: str) -> bool:
    return f'for="{id_input}"' in html and re.search(rf'<(input|select|textarea)[^>]*\bid="{id_input}"', html)


def test_label_terhubung_ke_input_formulir_laporan():
    html = klien(WARGA).get("/lapor").text
    for id_input in ("inputCariPeta", "lokasi_jalan", "tampilanKoordinat", "id_wilayah", "kategori_pilihan", "deskripsi"):
        assert _label_terhubung(html, id_input), id_input


def test_label_terhubung_ke_filter_dashboard_dan_work_order():
    dashboard = klien(ADMIN).get("/Dashboard").text
    for id_input in ("filter_wilayah_dashboard", "filter_status_dashboard", "filter_kategori_dashboard"):
        assert _label_terhubung(dashboard, id_input), id_input
    work_order = klien(ADMIN).get("/work-orders").text
    for id_input in ("filter_wilayah_wo", "filter_status_wo"):
        assert _label_terhubung(work_order, id_input), id_input
    # the filters still submit the same field names
    for nama in ("wilayah", "status", "kategori"):
        assert f'name="{nama}"' in dashboard
    for nama in ("wilayah", "status"):
        assert f'name="{nama}"' in work_order


def test_label_langkah_dan_header_berbahasa_indonesia():
    lapor = klien(WARGA).get("/lapor").text
    for no, label in ((1, "Foto"), (2, "Lokasi"), (3, "Detail"), (4, "Tinjau")):
        assert f'aria-label="Langkah {no}: {label}"' in lapor
    tampil = _teks(lapor)
    for lama in ("Capture", "Location", "Review"):
        assert not re.search(rf"\b{lama}\b", tampil), lama
    for halaman in ("/Dashboard", "/work-orders", "/verifikasi"):
        assert "Live Sync" not in klien(ADMIN).get(halaman).text, halaman


def test_tabel_lebar_memberi_petunjuk_geser_di_layar_kecil():
    for halaman in ("/Dashboard", "/work-orders"):
        html = klien(ADMIN).get(halaman).text
        assert "Geser tabel ke samping untuk melihat kolom lain" in html, halaman
