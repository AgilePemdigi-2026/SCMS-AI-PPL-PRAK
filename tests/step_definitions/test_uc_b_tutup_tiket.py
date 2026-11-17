"""Sprint 3 / PRD 5.3 BR-4: closing a ticket ("Ditutup") with a mandatory reason.

Door (a): the Admin rejects a ticket still being verified ("Tolak").
Door (b): the inspector recommends closing; the Admin confirms or rejects the recommendation.
"""
import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from selenium.webdriver.common.by import By

from app.controllers.kontrol_inspeksi import KontrolInspeksi
from app.controllers.kontrol_lacak import PESAN_RATING_DITUTUP, KontrolLacak
from app.controllers.kontrol_penanganan import PESAN_REKOMENDASI_TERTUNDA, KontrolPenanganan
from app.database import SessionLocal
from app.models.entities import Laporan, Notifikasi, RiwayatStatus, Warga, WorkOrder
from database.seed import seed_data

scenarios("../features/uc_b_tutup_tiket.feature")

ADMIN = "admin@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"
TOMBOL_INSPEKSI = {"Simpan Hasil Inspeksi": "simpanInspeksi"}


@pytest.fixture
def ctx(browser, live_server, login_as, alur):
    seed_data(verbose=False)
    return {"browser": browser, "base": live_server, "login_as": login_as, "alur": alur}


def _db_jalankan(fungsi):
    db = SessionLocal()
    try:
        return fungsi(db)
    finally:
        db.close()


def _status(id_wo):
    return _db_jalankan(lambda db: db.get(WorkOrder, id_wo).status_work_order)


def _id_warga(no_hp):
    return _db_jalankan(lambda db: db.query(Warga).filter_by(no_hp=no_hp).one().id_warga)


# -------------------------------------------------------------- door (a)
@given(parsers.parse('the admin opens ticket "{id_wo}" of report "{id_laporan}" with status "{status}"'))
def admin_buka_tiket(ctx, id_wo, id_laporan, status):
    def siapkan(db):
        # Like UC-F/UC-J, the scenario's starting status is prepared directly in the test database.
        wo = db.get(WorkOrder, id_wo)
        wo.status_work_order = status
        for lap in db.query(Laporan).filter_by(id_work_order=id_wo):
            lap.status = status
        db.commit()
        assert db.get(Laporan, id_laporan).id_work_order == id_wo
    _db_jalankan(siapkan)
    ctx["id_wo"], ctx["id_laporan"] = id_wo, id_laporan
    ctx["notif_awal"] = _db_jalankan(lambda db: db.query(Notifikasi).count())
    ctx["login_as"](ADMIN)
    ctx["browser"].get(f"{ctx['base']}/verifikasi?ticket_id={id_wo}")
    assert ctx["browser"].find_element(By.ID, "prioritasTiket")


@when('the admin presses the "Tolak" button')
def tekan_tolak(ctx):
    ringkas = ctx["browser"].find_element(By.ID, "tombolTolak")
    assert ringkas.text.strip() == "Tolak"
    ringkas.click()  # opens the <details> panel (no navigation)
    assert ctx["browser"].find_element(By.ID, "formTolak").is_displayed()


@when(parsers.parse('the admin selects the closing reason "{alasan}"'))
def pilih_alasan(pilih_opsi, alasan):
    pilih_opsi("alasan_tutup", alasan)


@when('the admin confirms with the "Tutup Tiket" button')
@when('the admin confirms with the "Tutup Tiket" button without selecting a closing reason')
def konfirmasi_tutup_verifikasi(ctx, klik_dan_tunggu):
    tombol = ctx["browser"].find_element(By.ID, "tombolTutupTiket")
    assert tombol.text.strip() == "Tutup Tiket"
    klik_dan_tunggu(tombol)


