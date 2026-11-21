"""
Security hardening C-01 .. C-04 plus small extras:

* C-01 session version: logout (and a password change) raises versi_sesi, so a copied old cookie
  is rejected; the cookie holds only id, role and version (no name or email).
* C-02 /docs, /redoc, /openapi.json are off when SCMS_PRODUKSI=1.
* C-03 failed-login limit per identifier (and a looser one per IP) -> 429.
* C-04 Origin/Referer check on state-changing methods; logout only through POST.
* Security headers, database/ganti_password.py, and the versi_sesi light migration.
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app import batas_login
from app.database import SessionLocal, pastikan_kolom_terbaru
from app.konfigurasi import opsi_dokumentasi
from app.main import app
from app.models.entities import Admin, PenilikJalan, Warga
from database import ganti_password
from database.seed import seed_data

ROOT = Path(__file__).resolve().parent.parent
ADMIN = "admin@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"
WARGA = "0812xxxxxxx"
SANDI = "password123"


@pytest.fixture(autouse=True)
def data_awal():
    seed_data(verbose=False)


def masuk(identifier=ADMIN, password=SANDI) -> TestClient:
    c = TestClient(app)
    r = c.post("/Login", data={"identifier": identifier, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    return c


def isi_cookie(c: TestClient) -> dict:
    """Decode Starlette's session cookie (base64 JSON before the signature)."""
    bagian = c.cookies.get("scms_session").split(".")[0]
    return json.loads(base64.b64decode(bagian + "=" * (-len(bagian) % 4)))


def admin_db() -> Admin:
    db = SessionLocal()
    try:
        return db.query(Admin).filter_by(email_admin=ADMIN).one()
    finally:
        db.close()


def coba_login(identifier, password="salah-sekali", headers=None):
    return TestClient(app).post("/Login", data={"identifier": identifier, "password": password},
                                headers=headers or {}, follow_redirects=False)


