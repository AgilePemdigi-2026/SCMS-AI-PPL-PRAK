"""Sprint 3 / CO-2 (PRD 5.3 "Temuan baru"): the assigned inspector records other damage found around
the inspected location. It goes through the citizen report flow (BR-1/BR-2/BR-3) as a "Temuan Penilik"
report without a citizen; only citizens who later join the ticket are notified."""
import io

import pytest
from PIL import Image
from pytest_bdd import given, parsers, scenarios, then, when
from selenium.webdriver.common.by import By

from app.controllers.kontrol_inspeksi import KontrolInspeksi
from app.controllers.kontrol_pelaporan import KontrolPelaporan
from app.controllers.kontrol_verifikasi import KontrolVerifikasi, tiket_ambigu
from app.database import SessionLocal
from app.models.entities import Laporan, Notifikasi, RiwayatStatus, Warga, WorkOrder
from database.seed import seed_data

scenarios("../features/uc_e_temuan_baru.feature")

PENILIK = "budi.santoso@dpupr.surabaya.go.id"
ADMIN = "admin@dpupr.surabaya.go.id"


def _jpeg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (100, 100, 100)).save(b, "JPEG")
    return b.getvalue()


def _db(fungsi):
    db = SessionLocal()
    try:
        return fungsi(db)
    finally:
        db.close()


def _koordinat(teks):
    lat, lng = (float(x) for x in teks.split(","))
    return lat, lng


@pytest.fixture
def ctx(browser, live_server, login_as, alur):
    seed_data(verbose=False)
    return {"browser": browser, "base": live_server, "login_as": login_as, "alur": alur,
            "wo_awal": _db(lambda db: {w.id_work_order for w in db.query(WorkOrder).all()}),
            "lap_awal": _db(lambda db: {l.id_laporan for l in db.query(Laporan).all()})}


def _laporan_baru(ctx):
    return _db(lambda db: [l for l in db.query(Laporan).all() if l.id_laporan not in ctx["lap_awal"]])


# ------------------------------------------------------------------ Given
@given(parsers.parse('the road inspector opens report details for "{id_laporan}" with status "{status}"'))
def penilik_buka(ctx, id_laporan, status):
    assert ctx["alur"]["status"](id_laporan) == status  # LAP-2026-0002 is assigned to Budi Santoso in the seed
    ctx["id_wo_asal"] = ctx["alur"]["id_wo"](id_laporan)
    ctx["status_asal"] = status
    ctx["login_as"](PENILIK)
    ctx["browser"].get(f"{ctx['base']}/TugasLapangan/{ctx['id_wo_asal']}")
    assert ctx["browser"].find_element(By.ID, "panelTemuan")


@given(parsers.parse('a finding ticket with source "{sumber}" and category "{kategori}" exists at "{titik}" with status "{status}"'))
def tiket_temuan_ada(ctx, sumber, kategori, titik, status):
    lat, lng = _koordinat(titik)
    hasil = _db(lambda db: KontrolInspeksi(db).catat_temuan(
        "REP-2026-00298", "PNL-01", "temuan_sudirman_80.jpg", _jpeg(), kategori,
        "Retak memanjang di bahu jalan sekitar 3 meter", lat, lng, "Jl. Sudirman No. 80, Surabaya"))
    assert hasil["success"] and not hasil["is_duplicate"], hasil
    ctx["id_wo_temuan"] = hasil["ticket_id"]
    wo = _db(lambda db: (db.get(WorkOrder, hasil["ticket_id"]).status_work_order,
                         db.get(WorkOrder, hasil["ticket_id"]).dari_temuan))
    assert wo == (status, True) and sumber == "Temuan Penilik"
    ctx["titik"] = (lat, lng)


# ------------------------------------------------------------------- When
@when('the road inspector opens the "Catat Temuan Baru" form')
def buka_form(ctx):
    ringkas = ctx["browser"].find_element(By.ID, "bukaFormTemuan")
    assert ringkas.text.strip() == "Catat Temuan Baru"
    ringkas.click()  # opens the <details> panel (no navigation)
    assert ctx["browser"].find_element(By.ID, "formTemuan").is_displayed()


@when(parsers.parse('the road inspector uploads finding photo "{foto}"'))
def unggah_foto(ctx, foto_uji, foto):
    ctx["browser"].find_element(By.ID, "foto_temuan").send_keys(foto_uji(foto))