@then(parsers.parse('I see the ticket status change to "{status}"'))
def status_berubah(ctx, status):
    assert _status(ctx["id_wo"]) == status
    b = ctx["browser"]
    assert b.find_element(By.ID, "infoDitutup").is_displayed()
    assert b.find_element(By.ID, "pesanVerifikasi").text.startswith(f"Tiket {ctx['id_wo']} ditutup")


@then(parsers.parse('the status history of "{id_wo}" contains "{teks}"'))
def riwayat_berisi(id_wo, teks):
    keterangan = _db_jalankan(lambda db: [r.keterangan or "" for r in
                                          db.query(RiwayatStatus).filter_by(id_work_order=id_wo)])
    assert any(teks in k for k in keterangan), keterangan


@then(parsers.parse('the citizen "{no_hp}" receives a notification containing "{teks}"'))
def notifikasi_alasan(ctx, no_hp, teks):
    id_warga = _id_warga(no_hp)
    notif = _db_jalankan(lambda db: db.query(Notifikasi).filter_by(id_warga=id_warga, judul="Laporan ditutup").all())
    assert len(notif) == 1, [n.pesan for n in notif]  # one per reporting citizen
    assert teks in notif[0].pesan and notif[0].status_baca is False


@then(parsers.parse('the citizen cannot submit a rating for report "{id_laporan}"'))
def tidak_bisa_rating(ctx, id_laporan):
    hasil = _db_jalankan(lambda db: KontrolLacak(db).simpan_rating(id_laporan, "USR-01", 5, "bagus"))
    assert hasil == {"success": False, "message": PESAN_RATING_DITUTUP}
    ctx["login_as"]("0812xxxxxxx")
    b = ctx["browser"]
    b.get(f"{ctx['base']}/lacak?id={id_laporan}")
    assert b.find_element(By.ID, "statusLaporan").text.strip() == "Ditutup"
    assert "Laporan tidak valid" in b.find_element(By.ID, "alasanDitutup").text
    assert b.find_element(By.ID, "ratingTidakTersedia")
    assert not b.find_elements(By.ID, "formRating")


@then(parsers.parse('the system displays a warning message "{pesan}"'))
def peringatan(ctx, pesan):
    b = ctx["browser"]
    assert b.find_element(By.ID, "pesanVerifikasi").text.strip() == pesan
    assert b.find_element(By.ID, "kotakPesanVerifikasi").get_attribute("data-jenis") == "gagal"


@then(parsers.parse('the ticket "{id_wo}" keeps the status "{status}"'))
def status_tetap(ctx, id_wo, status):
    assert _status(id_wo) == status
    assert _db_jalankan(lambda db: db.query(Notifikasi).filter_by(judul="Laporan ditutup").count()) == 0


# -------------------------------------------------------------- door (b)
@given(parsers.parse('the road inspector opens report details for "{id_laporan}" with status "{status}"'))
def penilik_buka(ctx, id_laporan, status):
    assert ctx["alur"]["status"](id_laporan) == status  # LAP-2026-0002 is assigned to Budi Santoso in the seed
    ctx["id_laporan"] = id_laporan
    ctx["id_wo"] = ctx["alur"]["id_wo"](id_laporan)
    ctx["login_as"](PENILIK)
    ctx["browser"].get(f"{ctx['base']}/TugasLapangan/{ctx['id_wo']}")
    assert ctx["browser"].find_element(By.ID, "formInspeksi")


@when(parsers.parse('the road inspector selects recommendation "{rekomendasi}" with reason "{alasan}"'))
def pilih_rekomendasi_tutup(ctx, pilih_opsi, rekomendasi, alasan):
    pilih_opsi("rekomendasi", rekomendasi)
    ctx["browser"].execute_script("tampilkanAlasanTutup();")  # what the select's onchange does
    assert ctx["browser"].find_element(By.ID, "alasan_rekomendasi").is_displayed()
    pilih_opsi("alasan_rekomendasi", alasan)


