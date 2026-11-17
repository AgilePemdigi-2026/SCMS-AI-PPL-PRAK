"""Sprint 3 / PRD 5.3 BR-1: the AI never rejects a report. A valid photo on which it recognises
no damage (or that looks like a non-road object) is accepted as "Perlu tinjauan manual" and treated
like an ambiguous score at verification."""
import io

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from app.controllers.kontrol_pelaporan import KontrolPelaporan
from app.database import SessionLocal
from app.main import app
from app.models.entities import Notifikasi, Warga, WorkOrder
from database.seed import seed_data

scenarios("../features/uc_a_tinjauan_manual.feature")

WARGA = "0812xxxxxxx"
ADMIN = "admin@dpupr.surabaya.go.id"
LABEL = "Perlu tinjauan manual"
PESAN_LAMA = "Objek jalan rusak tidak terdeteksi, silakan ambil ulang foto"


def _jpeg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 120, 120)).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture
def ctx(browser, live_server, login_as, tmp_path):
    seed_data(verbose=False)
    db = SessionLocal()
    yield {"browser": browser, "base": live_server, "login_as": login_as, "tmp": tmp_path,
           "existing_ids": {w.id_work_order for w in db.query(WorkOrder).all()},
           "lokasi": "Jl. Kenjeran No. 100, Surabaya", "kategori": "Jalan Berlubang",
           "deskripsi": "Aspal mengelupas dan berlubang di depan pasar", "result": None}
    db.close()


def _db(fungsi):
    db = SessionLocal()
    try:
        return fungsi(db)
    finally:
        db.close()


def _buka_lapor(ctx):
    ctx["login_as"](WARGA)
    ctx["browser"].get(f"{ctx['base']}/lapor")
    assert ctx["browser"].find_element(By.ID, "fileInputAsli")


def _unggah(ctx, path, nama):
    ctx["nama_foto"] = nama
    b = ctx["browser"]
    b.find_element(By.ID, "fileInputAsli").send_keys(str(path))
    # the photo is analysed by /api/analisis-foto asynchronously; wait for the final verdict
    WebDriverWait(b, 10).until(lambda d: d.find_element(By.ID, "infoStatusCV").text.strip()
                               not in ("Menunggu unggahan", "Menganalisis foto..."))
    ctx["alert"] = b.find_element(By.ID, "alert-step-1").text.strip()
    ctx["status_cv"] = b.find_element(By.ID, "infoStatusCV").text.strip()


def _unggah_jpeg(ctx, nama):
    path = ctx["tmp"] / nama
    path.write_bytes(_jpeg())
    _unggah(ctx, path, nama)


def _kirim(ctx, nama=None, data=None, latitude=-7.2471, longitude=112.7972):
    """The final submit goes through the same controller as POST /lapor (like the UC-A steps)."""
    nama = nama or ctx["nama_foto"]
    ctx["result"] = _db(lambda db: KontrolPelaporan(db).kirim_laporan(
        filename=nama, file_size_mb=0.1, lokasi_jalan=ctx["lokasi"], deskripsi=ctx["deskripsi"],
        kategori_pilihan=ctx["kategori"], latitude=latitude, longitude=longitude,
        foto_bytes=data if data is not None else _jpeg()))


def _panel_terlihat(ctx, no):
    return ctx["browser"].find_element(By.ID, f"panel-step-{no}").is_displayed()


# ------------------------------------------------------------------ Given
@given('I am logged in and on the "Buat Laporan" page')
@given('I am on the "Buat Laporan" page')
def halaman_lapor(ctx):
    _buka_lapor(ctx)


