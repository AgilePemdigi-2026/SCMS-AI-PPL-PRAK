"""
Fast HTTP-level and unit tests (no browser needed):
access control, photo upload, deduplication, risk scoring, AI backends, seed guard.
"""
import io
import types

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.engine import make_url

import app.services.penyimpanan as modul_penyimpanan
from app.database import SessionLocal
from app.main import app
from app.models.entities import Laporan, WorkOrder
from app.services import risk_scoring
from app.services.ai_service import (
    AIService, KemiripanLeksikal, KemiripanSentenceTransformer, VisiYolo, validasi_foto,
)
from app.services.deduplikasi import jarak_meter, normalisasi_alamat
from database import seed as modul_seed
from database.seed import seed_data

ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"
WARGA = "0812xxxxxxx"


def gambar(format_="JPEG", ukuran=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", ukuran, (120, 120, 120)).save(buf, format=format_)
    return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    seed_data(verbose=False)
    monkeypatch.setattr(modul_penyimpanan, "DIREKTORI_UNGGAHAN", tmp_path)
    with TestClient(app) as c:
        yield c


def masuk(c: TestClient, identifier: str, password: str = "password123"):
    r = c.post("/Login", data={"identifier": identifier, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text[:200]
    return r


def wo(tid):
    db = SessionLocal()
    try:
        return db.query(WorkOrder).filter_by(id_work_order=tid).first()
    finally:
        db.close()


def lapor(c, nama="foto_jalan.jpg", data=None, **form):
    isian = {
        "lokasi_jalan": "Jl. Dharmawangsa No. 10, Surabaya",
        "latitude": "-7.27200", "longitude": "112.75800",
        "deskripsi": "Aspal mengelupas dan berlubang di depan toko roti",
        "kategori_pilihan": "Jalan Berlubang", "id_wilayah": "WIL-01",
    }
    isian.update(form)
    berkas = {"foto": (nama, data if data is not None else gambar(), "image/jpeg")}
    return c.post("/lapor", data=isian, files=berkas)


def tiket_terbaru():
    db = SessionLocal()
    try:
        return db.query(WorkOrder).order_by(WorkOrder.id_work_order.desc()).first()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Access control
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", ["/Dashboard", "/verifikasi", "/work-orders", "/lapor", "/Beranda"])
def test_halaman_terlindungi_mengarahkan_ke_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/Login?next=")


def test_aksi_anonim_ditolak_dan_tidak_mengubah_data(client):
    sebelum = wo("REP-2026-00355").status_work_order
    r = client.post("/verifikasi/REP-2026-00355/approve", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/Login")
    assert wo("REP-2026-00355").status_work_order == sebelum


@pytest.mark.parametrize("akun,path,metode,kode", [
    (WARGA, "/Dashboard", "get", 403),
    (WARGA, "/verifikasi", "get", 403),
    (WARGA, "/verifikasi/REP-2026-00355/approve", "post", 403),
    (KABID, "/verifikasi", "get", 200),
    (KABID, "/verifikasi/REP-2026-00355/approve", "post", 403),
    (PENILIK, "/work-orders", "get", 200),
    (PENILIK, "/verifikasi", "get", 403),
    (PENILIK, "/work-orders/REP-2026-00341/assign", "post", 403),
    (ADMIN, "/lapor", "get", 403),
])
def test_hak_akses_per_peran(client, akun, path, metode, kode):
    masuk(client, akun)
    r = getattr(client, metode)(path, follow_redirects=False)
    assert r.status_code == kode


def test_admin_menyetujui_mencatat_admin(client):
    masuk(client, ADMIN)
    r = client.post("/verifikasi/REP-2026-00355/approve", follow_redirects=False)
    assert r.status_code == 303
    t = wo("REP-2026-00355")
    assert t.status_work_order == "Disetujui"
    assert t.id_admin == "ADM-01"


@pytest.mark.parametrize("path", [
    "/verifikasi/TIDAK-ADA/approve", "/verifikasi/TIDAK-ADA/inspect",
    "/verifikasi/TIDAK-ADA/skip-inspection", "/work-orders/TIDAK-ADA/assign",
    "/Dashboard/TIDAK-ADA/quick-approve",
])
def test_tiket_tidak_ada_404(client, path):
    masuk(client, ADMIN)
    assert client.post(path, follow_redirects=False).status_code == 404


def test_logout_menghapus_sesi(client):
    masuk(client, ADMIN)
    assert client.get("/Dashboard").status_code == 200
    client.get("/Logout")
    assert client.get("/Dashboard", follow_redirects=False).status_code == 303


def test_next_hanya_path_internal(client):
    r = client.post("/Login", data={"identifier": ADMIN, "password": "password123", "next": "//evil.example"},
                    follow_redirects=False)
    assert r.headers["location"] == "/Dashboard"
    client.get("/Logout")
    r = client.post("/Login", data={"identifier": ADMIN, "password": "password123", "next": "/verifikasi?ticket_id=REP-2026-00355"},
                    follow_redirects=False)
    assert r.headers["location"] == "/verifikasi?ticket_id=REP-2026-00355"


# --------------------------------------------------------------------------- #
# Registration / login hardening
# --------------------------------------------------------------------------- #
def test_warga_tidak_bisa_mendaftar_dengan_email_admin(client):
    r = client.post("/Register", data=dict(
        nik="3578000000000001", nama_lengkap="Bukan Admin", no_hp="081200000001",
        email="Admin@DPUPR.surabaya.go.id", alamat_domisili="x", password="rahasia1", konfirmasi_password="rahasia1"))
    assert "Email instansi tidak dapat digunakan" in r.text
    r = client.post("/Login", data={"identifier": ADMIN, "password": "password123"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/Dashboard"


def test_registrasi_menyimpan_alamat(client):
    r = client.post("/Register", data=dict(
        nik="3578000000000002", nama_lengkap="Warga Baru", no_hp="081200000002",
        email="warga.baru@gmail.com", alamat_domisili="Jl. Airlangga No. 4", password="rahasia1",
        konfirmasi_password="rahasia1"))
    assert "Registrasi berhasil" in r.text
    from app.models.entities import Warga
    db = SessionLocal()
    try:
        assert db.query(Warga).filter_by(nik="3578000000000002").first().alamat_domisili == "Jl. Airlangga No. 4"
    finally:
        db.close()


def test_akun_nonaktif_tidak_terungkap_tanpa_password_benar(client):
    r = client.post("/Login", data={"identifier": "0899xxxxxxx", "password": "salah"})
    assert "tidak aktif" not in r.text
    assert "password salah" in r.text


# --------------------------------------------------------------------------- #
# Photo upload & AI
# --------------------------------------------------------------------------- #
def test_unggah_foto_asli_berhasil_dan_tersimpan(client, tmp_path):
    masuk(client, WARGA)
    r = lapor(client, nama="IMG_0001.jpg")
    assert "Laporan berhasil dikirim" in r.text
    lap = SessionLocal().query(Laporan).order_by(Laporan.id_laporan.desc()).first()
    nama_simpan = lap.url_foto.rsplit("/", 1)[-1]
    assert (tmp_path / nama_simpan).exists()
    assert lap.id_warga == "USR-01"  # the logged-in citizen, not a hardcoded id


def test_berkas_palsu_berekstensi_jpg_ditolak(client):
    masuk(client, WARGA)
    r = lapor(client, nama="laporan.jpg", data=b"%PDF-1.4 bukan gambar")
    assert "Format harus JPG/PNG dan ukuran maksimal 10MB" in r.text


def test_berkas_lebih_10mb_ditolak(client):
    masuk(client, WARGA)
    r = lapor(client, nama="besar.jpg", data=gambar() + b"\0" * (10 * 1024 * 1024 + 10))
    assert "Format harus JPG/PNG dan ukuran maksimal 10MB" in r.text


def test_tanpa_foto_ditolak(client):
    masuk(client, WARGA)
    r = client.post("/lapor", data={"lokasi_jalan": "Jl. X No. 1", "deskripsi": "Lubang besar sekali di sini"})
    assert "Validasi Gagal pada Step 1" in r.text


def test_api_analisis_foto_jujur_tentang_mode(client):
    masuk(client, WARGA)
    r = client.post("/api/analisis-foto", files={"foto": ("retak_aspal.jpg", gambar(), "image/jpeg")})
    h = r.json()
    assert h["valid"] and h["detected"]
    assert h["kategori"] == "Retak Permukaan"
    assert h["mode"] == "simulasi"
    assert h["confidence"] is None  # no fake 98.4% any more


def test_validasi_foto_memeriksa_isi_berkas():
    assert validasi_foto("a.png", 0, gambar("PNG")).valid
    assert not validasi_foto("a.png", 0, b"not an image").valid
    assert not validasi_foto("a.gif", 0, gambar("GIF")).valid


class _FakeBoxes:
    def __init__(self, rows):
        self.cls = types.SimpleNamespace(tolist=lambda: [r[0] for r in rows])
        self.conf = types.SimpleNamespace(tolist=lambda: [r[1] for r in rows])
        self.xywhn = types.SimpleNamespace(tolist=lambda: [r[2] for r in rows])


class _FakeYolo:
    def __init__(self, rows, names):
        self.rows, self.names = rows, names

    def predict(self, img, conf, verbose):
        return [types.SimpleNamespace(boxes=_FakeBoxes(self.rows), names=self.names)]


def test_backend_yolo_memetakan_kelas_dan_severity():
    names = {0: "D00", 1: "D40", 2: "person"}
    visi = VisiYolo(model=_FakeYolo([(1, 0.9, [0.5, 0.5, 0.4, 0.3]), (2, 0.95, [0.5, 0.5, 0.2, 0.6])], names))
    h = visi.analisis("x.jpg", gambar())
    assert h.detected and h.rekomendasi_kategori == "Jalan Berlubang"
    assert h.confidence == 90.0 and 7.0 < h.severity_score <= 10.0
    kosong = VisiYolo(model=_FakeYolo([(2, 0.99, [0.5, 0.5, 0.5, 0.5])], names)).analisis("x.jpg", gambar())
    assert not kosong.detected


class _FakeYoloV4:
    """Accepts the extra predict() options and records them."""

    def __init__(self, rows, names):
        self.rows, self.names, self.panggilan = rows, names, []

    def predict(self, img, **kwargs):
        self.panggilan.append((img, kwargs))
        return [types.SimpleNamespace(boxes=_FakeBoxes(self.rows), names=self.names)]


KONFIG_V4 = {
    "versi": "v4",
    "conf_per_class": {"Jalan Berlubang": 0.26, "Retak Permukaan": 0.20},
    "infer_imgsz": 800,
    "nms_iou": 0.6,
    "agnostic_nms": False,
}
NAMA_V4 = {0: "Jalan Berlubang", 1: "Retak Permukaan"}


def test_backend_yolo_v4_memakai_ambang_per_kelas_dan_opsi_config():
    # Retak 0.22 lolos (ambang 0.20), lubang 0.24 tidak (ambang 0.26)
    model = _FakeYoloV4([(0, 0.24, [0.5, 0.5, 0.3, 0.3]), (1, 0.22, [0.5, 0.5, 0.4, 0.1])], NAMA_V4)
    visi = VisiYolo(model=model, config=KONFIG_V4)
    h = visi.analisis("x.jpg", gambar())
    assert h.detected and h.rekomendasi_kategori == "Retak Permukaan" and h.confidence == 22.0
    _, opsi = model.panggilan[0]
    assert opsi["conf"] == 0.20 and opsi["imgsz"] == 800 and opsi["iou"] == 0.6 and opsi["agnostic_nms"] is False

    # Semua deteksi di bawah ambang kelasnya -> tidak terdeteksi
    lemah = _FakeYoloV4([(0, 0.25, [0.5, 0.5, 0.3, 0.3]), (1, 0.19, [0.5, 0.5, 0.4, 0.1])], NAMA_V4)
    assert not VisiYolo(model=lemah, config=KONFIG_V4).analisis("x.jpg", gambar()).detected


def test_backend_yolo_membaca_model_config_json(tmp_path):
    import json

    path = tmp_path / "model_config.json"
    path.write_text(json.dumps(KONFIG_V4), encoding="utf-8")
    visi = VisiYolo(model=_FakeYoloV4([], NAMA_V4), config_path=str(path))
    assert visi.versi == "v4"
    assert visi.ambang("Jalan Berlubang") == 0.26 and visi.ambang("Retak Permukaan") == 0.20
    # Tanpa file config: ambang tunggal bawaan
    tanpa = VisiYolo(model=_FakeYoloV4([], NAMA_V4), config_path=str(tmp_path / "tidak_ada.json"))
    assert tanpa.ambang("Jalan Berlubang") == 0.35 and tanpa.opsi_prediksi == {}


def test_backend_yolo_memutar_foto_sesuai_exif():
    # Foto 64x48 dengan tag EXIF orientation=6 (diputar 90 derajat) harus sampai ke model sebagai 48x64
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (64, 48), (120, 120, 120)).save(buf, format="JPEG", exif=exif)
    model = _FakeYoloV4([], NAMA_V4)
    VisiYolo(model=model, config=KONFIG_V4).analisis("x.jpg", buf.getvalue())
    img, _ = model.panggilan[0]
    assert img.size == (48, 64)


def test_backend_yolo_mengembalikan_kotak_yang_lolos_ambang_terurut():
    model = _FakeYoloV4([
        (1, 0.45, [0.25, 0.75, 0.30, 0.10]),  # retak, lolos (>= 0.20)
        (0, 0.24, [0.50, 0.50, 0.20, 0.20]),  # lubang di bawah ambang 0.26 -> dibuang
        (0, 0.892, [0.50, 0.40, 0.40, 0.20]),  # lubang, lolos
        (1, 0.19, [0.10, 0.10, 0.10, 0.10]),  # retak di bawah ambang 0.20 -> dibuang
    ], NAMA_V4)
    h = VisiYolo(model=model, config=KONFIG_V4).analisis("x.jpg", gambar())
    assert [k["kategori"] for k in h.kotak] == ["Jalan Berlubang", "Retak Permukaan"]
    lubang, retak = h.kotak
    assert lubang == {"kategori": "Jalan Berlubang", "confidence": 89.2, "x1": 0.3, "y1": 0.3, "x2": 0.7, "y2": 0.5}
    assert retak["confidence"] == 45.0 and (retak["x1"], retak["y1"], retak["x2"], retak["y2"]) == (0.1, 0.7, 0.4, 0.8)
    # koordinat tidak keluar dari gambar
    pinggir = _FakeYoloV4([(0, 0.9, [0.05, 0.98, 0.2, 0.1])], NAMA_V4)
    k = VisiYolo(model=pinggir, config=KONFIG_V4).analisis("x.jpg", gambar()).kotak[0]
    assert k["x1"] == 0.0 and k["y2"] == 1.0


def test_backend_yolo_kotak_maksimal_20():
    rows = [(0, 0.30 + i * 0.01, [0.5, 0.5, 0.1, 0.1]) for i in range(30)]
    h = VisiYolo(model=_FakeYoloV4(rows, NAMA_V4), config=KONFIG_V4).analisis("x.jpg", gambar())
    assert len(h.kotak) == 20
    assert h.kotak[0]["confidence"] == 59.0 and h.kotak[-1]["confidence"] == 40.0


def test_backend_simulasi_tanpa_kotak():
    assert AIService().analisis_foto("jalan_berlubang.jpg", gambar()).kotak == []


def test_api_analisis_foto_mengembalikan_kotak(client, monkeypatch):
    import app.main as modul_main

    model = _FakeYoloV4([(0, 0.9, [0.5, 0.5, 0.4, 0.2])], NAMA_V4)
    ai = AIService(visi=VisiYolo(model=model, config=KONFIG_V4))
    monkeypatch.setattr(modul_main, "get_ai_service", lambda: ai)
    masuk(client, WARGA)
    h = client.post("/api/analisis-foto", files={"foto": ("jalan.jpg", gambar(), "image/jpeg")}).json()
    assert h["mode"] == "yolov8" and h["confidence"] == 90.0
    assert h["kotak"] == [{"kategori": "Jalan Berlubang", "confidence": 90.0, "x1": 0.3, "y1": 0.4, "x2": 0.7, "y2": 0.6}]

    monkeypatch.undo()
    masuk(client, WARGA)
    sim = client.post("/api/analisis-foto", files={"foto": ("jalan.jpg", gambar(), "image/jpeg")}).json()
    assert sim["mode"] == "simulasi" and sim["kotak"] == []


def test_severity_laporan_aturan_ganti_kategori():
    from app.controllers.kontrol_pelaporan import severity_laporan

    assert severity_laporan("Jalan Berlubang", "Jalan Berlubang", 9.2) == 9.2
    assert severity_laporan("Retak Permukaan", "Jalan Berlubang", 9.2) == 4.5
    assert severity_laporan("Jalan Amblas", "Retak Permukaan", 5.4) == 7.5
    assert severity_laporan("Jalan Berlubang", "Retak Permukaan", 5.4) == 7.0


def test_lapor_kategori_sama_dengan_ai_memakai_severity_ai(client):
    masuk(client, WARGA)
    # mode simulasi: nama berkas "jalan_berlubang" -> Jalan Berlubang, severity AI 8.5
    lapor(client, nama="jalan_berlubang.jpg", kategori_pilihan="Jalan Berlubang",
          lokasi_jalan="Jl. Kertajaya No. 77, Surabaya", latitude="-7.27900", longitude="112.76900",
          deskripsi="Lubang lebar di lajur kiri dekat halte bus")
    t = tiket_terbaru()
    assert t.kategori_kerusakan == "Jalan Berlubang" and t.severity_score_kasus == 8.5


def test_lapor_kategori_diganti_warga_memakai_severity_dasar(client):
    masuk(client, WARGA)
    # AI merekomendasikan Jalan Berlubang (8.5), warga memilih Retak Permukaan -> nilai dasar 4.5
    lapor(client, nama="jalan_berlubang.jpg", kategori_pilihan="Retak Permukaan",
          lokasi_jalan="Jl. Manyar Kertoarjo No. 12, Surabaya", latitude="-7.28100", longitude="112.77300",
          deskripsi="Retakan memanjang di aspal sepanjang dua meter")
    t = tiket_terbaru()
    assert t.kategori_kerusakan == "Retak Permukaan" and t.severity_score_kasus == 4.5
    db = SessionLocal()
    try:
        assert db.query(Laporan).filter_by(id_work_order=t.id_work_order).one().severity_score == 4.5
    finally:
        db.close()


def test_backend_sentence_transformer_memakai_encoder():
    enc = types.SimpleNamespace(encode=lambda teks: [[1.0, 0.0], [1.0, 0.0]] if "lubang" in teks[1] else [[1.0, 0.0], [0.0, 1.0]])
    st = KemiripanSentenceTransformer(encoder=enc)
    assert st.kemiripan("jalan berlubang", "ada lubang") == pytest.approx(1.0)
    assert st.kemiripan("jalan berlubang", "retak") == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Deduplication (BR-3)
# --------------------------------------------------------------------------- #
def daftar_dan_masuk(c, nomor="081200000009"):
    c.get("/Logout")
    r = c.post("/Register", data=dict(nik="35780000000000" + nomor[-2:], nama_lengkap="Warga Kedua", no_hp=nomor,
                                      email="", alamat_domisili="", password="rahasia1", konfirmasi_password="rahasia1"))
    assert "Registrasi berhasil" in r.text
    masuk(c, nomor, "rahasia1")


def test_laporan_serupa_di_titik_sama_digabung(client):
    masuk(client, WARGA)
    lapor(client)
    pertama = tiket_terbaru()
    daftar_dan_masuk(client)
    r = lapor(client, deskripsi="Jalan berlubang, aspal mengelupas dekat toko roti")
    assert "digabungkan" in r.text
    gabung = wo(pertama.id_work_order)
    assert gabung.exposure_count == 2
    assert gabung.risk_score > pertama.risk_score


def test_warga_yang_sama_tidak_menaikkan_exposure(client):
    masuk(client, WARGA)
    lapor(client)
    pertama = tiket_terbaru()
    for _ in range(5):
        r = lapor(client, deskripsi="Jalan berlubang, aspal mengelupas dekat toko roti")
        assert "digabungkan" in r.text
    t = wo(pertama.id_work_order)
    assert (t.exposure_count, t.risk_score) == (1, pertama.risk_score)


def test_kirim_laporan_redirect_agar_refresh_tidak_mengirim_ulang(client):
    masuk(client, WARGA)
    r = client.post("/lapor", data={
        "lokasi_jalan": "Jl. Manyar No. 3", "deskripsi": "Lubang besar di jalur lambat",
        "kategori_pilihan": "Jalan Berlubang", "id_wilayah": "WIL-01"},
        files={"foto": ("a.jpg", gambar(), "image/jpeg")}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/lapor"
    assert "Laporan berhasil dikirim" in client.get("/lapor").text
    assert "Laporan berhasil dikirim" not in client.get("/lapor").text  # shown once


def test_form_lapor_tanpa_koordinat_bawaan(client):
    masuk(client, WARGA)
    html = client.get("/lapor").text
    assert 'name="latitude" value=""' in html and 'name="longitude" value=""' in html


def test_png_berekstensi_jpg_disimpan_sebagai_png(client, tmp_path):
    masuk(client, WARGA)
    lapor(client, nama="foto.jpg", data=gambar("PNG"))
    lap = SessionLocal().query(Laporan).order_by(Laporan.id_laporan.desc()).first()
    assert lap.url_foto.endswith(".png")


def test_jalan_sama_titik_berbeda_tidak_digabung(client):
    masuk(client, WARGA)
    lapor(client)
    # ~400 m further along the same street
    r = lapor(client, lokasi_jalan="Jl. Dharmawangsa No. 210, Surabaya", latitude="-7.27560",
              deskripsi="Aspal mengelupas dan berlubang di depan toko roti")
    assert "berhasil dikirim" in r.text


def test_titik_sama_deskripsi_berbeda_tidak_digabung(client):
    masuk(client, WARGA)
    lapor(client)
    r = lapor(client, deskripsi="Gorong-gorong ambrol membuat genangan setinggi mata kaki")
    assert "berhasil dikirim" in r.text


def test_tidak_digabung_ke_tiket_selesai(client):
    masuk(client, WARGA)
    r = lapor(client, nama="retak.jpg", kategori_pilihan="Retak Permukaan", lokasi_jalan="Jl. Dharmahusada No. 8",
              latitude="-7.26610", longitude="112.77900", deskripsi="Retakan memanjang di aspal depan sekolah")
    assert "berhasil dikirim" in r.text  # REP-2026-00290 is Selesai


def test_laporan_sudirman_tidak_menimpa_tiket_341(client):
    sebelum = wo("REP-2026-00341")
    masuk(client, WARGA)
    lapor(client, lokasi_jalan="Jl. Panglima Sudirman No. 2, Surabaya", latitude="-7.26300", longitude="112.74400",
          deskripsi="Retak di tengah lajur kanan dekat halte", kategori_pilihan="Retak Permukaan", nama="retak.jpg")
    sesudah = wo("REP-2026-00341")
    assert (sesudah.status_work_order, sesudah.lokasi_jalan) == (sebelum.status_work_order, sebelum.lokasi_jalan)


def test_normalisasi_alamat_dan_jarak():
    assert normalisasi_alamat("Jl. Sudirman No. 45, Surabaya") == normalisasi_alamat("Jalan Sudirman 45")
    assert normalisasi_alamat("Jl. Sudirman No. 45") != normalisasi_alamat("Jl. Sudirman No. 46")
    assert jarak_meter(-7.2655, 112.747, -7.2655, 112.747) == 0
    assert 100 < jarak_meter(-7.2655, 112.747, -7.2665, 112.747) < 120


def test_kemiripan_leksikal_mengabaikan_kata_umum():
    k = KemiripanLeksikal()
    assert k.kemiripan("ada jalan di depan", "jalan di dekat sini") == 0.0
    assert k.kemiripan("Jalan berlubang dekat lampu merah Sudirman",
                       "Ada jalan berlubang cukup dalam di depan gedung Sudirman") >= k.ambang_duplikat


# --------------------------------------------------------------------------- #
# Risk scoring (BR-2) and dashboard
# --------------------------------------------------------------------------- #
def test_risk_score_dihitung_dengan_formula(client):
    masuk(client, WARGA)
    lapor(client)
    t = tiket_terbaru()
    harapan = risk_scoring.nilai_risiko(t.severity_score_kasus, 1, t.vulnerability_score, t.kelas_jalan)
    assert (t.risk_score, t.prioritas, t.sla_rekomendasi) == (harapan.risk_score, harapan.prioritas, harapan.sla_rekomendasi)
    assert t.risk_score != t.severity_score_kasus  # no longer just a copy of severity


@pytest.mark.parametrize("skor,prioritas,sla", [
    (8.0, "Urgent", "24 jam"), (7.9, "Tinggi", "3x24 jam"), (6.0, "Tinggi", "3x24 jam"),
    (5.9, "Borderline", "5x24 jam"), (4.0, "Borderline", "5x24 jam"), (3.9, "Rendah", "7x24 jam"),
])
def test_ambang_prioritas(skor, prioritas, sla):
    assert risk_scoring.klasifikasi_prioritas(skor) == (prioritas, sla)


def test_skor_risiko_terbatas_0_sampai_10():
    assert risk_scoring.hitung_risk_score(10, 1000, 10, 10) == 10.0
    assert risk_scoring.hitung_risk_score(0, 1, 0, 0) >= 0.0


def test_seed_sesuai_skenario_bdd():
    seed_data(verbose=False)
    assert (wo("REP-2026-00341").risk_score, wo("REP-2026-00341").prioritas) == (8.4, "Urgent")
    assert (wo("REP-2026-00355").risk_score, wo("REP-2026-00355").prioritas) == (5.1, "Borderline")
    assert wo("REP-2026-00298").status_work_order != "Selesai"


def test_peta_dashboard_memakai_koordinat_tiket(client):
    masuk(client, WARGA)
    lapor(client, lokasi_jalan='Jl. "Kutip" \\ Miring No. 1', latitude="-7.23000", longitude="112.61000")
    client.get("/Logout")
    masuk(client, ADMIN)
    html = client.get("/Dashboard").text
    assert '"lat": -7.23' in html and '"lng": 112.61' in html
    assert "245 <span" not in html and "94.2%" not in html  # no hardcoded KPI numbers


def test_seed_menolak_reset_database_non_sqlite(monkeypatch):
    palsu = types.SimpleNamespace(url=make_url("postgresql+psycopg2://u:p@localhost/scms"))
    monkeypatch.setattr(modul_seed, "engine", palsu)
    monkeypatch.delenv("SCMS_ALLOW_DB_RESET", raising=False)
    with pytest.raises(RuntimeError, match="Refusing to drop"):
        modul_seed.seed_data()


# --------------------------------------------------------------------------- #
# Regression tests for the independent review
# --------------------------------------------------------------------------- #
def test_inspeksi_nama_penilik_palsu_tidak_dilaporkan_berhasil(client):
    masuk(client, ADMIN)
    r = client.post("/verifikasi/REP-2026-00355/inspect", data={"nama_penilik": "Orang Palsu"})
    assert "tidak ditemukan di wilayah" in r.text
    assert wo("REP-2026-00355").status_work_order == "Dilaporkan"


def test_next_mempertahankan_seluruh_query(client):
    r = client.get("/Dashboard?status=Dilaporkan&kategori=Jalan%20Amblas", follow_redirects=False)
    login_page = client.get(r.headers["location"]).text
    import re as _re
    nilai_next = _re.search(r'name="next" value="([^"]*)"', login_page).group(1).replace("&amp;", "&")
    r = client.post("/Login", data={"identifier": ADMIN, "password": "password123", "next": nilai_next},
                    follow_redirects=False)
    assert r.headers["location"] == "/Dashboard?status=Dilaporkan&kategori=Jalan%20Amblas"


def test_aksi_post_anonim_tidak_kembali_ke_url_post(client):
    r = client.post("/verifikasi/REP-2026-00355/approve", follow_redirects=False)
    assert r.headers["location"] == "/Login"


def test_akun_dinonaktifkan_kehilangan_sesi(client):
    masuk(client, ADMIN)
    assert client.get("/Dashboard").status_code == 200
    from app.models.entities import Admin
    db = SessionLocal()
    db.get(Admin, "ADM-01").is_active = False
    db.commit(); db.close()
    assert client.get("/Dashboard", follow_redirects=False).status_code == 303


def test_login_email_staf_tidak_peka_huruf_besar(client):
    r = client.post("/Login", data={"identifier": "ADMIN@DPUPR.Surabaya.go.id", "password": "password123"},
                    follow_redirects=False)
    assert r.headers["location"] == "/Dashboard"


def test_verifikasi_tanpa_tiket_tidak_error(client):
    db = SessionLocal()
    db.query(Laporan).delete(); db.query(WorkOrder).delete(); db.commit(); db.close()
    masuk(client, ADMIN)
    r = client.get("/verifikasi")
    assert r.status_code == 200 and "Belum ada tiket" in r.text


def test_secret_contoh_tidak_dipakai():
    from app.main import pilih_secret
    assert pilih_secret("ganti_dengan_string_acak_panjang") != "ganti_dengan_string_acak_panjang"
    assert pilih_secret("") and pilih_secret("pendek") != "pendek"
    assert pilih_secret("x" * 40) == "x" * 40


def test_database_lama_mendapat_kolom_baru(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from app.database import pastikan_kolom_terbaru
    eng = create_engine(f"sqlite:///{tmp_path / 'lama.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE work_order (id_work_order VARCHAR(20) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE laporan (id_laporan VARCHAR(20) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE warga (id_warga VARCHAR(20) PRIMARY KEY)"))
    pastikan_kolom_terbaru(eng)
    pastikan_kolom_terbaru(eng)  # idempotent
    kolom = {t: {c["name"] for c in inspect(eng).get_columns(t)} for t in ("work_order", "laporan", "warga")}
    assert {"latitude", "longitude"} <= kolom["work_order"] and {"latitude", "longitude"} <= kolom["laporan"]
    assert "alamat_domisili" in kolom["warga"]