@when(parsers.parse('the road inspector selects finding category "{kategori}"'))
def pilih_kategori(pilih_opsi, kategori):
    pilih_opsi("kategori_temuan", kategori)


@when(parsers.parse('the road inspector enters finding description "{deskripsi}"'))
def isi_deskripsi(ctx, deskripsi):
    ctx["browser"].find_element(By.ID, "deskripsi_temuan").send_keys(deskripsi)


def _tandai_titik(ctx, lat, lng):
    b = ctx["browser"]
    b.execute_script("window.tandaiTitikTemuan(arguments[0], arguments[1]);", lat, lng)  # what a map click does
    assert float(b.find_element(By.ID, "latitude_temuan").get_attribute("value")) == pytest.approx(lat)
    assert float(b.find_element(By.ID, "longitude_temuan").get_attribute("value")) == pytest.approx(lng)


@when(parsers.parse('the road inspector marks the finding point "{titik}" on the map'))
def tandai_titik(ctx, titik):
    _tandai_titik(ctx, *_koordinat(titik))


@when(parsers.parse('the road inspector records a finding with category "{kategori}" at point "{titik}" with photo "{foto}"'))
def catat_temuan_lengkap(ctx, pilih_opsi, foto_uji, kategori, titik, foto):
    buka_form(ctx)
    unggah_foto(ctx, foto_uji, foto)
    pilih_opsi("kategori_temuan", kategori)
    isi_deskripsi(ctx, "Lubang di jalur kiri dekat titik laporan sebelumnya")
    _tandai_titik(ctx, *_koordinat(titik))


@when("the road inspector fills in the finding category, description and map point without uploading a photo")
def isi_tanpa_foto(ctx, pilih_opsi):
    buka_form(ctx)
    pilih_opsi("kategori_temuan", "Retak Permukaan")
    isi_deskripsi(ctx, "Retak memanjang di bahu jalan sekitar 3 meter")
    _tandai_titik(ctx, -7.26700, 112.74950)


@when(parsers.parse('the road inspector clicks the "{tombol}" button'))
def klik_simpan(ctx, klik_dan_tunggu, tombol):
    el = ctx["browser"].find_element(By.ID, "simpanTemuan")
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


@when(parsers.parse('the citizen "{no_hp}" submits a "{kategori}" report at the same point with a similar description'))
def warga_melapor(ctx, no_hp, kategori):
    id_warga = _db(lambda db: db.query(Warga).filter_by(no_hp=no_hp).one().id_warga)
    lat, lng = ctx["titik"]
    ctx["hasil_warga"] = _db(lambda db: KontrolPelaporan(db).kirim_laporan(
        filename="retak_bahu_sudirman.jpg", file_size_mb=0.1, lokasi_jalan="Jl. Sudirman No. 80, Surabaya",
        deskripsi="Retak memanjang di bahu jalan Sudirman", kategori_pilihan=kategori,
        latitude=lat + 0.00002, longitude=lng + 0.00002, id_warga=id_warga))
    ctx["id_warga"] = id_warga


@when("the admin approves the finding ticket")
def admin_menyetujui(ctx):
    def setujui(db):
        k = KontrolVerifikasi(db)
        wo = db.get(WorkOrder, ctx["id_wo_temuan"])
        # an ambiguous score is approved through "Lanjutkan Tanpa Inspeksi" (UC-B rule)
        wo = k.lanjutkan_tanpa_inspeksi(wo.id_work_order, ADMIN) if tiket_ambigu(wo) else k.setujui_tiket(wo.id_work_order, ADMIN)
        return wo.status_work_order
    assert _db(setujui) == "Disetujui"


# ------------------------------------------------------------------- Then
@then(parsers.parse('the system creates a new ticket with source "{sumber}" and status "{status}"'))
def tiket_baru(ctx, sumber, status):
    baru = _db(lambda db: [w for w in db.query(WorkOrder).all() if w.id_work_order not in ctx["wo_awal"]])
    assert len(baru) == 1
    ctx["id_wo_temuan"] = baru[0].id_work_order
    lap = _laporan_baru(ctx)
    assert len(lap) == 1 and lap[0].sumber == sumber and lap[0].id_work_order == ctx["id_wo_temuan"]
    assert baru[0].status_work_order == status and baru[0].exposure_count == 1
    assert f"Temuan dicatat sebagai tiket baru {ctx['id_wo_temuan']}" in ctx["browser"].page_source