# --------------------------------------------------------------------------- #
# C-01 session version and slim cookie
# --------------------------------------------------------------------------- #
def test_c01_cookie_lama_ditolak_setelah_logout():
    c = masuk()
    salinan = c.cookies.get("scms_session")
    assert c.get("/Dashboard").status_code == 200
    assert c.post("/Logout", follow_redirects=False).status_code == 303

    pencuri = TestClient(app)
    pencuri.cookies.set("scms_session", salinan)
    r = pencuri.get("/Dashboard", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/Login")


def test_c01_logout_menaikkan_versi_sesi_dan_mengakhiri_sesi_di_perangkat_lain():
    versi_awal = admin_db().versi_sesi
    hp, laptop = masuk(), masuk()
    hp.post("/Logout")
    assert admin_db().versi_sesi == versi_awal + 1
    assert laptop.get("/Dashboard", follow_redirects=False).status_code == 303
    assert masuk().get("/Dashboard").status_code == 200  # a new login gets the new version


def test_c01_cookie_tidak_berisi_nama_atau_email():
    admin = admin_db()
    c = masuk()
    html = c.get("/Dashboard").text
    sesi = isi_cookie(c)
    assert set(sesi["pengguna"]) == {"id", "peran", "versi"}
    mentah = json.dumps(sesi)
    assert admin.nama_admin not in mentah and admin.email_admin not in mentah and "@" not in mentah
    assert admin.nama_admin in html  # the name still reaches the page, from the database


@pytest.mark.parametrize("akun, halaman", [(WARGA, "/Beranda"), (PENILIK, "/TugasLapangan"), (WARGA, "/lapor")])
def test_c01_nama_tetap_tampil_di_halaman_lain(akun, halaman):
    db = SessionLocal()
    try:
        nama = (db.query(Warga).filter_by(no_hp=akun).first() or
                db.query(PenilikJalan).filter_by(email_penilik=akun).first())
        nama = getattr(nama, "nama_warga", None) or nama.nama_penilik
    finally:
        db.close()
    c = masuk(akun)
    r = c.get(halaman)
    assert r.status_code == 200 and nama in r.text
    assert nama not in json.dumps(isi_cookie(c))


def test_c01_cookie_format_lama_tanpa_versi_ditolak():
    """A cookie signed before this change (name/email, no version) must log in again."""
    from itsdangerous import TimestampSigner
    signer = TimestampSigner(os.environ["SCMS_SECRET_KEY"])
    admin = admin_db()
    data = {"pengguna": {"id": admin.id_admin, "peran": "Admin", "nama": admin.nama_admin, "email": ADMIN}}
    cookie = signer.sign(base64.b64encode(json.dumps(data).encode())).decode()
    c = TestClient(app)
    c.cookies.set("scms_session", cookie)
    assert c.get("/Dashboard", follow_redirects=False).status_code == 303


# --------------------------------------------------------------------------- #
# C-02 API docs
# --------------------------------------------------------------------------- #
def test_c02_opsi_dokumentasi_mengikuti_mode_produksi(monkeypatch):
    monkeypatch.setenv("SCMS_PRODUKSI", "1")
    assert opsi_dokumentasi() == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    monkeypatch.setenv("SCMS_PRODUKSI", "0")
    assert opsi_dokumentasi()["docs_url"] == "/docs"


def test_c02_docs_aktif_di_mode_lokal():
    c = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 200, path


@pytest.mark.parametrize("produksi, harapan", [("1", 404), ("0", 200)])
def test_c02_docs_aplikasi_asli_mengikuti_scms_produksi(tmp_path, produksi, harapan):
    """The flag is read when the app is created, so start a fresh interpreter with it set."""
    kode = ("from fastapi.testclient import TestClient\nfrom app.main import app\nc = TestClient(app)\n"
            "print(','.join(str(c.get(p).status_code) for p in ('/docs', '/redoc', '/openapi.json')))")
    env = dict(os.environ, SCMS_PRODUKSI=produksi, DATABASE_URL=f"sqlite:///{(tmp_path / 'docs.db').as_posix()}",
               SCMS_SECRET_KEY="test-secret-key-for-pytest-only")
    hasil = subprocess.run([sys.executable, "-c", kode], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    assert hasil.returncode == 0, hasil.stderr[-2000:]
    assert hasil.stdout.strip().splitlines()[-1] == ",".join([str(harapan)] * 3)


# --------------------------------------------------------------------------- #
# C-03 login limit
# --------------------------------------------------------------------------- #
def test_c03_gagal_keenam_429_dan_login_benar_pun_ditolak():
    for _ in range(5):
        r = coba_login(ADMIN)
        assert r.status_code == 200 and "password salah" in r.text
    r = coba_login(ADMIN)
    assert r.status_code == 429
    assert "Terlalu banyak percobaan. Coba lagi dalam 15 menit." in r.text
    assert 'id="identifier"' in r.text  # still the friendly login page
    assert coba_login(ADMIN, SANDI).status_code == 429  # password is not even checked while locked
    assert coba_login(ADMIN.upper()).status_code == 429  # identifier is case-insensitive


def test_c03_login_sukses_mereset_hitungan():
    for _ in range(4):
        coba_login(ADMIN)
    assert coba_login(ADMIN, SANDI).status_code == 303
    for _ in range(5):
        assert coba_login(ADMIN).status_code == 200
    assert coba_login(ADMIN).status_code == 429


def test_c03_identifier_lain_tidak_ikut_terkunci():
    for _ in range(6):
        coba_login(ADMIN)
    assert coba_login(WARGA, SANDI).status_code == 303


def test_c03_angka_diatur_lewat_env(monkeypatch):
    monkeypatch.setenv("SCMS_LOGIN_MAKS_GAGAL", "2")
    monkeypatch.setenv("SCMS_LOGIN_JEDA_MENIT", "3")
    coba_login(ADMIN), coba_login(ADMIN)
    r = coba_login(ADMIN)
    assert r.status_code == 429 and "Coba lagi dalam 3 menit." in r.text


def test_c03_batas_per_ip(monkeypatch):
    monkeypatch.setenv("SCMS_LOGIN_MAKS_GAGAL_IP", "3")
    ip = {"CF-Connecting-IP": "203.0.113.7"}
    for i in range(3):
        assert coba_login(f"tidak-ada-{i}@contoh.id", headers=ip).status_code == 200
    assert coba_login("tidak-ada-9@contoh.id", headers=ip).status_code == 429
    assert coba_login(WARGA, SANDI, headers={"CF-Connecting-IP": "203.0.113.8"}).status_code == 303
    assert batas_login.MAKS_GAGAL_IP_BAWAAN == 20


def test_c03_ip_klien_cloudflare_lalu_forwarded_lalu_socket():
    from starlette.requests import Request

    def req(headers):
        return Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                        "client": ("10.0.0.5", 1234)})

    assert batas_login.ip_klien(req({"CF-Connecting-IP": "1.1.1.1", "X-Forwarded-For": "2.2.2.2"})) == "1.1.1.1"
    assert batas_login.ip_klien(req({"X-Forwarded-For": "2.2.2.2, 10.0.0.1"})) == "2.2.2.2"
    assert batas_login.ip_klien(req({})) == "10.0.0.5"


def test_c03_kunci_berakhir_setelah_jeda(monkeypatch):
    jam = [1000.0]
    monkeypatch.setattr(batas_login.time, "monotonic", lambda: jam[0])
    for _ in range(5):
        batas_login.catat_gagal("x@contoh.id", "1.2.3.4")
    assert batas_login.menit_terkunci("x@contoh.id", "9.9.9.9") == 15
    jam[0] += 14 * 60 + 1
    assert batas_login.menit_terkunci("x@contoh.id", "9.9.9.9") == 1
    jam[0] += 60
    assert batas_login.menit_terkunci("x@contoh.id", "9.9.9.9") is None