@when(parsers.parse('the road inspector selects damage level "{tingkat}"'))
def pilih_tingkat_kerusakan(pilih_tingkat, tingkat):
    pilih_tingkat(tingkat)


@when(parsers.parse('the road inspector uploads survey photo "{foto}" and clicks the "{tombol}" button'))
def unggah_dan_simpan(ctx, foto_uji, klik_dan_tunggu, foto, tombol):
    b = ctx["browser"]
    b.find_element(By.ID, "foto_survei").send_keys(foto_uji(foto))
    el = b.find_element(By.ID, TOMBOL_INSPEKSI[tombol])
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


@then(parsers.parse('the system updates the report status of "{id_laporan}" to "{status}"'))
def status_laporan(ctx, id_laporan, status):
    assert _db_jalankan(lambda db: db.get(Laporan, id_laporan).status) == status
    assert "Hasil inspeksi berhasil disimpan" in ctx["browser"].page_source


@given(parsers.parse('ticket "{id_wo}" is "{status}" with an inspector recommendation to close for reason "{alasan}"'))
def tiket_dengan_rekomendasi(ctx, id_wo, status, alasan):
    hasil = _db_jalankan(lambda db: KontrolInspeksi(db).simpan_inspeksi(
        id_wo, "PNL-01", "", "Tidak ada kerusakan di titik laporan", "Rekomendasikan Tutup",
        alasan_rekomendasi=alasan))
    assert hasil["success"], hasil
    assert _status(id_wo) == status
    ctx["id_wo"] = id_wo


@when(parsers.parse('the admin opens the Work Order "{id_wo}"'))
def admin_buka_wo(ctx, id_wo):
    ctx["login_as"](ADMIN)
    ctx["browser"].get(f"{ctx['base']}/work-orders?select_ticket={id_wo}")
    assert ctx["browser"].find_element(By.ID, "lencanaPrioritas")


@then(parsers.parse('the admin sees the inspector recommendation "{teks}"'))
def lihat_rekomendasi(ctx, teks):
    assert ctx["browser"].find_element(By.ID, "teksRekomendasiTutup").text.strip() == teks


@then('the "Terbitkan SPK" button is not available while the recommendation is pending')
def spk_ditahan(ctx):
    assert not ctx["browser"].find_elements(By.ID, "terbitkanSpk")
    hasil = _db_jalankan(lambda db: KontrolPenanganan(db).terbitkan_spk(
        ctx["id_wo"], "SPK/PUPR/XI/2026/099", "Satgas Rayon Gubeng"))
    assert hasil == {"success": False, "message": PESAN_REKOMENDASI_TERTUNDA}


@when('the admin presses the "Konfirmasi Tutup Tiket" button')
def klik_konfirmasi(ctx, klik_dan_tunggu):
    el = ctx["browser"].find_element(By.ID, "konfirmasiTutup")
    assert el.text.strip() == "Konfirmasi Tutup Tiket"
    klik_dan_tunggu(el)


@when('the admin presses the "Tolak Rekomendasi" button')
def klik_tolak_rekomendasi(ctx, klik_dan_tunggu):
    el = ctx["browser"].find_element(By.ID, "tolakRekomendasi")
    assert el.text.strip() == "Tolak Rekomendasi"
    klik_dan_tunggu(el)


@then(parsers.parse('the ticket "{id_wo}" has status "{status}"'))
def status_tiket(ctx, id_wo, status):
    assert _status(id_wo) == status
    assert ctx["browser"].find_element(By.ID, "infoTiketDitutup").is_displayed()


@then(parsers.parse('the SPK form with button "{tombol}" is available for "{id_wo}"'))
def spk_tersedia(ctx, tombol, id_wo):
    b = ctx["browser"]
    assert not b.find_elements(By.ID, "panelRekomendasiTutup")
    assert b.find_element(By.ID, "terbitkanSpk").text.strip() == tombol
