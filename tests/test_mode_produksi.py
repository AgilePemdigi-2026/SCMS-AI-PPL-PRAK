"""
SCMS_PRODUKSI (server mode): demo/test helpers are not rendered on the production server.
The flag is read per request (app.konfigurasi.mode_produksi), so monkeypatch.setenv is enough.
"""
import pytest
from fastapi.testclient import TestClient

from app.konfigurasi import mode_produksi
from app.main import app
from database.seed import seed_data

ADMIN = "admin@dpupr.surabaya.go.id"
WARGA = "0812xxxxxxx"

# page -> (account, texts that only the demo/test helpers put on that page)
HALAMAN = {
    "/Login": (None, ["Kredensial Aktor", "password123"]),
    "/lapor": (WARGA, ["demoBerkas", "isiDeskripsiContoh", "Atau buat berkas uji coba", "Isi Contoh Deskripsi Baru"]),
    "/Dashboard": (ADMIN, ["Simulasi Skenario Filter Kosong"]),
}


@pytest.fixture(scope="module", autouse=True)
def data_awal():
    seed_data(verbose=False)


def buka(path: str) -> str:
    akun, _ = HALAMAN[path]
    c = TestClient(app)
    if akun:
        r = c.post("/Login", data={"identifier": akun, "password": "password123"}, follow_redirects=False)
        assert r.status_code == 303, r.text[:200]
    r = c.get(path)
    assert r.status_code == 200
    return r.text


@pytest.mark.parametrize("path", list(HALAMAN))
def test_produksi_menyembunyikan_alat_bantu_demo(monkeypatch, path):
    monkeypatch.setenv("SCMS_PRODUKSI", "1")
    html = buka(path)
    for teks in HALAMAN[path][1]:
        assert teks not in html, f"{teks!r} masih tampil di {path} pada mode produksi"


@pytest.mark.parametrize("nilai", ["0", None])
@pytest.mark.parametrize("path", list(HALAMAN))
def test_bukan_produksi_menampilkan_alat_bantu_demo(monkeypatch, path, nilai):
    if nilai is None:
        monkeypatch.delenv("SCMS_PRODUKSI", raising=False)
    else:
        monkeypatch.setenv("SCMS_PRODUKSI", nilai)
    html = buka(path)
    for teks in HALAMAN[path][1]:
        assert teks in html, f"{teks!r} tidak tampil di {path} di luar mode produksi"


def test_produksi_tetap_menampilkan_form_dan_bantuan_login(monkeypatch):
    monkeypatch.setenv("SCMS_PRODUKSI", "1")
    html = buka("/Login")
    assert 'id="identifier"' in html and 'id="password"' in html
    assert "Gunakan akun Warga" in html  # help text above the form stays


def test_produksi_form_lapor_tetap_lengkap(monkeypatch):
    monkeypatch.setenv("SCMS_PRODUKSI", "1")
    html = buka("/lapor")
    for bagian in ('id="formLaporan"', 'id="fileInputAsli"', 'id="deskripsi"', 'id="tombolKirimLaporan"',
                   "function hitungKarakter", "function lanjutKeStep4"):
        assert bagian in html


def test_bendera_dibaca_saat_dipakai(monkeypatch):
    monkeypatch.delenv("SCMS_PRODUKSI", raising=False)
    assert mode_produksi() is False
    monkeypatch.setenv("SCMS_PRODUKSI", "1")
    assert mode_produksi() is True
    for nilai in ("0", "", "tidak"):
        monkeypatch.setenv("SCMS_PRODUKSI", nilai)
        assert mode_produksi() is False