@given(parsers.parse('a ticket labelled "{label}" with status "{status}" reported by citizen "{no_hp}"'))
def tiket_tinjauan_manual(ctx, label, status, no_hp):
    id_warga = _db(lambda db: db.query(Warga).filter_by(no_hp=no_hp).one().id_warga)
    ctx["result"] = _db(lambda db: KontrolPelaporan(db).kirim_laporan(
        filename="tanpa_deteksi_jl_kenjeran.jpg", file_size_mb=0.1, lokasi_jalan="Jl. Kenjeran No. 100, Surabaya",
        deskripsi="Aspal mengelupas dan berlubang di depan pasar", kategori_pilihan="Jalan Berlubang",
        latitude=-7.2471, longitude=112.7972, id_warga=id_warga, foto_bytes=_jpeg()))
    hasil = ctx["result"]
    assert hasil["success"] and hasil["perlu_tinjauan_manual"] and hasil["status_work_order"] == status
    # base severity of Jalan Berlubang gives a CLEAR score (6.5 Tinggi): manual review still wins
    assert (hasil["risk_score"], hasil["prioritas"]) == (6.5, "Tinggi")
    ctx["id_wo"] = hasil["ticket_id"]
    assert label == LABEL


# ------------------------------------------------------------------- When
@when(parsers.parse('I upload a valid road photo "{nama}" in which the AI detects nothing'))
@when(parsers.parse('I upload a valid photo that does not show road damage, such as "{nama}"'))
def unggah_foto_valid(ctx, nama):
    _unggah_jpeg(ctx, nama)


@when(parsers.parse('I upload a file named "{nama}" that is not a real JPEG or PNG image'))
def unggah_bukan_gambar(ctx, nama):
    path = ctx["tmp"] / nama
    path.write_bytes(b"%PDF-1.4 bukan gambar")
    _unggah(ctx, path, nama)
    _kirim(ctx, nama, data=path.read_bytes())  # the backend checks the same rule (BR-1)


@when(parsers.parse('I select the location "{lokasi}" via GPS'))
def pilih_lokasi(ctx, lokasi):
    ctx["lokasi"] = lokasi


@when(parsers.parse('I choose the category "{kategori}" myself'))
def pilih_kategori(ctx, pilih_opsi, kategori):
    ctx["kategori"] = kategori
    ctx["browser"].execute_script("bukaStep(3);")
    pilih_opsi("kategori_pilihan", kategori)
    assert ctx["browser"].find_element(By.ID, "catatanTinjauanManual").is_displayed()
    assert ctx["browser"].find_element(By.ID, "teksRekomendasiAI").text.strip() == LABEL


@when(parsers.parse('I enter the description "{deskripsi}"'))
def isi_deskripsi(ctx, deskripsi):
    ctx["deskripsi"] = deskripsi


@when('I press the "Kirim Laporan" button')
def kirim(ctx):
    _kirim(ctx)


@when('I complete the location, category and description steps and press the "Kirim Laporan" button')
def lengkapi_dan_kirim(ctx):
    ctx["lokasi"] = "Jl. Kenjeran No. 210, Surabaya"
    _kirim(ctx, latitude=-7.2440, longitude=112.7960)


@when("the admin opens the ticket on the Verifikasi page")
def admin_buka_verifikasi(ctx):
    ctx["login_as"](ADMIN)
    ctx["browser"].get(f"{ctx['base']}/verifikasi?ticket_id={ctx['id_wo']}")


@when(parsers.parse('the admin presses the "Tolak" button and closes the ticket with reason "{alasan}"'))
def tolak_dengan_alasan(ctx, pilih_opsi, klik_dan_tunggu, alasan):
    b = ctx["browser"]
    b.get(f"{ctx['base']}/verifikasi?ticket_id={ctx['id_wo']}")
    b.find_element(By.ID, "tombolTolak").click()  # opens the <details> panel (no navigation)
    pilih_opsi("alasan_tutup", alasan)
    klik_dan_tunggu(b.find_element(By.ID, "tombolTutupTiket"))


# ------------------------------------------------------------------- Then
@then(parsers.parse('I see the notice "{pemberitahuan}"'))
def lihat_pemberitahuan(ctx, pemberitahuan):
    assert ctx["status_cv"] == pemberitahuan
    assert ctx["alert"].startswith(pemberitahuan)


@then(parsers.parse('I do not see the warning "{peringatan}"'))
def tidak_ada_peringatan_lama(ctx, peringatan):
    assert peringatan == PESAN_LAMA
    assert peringatan not in ctx["browser"].page_source


@then("I can proceed to the next step")
def bisa_lanjut(ctx):
    ctx["browser"].execute_script("bukaStep(2);")
    assert _panel_terlihat(ctx, 2) and not _panel_terlihat(ctx, 1)