# --------------------------------------------------------------------------- #
# C-04 origin check and POST logout
# --------------------------------------------------------------------------- #
def test_c04_origin_asing_ditolak_403():
    c = masuk()
    r = c.post("/Logout", headers={"Origin": "https://evil.example"}, follow_redirects=False)
    assert r.status_code == 403
    assert c.get("/Dashboard").status_code == 200  # the session survived
    assert coba_login(ADMIN, SANDI, headers={"Origin": "http://evil.example"}).status_code == 403


@pytest.mark.parametrize("headers", [{"Referer": "https://evil.example/halaman"}, {"Origin": "null"},
                                     {"Origin": "http://testserver.evil.example"},
                                     {"Origin": "http://testserver:8080"}])
def test_c04_referer_atau_origin_aneh_ditolak(headers):
    assert coba_login(ADMIN, SANDI, headers=headers).status_code == 403


@pytest.mark.parametrize("headers", [
    {},  # non-browser client (no Origin, no Referer)
    {"Origin": "http://testserver"},
    {"Origin": "http://TestServer:80"},
    {"Referer": "http://testserver/Login?next=%2FDashboard"},
    # behind Cloudflare/Coolify: the browser's host arrives in X-Forwarded-Host/-Proto
    {"Origin": "https://scms.example.id", "X-Forwarded-Host": "scms.example.id", "X-Forwarded-Proto": "https"},
])
def test_c04_asal_sama_atau_tanpa_header_diizinkan(headers):
    assert coba_login(ADMIN, SANDI, headers=headers).status_code == 303


def test_c04_get_tidak_dicek():
    assert TestClient(app).get("/Login", headers={"Origin": "https://evil.example"}).status_code == 200


def test_c04_get_logout_tidak_menghapus_sesi():
    c = masuk()
    r = c.get("/Logout")
    assert r.status_code == 200
    assert 'id="konfirmasiKeluar"' in r.text and 'action="/Logout"' in r.text and 'method="post"' in r.text
    assert c.get("/logout").status_code == 200
    assert c.get("/Dashboard", follow_redirects=False).status_code == 200


def test_c04_post_logout_menghapus_sesi():
    c = masuk()
    r = c.post("/Logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/Login"
    assert c.get("/Dashboard", follow_redirects=False).status_code == 303
    assert TestClient(app).get("/Logout", follow_redirects=False).headers["location"] == "/Login"


def test_c04_template_tidak_lagi_memakai_tautan_logout():
    folder = ROOT / "app" / "views" / "templates"
    for p in folder.glob("*.html"):
        isi = p.read_text(encoding="utf-8")
        assert 'href="/Logout"' not in isi and "href='/Logout'" not in isi, p.name
    for halaman, akun in [("/Dashboard", ADMIN), ("/Beranda", WARGA), ("/lapor", WARGA), ("/work-orders", ADMIN),
                          ("/verifikasi", ADMIN), ("/TugasLapangan", PENILIK), ("/lacak", WARGA)]:
        html = masuk(akun).get(halaman).text
        assert '<form method="post" action="/Logout"' in html and 'id="tombolKeluar"' in html, halaman
        assert "min-h-[40px]" in html.split('id="tombolKeluar"')[1][:200], halaman


# --------------------------------------------------------------------------- #
# Security headers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("metode, path", [("get", "/Login"), ("get", "/static/css/tailwind.css"),
                                          ("get", "/tidak-ada"), ("post", "/Login")])