@then(parsers.parse('the new report has no reporting citizen and is recorded by road inspector "{nama}"'))
def tanpa_warga(ctx, nama):
    def cek(db):
        lap = db.query(Laporan).filter_by(id_work_order=ctx["id_wo_temuan"]).one()
        return lap.id_warga, lap.id_penilik_pencatat, lap.label_pelapor
    assert _db(cek) == (None, "PNL-01", f"Temuan Penilik: {nama}")


@then("the new ticket appears in the Verifikasi queue")
def di_antrean(ctx):
    ctx["login_as"](ADMIN)
    b = ctx["browser"]
    b.get(f"{ctx['base']}/verifikasi?ticket_id={ctx['id_wo_temuan']}")
    baris = b.find_element(By.XPATH, f"//tr[td[normalize-space()='{ctx['id_wo_temuan']}']]")
    assert baris.find_element(By.CSS_SELECTOR, ".label-sumber-temuan").text.strip() == "Temuan Penilik"
    assert b.find_element(By.ID, "sumberLaporan").text.strip() == "Pelapor: Temuan Penilik: Budi Santoso"


@then(parsers.parse('the ticket "{id_wo}" keeps the status "{status}"'))
def tiket_asal_tetap(ctx, id_wo, status):
    def cek(db):
        return (db.get(WorkOrder, id_wo).status_work_order,
                [r.keterangan or "" for r in db.query(RiwayatStatus).filter_by(id_work_order=id_wo)])
    status_kini, riwayat = _db(cek)
    assert status_kini == status
    assert any(k.startswith(f"Penilik mencatat temuan baru {ctx['id_wo_temuan']} / ") for k in riwayat), riwayat


@then("no citizen notification is created for the new ticket")
def tanpa_notifikasi(ctx):
    def jumlah(db):
        ids = [l.id_laporan for l in db.query(Laporan).filter_by(id_work_order=ctx["id_wo_temuan"])]
        return db.query(Notifikasi).filter(Notifikasi.id_laporan.in_(ids)).count()
    assert _db(jumlah) == 0


@then("the citizen report is merged into the finding ticket")
def digabung_ke_temuan(ctx):
    hasil = ctx["hasil_warga"]
    assert hasil["success"] and hasil["is_duplicate"] and hasil["ticket_id"] == ctx["id_wo_temuan"]
    assert hasil["exposure_count"] == 2  # the finding counts once, the first citizen adds one (5.9 no. 11)


@then(parsers.parse('the citizen "{no_hp}" receives the notification "{judul}"'))
def notifikasi_gabung(ctx, no_hp, judul):
    n = _db(lambda db: db.query(Notifikasi).filter_by(id_warga=ctx["id_warga"], judul=judul).all())
    assert len(n) == 1 and ctx["id_wo_temuan"] in n[0].pesan


@then(parsers.parse('the citizen "{no_hp}" receives a status notification for the finding ticket'))
def notifikasi_status(ctx, no_hp):
    def cek(db):
        lap = db.query(Laporan).filter_by(id_work_order=ctx["id_wo_temuan"], id_warga=ctx["id_warga"]).one()
        return [n.judul for n in db.query(Notifikasi).filter_by(id_laporan=lap.id_laporan)]
    judul = _db(cek)
    assert "Laporan diverifikasi" in judul  # one per citizen; the finding itself notifies nobody
    assert _db(lambda db: db.query(Notifikasi).filter(Notifikasi.id_warga.is_(None)).count()) == 0


@then("no new ticket is created")
def tanpa_tiket_baru(ctx):
    assert _db(lambda db: {w.id_work_order for w in db.query(WorkOrder).all()}) == ctx["wo_awal"]


@then(parsers.parse('the finding is merged into ticket "{id_wo}"'))
def digabung(ctx, id_wo):
    lap = _laporan_baru(ctx)
    assert len(lap) == 1 and lap[0].id_work_order == id_wo and lap[0].sumber == "Temuan Penilik"
    assert _db(lambda db: db.get(WorkOrder, id_wo).exposure_count) == 1  # a finding never raises exposure


@then(parsers.parse('the system displays the message "{pesan}"'))
def pesan_sukses(ctx, pesan):
    assert pesan in ctx["browser"].page_source


@then(parsers.parse('the system displays a warning message "{pesan}"'))
def pesan_peringatan(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan
    assert _laporan_baru(ctx) == []