@then(parsers.parse('I receive a new ticket number with initial status "{status}"'))
def tiket_baru(ctx, status):
    hasil = ctx["result"]
    assert hasil["success"] is True and hasil["is_duplicate"] is False
    assert hasil["ticket_id"] not in ctx["existing_ids"] and hasil["status_work_order"] == status
    assert hasil["perlu_tinjauan_manual"] is True and hasil["kategori_final"] == ctx["kategori"]
    ctx["id_wo"] = hasil["ticket_id"]


@then(parsers.parse('the new ticket is labelled "{label}" in the Verifikasi queue'))
def label_di_antrean(ctx, label):
    ctx["login_as"](ADMIN)
    b = ctx["browser"]
    b.get(f"{ctx['base']}/verifikasi?ticket_id={ctx['id_wo']}")
    baris = b.find_element(By.XPATH, f"//tr[td[normalize-space()='{ctx['id_wo']}']]")
    assert baris.find_element(By.CSS_SELECTOR, ".label-tinjauan-manual").text.strip() == label
    assert label in b.find_element(By.ID, "infoTinjauanManual").text


@then(parsers.parse('I see the options "{a}", "{b}" and "{c}"'))
def lihat_opsi(ctx, a, b, c):
    br = ctx["browser"]
    tombol = {e.text.strip() for e in br.find_elements(By.CSS_SELECTOR, "button, summary")}
    assert {a, b, c} <= tombol, tombol
    assert br.find_element(By.ID, "infoTinjauanManual")


@then('I do not see the "Setujui Tiket" button')
def tanpa_setujui(ctx):
    br = ctx["browser"]
    assert not br.find_elements(By.CSS_SELECTOR, f"form[action='/verifikasi/{ctx['id_wo']}/approve']")
    assert "Setujui Tiket" not in {e.text.strip() for e in br.find_elements(By.TAG_NAME, "button")}


@then("the Dashboard quick-approve of that ticket is rejected")
def aksi_cepat_ditolak(ctx):
    br = ctx["browser"]
    br.get(f"{ctx['base']}/Dashboard")
    baris = br.find_element(By.CSS_SELECTOR, f"tr[data-tiket='{ctx['id_wo']}']")
    assert baris.find_element(By.CSS_SELECTOR, ".label-tinjauan-manual").text.strip() == LABEL
    assert not baris.find_elements(By.CSS_SELECTOR, "form[action$='/quick-approve']")
    # a hand-made POST is refused by the backend as well
    c = TestClient(app)
    c.post("/Login", data={"identifier": ADMIN, "password": "password123"})
    r = c.post(f"/Dashboard/{ctx['id_wo']}/quick-approve", follow_redirects=False)
    assert r.status_code == 303 and "perlu%20tinjauan%20manual" in r.headers["location"]
    assert _db(lambda db: db.get(WorkOrder, ctx["id_wo"]).status_work_order) == "Dilaporkan"


@then(parsers.parse('I see the ticket status change to "{status}"'))
def status_berubah(ctx, status):
    assert _db(lambda db: db.get(WorkOrder, ctx["id_wo"]).status_work_order) == status
    assert ctx["browser"].find_element(By.ID, "infoDitutup").is_displayed()


@then(parsers.parse('the citizen "{no_hp}" receives a notification containing "{teks}"'))
def notifikasi_alasan(ctx, no_hp, teks):
    def cek(db):
        id_warga = db.query(Warga).filter_by(no_hp=no_hp).one().id_warga
        return [n.pesan for n in db.query(Notifikasi).filter_by(id_warga=id_warga, judul="Laporan ditutup")]
    pesan = _db(cek)
    assert len(pesan) == 1 and teks in pesan[0]


@then(parsers.parse('I see the error message "{pesan}"'))
def pesan_galat(ctx, pesan):
    assert ctx["alert"] == pesan
    assert ctx["result"] == {"success": False, "step": 1, "message": pesan}


@then("I cannot proceed to the next step")
def tidak_bisa_lanjut(ctx):
    ctx["browser"].execute_script("bukaStep(2);")
    assert _panel_terlihat(ctx, 1) and not _panel_terlihat(ctx, 2)