def test_header_keamanan_ada(metode, path):
    r = getattr(TestClient(app), metode)(path, follow_redirects=False)
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_header_keamanan_juga_pada_403_csrf():
    r = coba_login(ADMIN, SANDI, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.headers["x-frame-options"] == "DENY"


# --------------------------------------------------------------------------- #
# database/ganti_password.py
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sandi", ["", "pendek", "123456789", "password123", "PASSWORD123", " password123 "])
def test_ganti_password_menolak_password_lemah(sandi):
    with pytest.raises(ganti_password.PasswordDitolak):
        ganti_password.validasi_password(sandi)


def test_ganti_password_mengganti_hash_dan_menaikkan_versi_sesi():
    lama = masuk()
    versi_awal = admin_db().versi_sesi
    jawaban = iter(["password123", "pendek", "SandiBaru-2026!", "beda", "SandiBaru-2026!", "SandiBaru-2026!"])
    assert ganti_password.main(["--identifier", ADMIN], baca=lambda _: next(jawaban)) == 0
    assert admin_db().versi_sesi == versi_awal + 1
    assert lama.get("/Dashboard", follow_redirects=False).status_code == 303  # old session ended
    assert coba_login(ADMIN, SANDI).status_code == 200  # old password no longer works
    assert masuk(ADMIN, "SandiBaru-2026!").get("/Dashboard").status_code == 200


def test_ganti_password_identifier_tidak_ada():
    assert ganti_password.main(["--identifier", "tidak.ada@contoh.id"], baca=lambda _: "x") == 1


def test_ganti_password_semua_staf_boleh_melewati_akun():
    db = SessionLocal()
    try:
        jumlah_staf = db.query(Admin).count() + db.query(PenilikJalan).count()
    finally:
        db.close()
    # first staff account gets a new password, every other one is skipped with an empty answer
    jawaban = iter(["Staf-Baru-12345", "Staf-Baru-12345"] + [""] * jumlah_staf)
    assert ganti_password.main(["--semua-staf"], baca=lambda _: next(jawaban)) == 0
    db = SessionLocal()
    try:
        pertama = db.query(Admin).order_by(Admin.id_admin).first()
        assert ganti_password.pwd_context.verify("Staf-Baru-12345", pertama.password_hash)
        assert pertama.versi_sesi == 1
        assert all(a.versi_sesi == 0 for a in db.query(PenilikJalan).all())
    finally:
        db.close()


def test_ganti_password_tidak_menerima_password_lewat_argumen():
    with pytest.raises(SystemExit):
        ganti_password.main(["--identifier", ADMIN, "--password", "SandiBaru-2026!"], baca=lambda _: "")


# --------------------------------------------------------------------------- #
# Light migration of versi_sesi on an old database
# --------------------------------------------------------------------------- #
def test_migrasi_versi_sesi_pada_db_lama_tanpa_kehilangan_data(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'lama.db').as_posix()}")
    with eng.begin() as conn:  # account tables from before C-01
        conn.execute(text("CREATE TABLE warga (id_warga VARCHAR(20) PRIMARY KEY, nik VARCHAR(16), "
                          "nama_warga VARCHAR(50) NOT NULL, email VARCHAR(50), no_hp VARCHAR(15), "
                          "password_hash VARCHAR(255) NOT NULL, alamat_domisili VARCHAR(255), is_active BOOLEAN)"))
        conn.execute(text("CREATE TABLE admin (id_admin VARCHAR(20) PRIMARY KEY, nama_admin VARCHAR(50) NOT NULL, "
                          "email_admin VARCHAR(50) NOT NULL, password_hash VARCHAR(255) NOT NULL, "
                          "is_kepala_bidang BOOLEAN, is_active BOOLEAN)"))
        conn.execute(text("CREATE TABLE penilik_jalan (id_penilik VARCHAR(20) PRIMARY KEY, id_wilayah VARCHAR(20) NOT NULL, "
                          "nama_penilik VARCHAR(50) NOT NULL, nip VARCHAR(20), email_penilik VARCHAR(50), "
                          "password_hash VARCHAR(255) NOT NULL, status_ketersediaan VARCHAR(20), is_active BOOLEAN)"))
        conn.execute(text("INSERT INTO warga VALUES ('USR-01', '3578000000000001', 'Siti', 's@x.id', '0812', 'h1', 'Sby', 1)"))
        conn.execute(text("INSERT INTO admin VALUES ('ADM-01', 'Andi', 'a@dpupr.surabaya.go.id', 'h2', 0, 1)"))
        conn.execute(text("INSERT INTO penilik_jalan VALUES ('PNL-01', 'WIL-01', 'Budi', '1990', 'b@x.id', 'h3', 'Tersedia', 1)"))

    pastikan_kolom_terbaru(eng)
    pastikan_kolom_terbaru(eng)  # idempotent

    insp = inspect(eng)
    for tabel in ("warga", "admin", "penilik_jalan"):
        kolom = {c["name"]: c for c in insp.get_columns(tabel)}
        assert "versi_sesi" in kolom and kolom["versi_sesi"]["nullable"] is False, tabel
    with eng.begin() as conn:
        assert conn.execute(text("SELECT nama_warga, password_hash, versi_sesi FROM warga")).one() == ("Siti", "h1", 0)
        assert conn.execute(text("SELECT nama_admin, email_admin, versi_sesi FROM admin")).one() == \
            ("Andi", "a@dpupr.surabaya.go.id", 0)
        assert conn.execute(text("SELECT nama_penilik, nip, versi_sesi FROM penilik_jalan")).one() == ("Budi", "1990", 0)
        # a row inserted later without the column still gets 0
        conn.execute(text("INSERT INTO admin (id_admin, nama_admin, email_admin, password_hash) VALUES ('ADM-02', 'B', 'b', 'h')"))
        assert conn.execute(text("SELECT versi_sesi FROM admin WHERE id_admin = 'ADM-02'")).scalar() == 0
    eng.dispose()
