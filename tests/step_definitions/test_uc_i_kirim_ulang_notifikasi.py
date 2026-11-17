"""Sprint 3 / PRD 5.3 BR-8: delivery status, automatic retries and the Admin's "Kirim Ulang".

The simulated outside channel fails when random.random() < SCMS_NOTIF_TINGKAT_GAGAL. The live
server runs in this process, so setting the variable with monkeypatch reaches the app (it is read
on every send) and is restored after each scenario. Data lives in the separate test database.
"""
import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from selenium.webdriver.common.by import By

from app.controllers.kontrol_notifikasi import PESAN_KIRIM_ULANG_OK
from app.database import SessionLocal
from app.models.entities import Laporan, Notifikasi, Warga, WorkOrder
from app.services.alur_status import kirim_notifikasi
from app.services.pengiriman_notifikasi import ENV_TINGKAT_GAGAL, KIRIM_GAGAL
from database.seed import seed_data

scenarios("../features/uc_i_kirim_ulang_notifikasi.feature")

ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"


@pytest.fixture
def ctx(browser, live_server, login_as, monkeypatch):
    seed_data(verbose=False)
    monkeypatch.delenv(ENV_TINGKAT_GAGAL, raising=False)
    return {"browser": browser, "base": live_server, "login_as": login_as, "monkeypatch": monkeypatch}


def _db(fungsi):
    db = SessionLocal()
    try:
        return fungsi(db)
    finally:
        db.close()


def _notif(id_notifikasi):
    return _db(lambda db: db.get(Notifikasi, id_notifikasi))


def _id_notif_baru(id_laporan, sebelum):
    """The notification for `id_laporan` created by the step under test (not in `sebelum`)."""
    def cari(db):
        baru = [n for n in db.query(Notifikasi).filter_by(id_laporan=id_laporan)
                if n.id_notifikasi not in sebelum]
        assert len(baru) == 1, f"Harus ada tepat satu notifikasi baru untuk {id_laporan}, ada {len(baru)}"
        return baru[0].id_notifikasi
    return _db(cari)


def _baris(ctx, id_notifikasi):
    return ctx["browser"].find_elements(By.CSS_SELECTOR, f"#tabelNotifGagal tr[data-notifikasi='{id_notifikasi}']")


# ------------------------------------------------------------------ Given
@given(parsers.parse('the notification delivery channel failure rate is "{tingkat}"'))
def atur_tingkat_gagal(ctx, tingkat):
    ctx["monkeypatch"].setenv(ENV_TINGKAT_GAGAL, tingkat)


@given(parsers.parse('a notification for report "{id_laporan}" has delivery status "Gagal"'))
def notif_gagal(ctx, id_laporan):
    """Made through the real send path (kirim_notifikasi) with a channel that always fails."""
    ctx["monkeypatch"].setenv(ENV_TINGKAT_GAGAL, "1")

    def buat(db):
        notif = kirim_notifikasi(db, db.get(Laporan, id_laporan), "Laporan diverifikasi",
                                 "Laporan Anda telah diverifikasi dan disetujui oleh Dinas PUPR.")
        db.commit()
        return notif.id_notifikasi
    ctx["id_notif"] = _db(buat)
    ctx["monkeypatch"].delenv(ENV_TINGKAT_GAGAL)
    n = _notif(ctx["id_notif"])
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_GAGAL, 4)


# ------------------------------------------------------------------ When
@when(parsers.parse('the admin assigns road inspector "{nama}" to ticket "{id_wo}"'))
def admin_tugaskan(ctx, klik_dan_tunggu, nama, id_wo):
    ctx["notif_sebelum"] = _db(lambda db: {n.id_notifikasi for n in db.query(Notifikasi)})
    ctx["login_as"](ADMIN)
    b = ctx["browser"]
    b.get(f"{ctx['base']}/work-orders?select_ticket={id_wo}")
    ok = b.execute_script(
        "var s = document.querySelector('form[action$=\"/assign\"] select[name=\"nama_penilik\"]');"
        "if (!s) return false;"
        "for (var i = 0; i < s.options.length; i++) {"
        "  if (s.options[i].text.trim().indexOf(arguments[0]) === 0) { s.selectedIndex = i; return true; }"
        "} return false;", nama)
    assert ok, f"Penilik '{nama}' tidak ada di daftar penugasan tiket {id_wo}"
    klik_dan_tunggu(b.find_element(By.CSS_SELECTOR, "form[action$='/assign'] button[type='submit']"))


@when('the admin opens the "Notifikasi Gagal" page')
def admin_buka_halaman(ctx, klik_dan_tunggu):
    ctx["login_as"](ADMIN)
    _buka_lewat_menu(ctx, klik_dan_tunggu)


@when('the head of division opens the "Notifikasi Gagal" page')
def kabid_buka_halaman(ctx, klik_dan_tunggu):
    ctx["login_as"](KABID)
    _buka_lewat_menu(ctx, klik_dan_tunggu)


def _buka_lewat_menu(ctx, klik_dan_tunggu):
    b = ctx["browser"]
    b.get(f"{ctx['base']}/Dashboard")
    menu = b.find_element(By.ID, "menuNotifikasiGagal")
    assert "Notifikasi Gagal" in menu.text
    klik_dan_tunggu(menu)
    assert b.current_url.endswith("/notifikasi-gagal")
    assert _baris(ctx, ctx["id_notif"]), "Notifikasi gagal tidak tampil di daftar"


@when(parsers.parse('the admin clicks the "Kirim Ulang" button for report "{id_laporan}"'))
def klik_kirim_ulang(ctx, klik_dan_tunggu, id_laporan):
    baris = _baris(ctx, ctx["id_notif"])[0]
    assert baris.get_attribute("data-laporan") == id_laporan
    tombol = baris.find_element(By.CSS_SELECTOR, ".tombol-kirim-ulang")
    assert tombol.text.strip() == "Kirim Ulang"
    klik_dan_tunggu(tombol)


# ------------------------------------------------------------------ Then
@then(parsers.parse('the citizen "{no_hp}" receives a notification for report "{id_laporan}"'))
def warga_terima(ctx, no_hp, id_laporan):
    ctx["id_notif"] = _id_notif_baru(id_laporan, ctx["notif_sebelum"])
    n = _notif(ctx["id_notif"])
    id_warga = _db(lambda db: db.query(Warga).filter_by(no_hp=no_hp).one().id_warga)
    assert n.id_warga == id_warga
    assert n.judul == "Petugas ditugaskan"


@then(parsers.parse('the notification delivery status is "{status}" after 1 attempt'))
def terkirim_satu_kali(ctx, status):
    n = _notif(ctx["id_notif"])
    assert (n.status_kirim, n.jumlah_percobaan) == (status, 1)
    assert n.waktu_percobaan_terakhir is not None


@then(parsers.parse('the ticket "{id_wo}" has status "{status}"'))
def status_tiket(id_wo, status):
    assert _db(lambda db: db.get(WorkOrder, id_wo).status_work_order) == status


@then(parsers.parse('the notification for report "{id_laporan}" has delivery status "{status}" after 3 automatic retries'))
def gagal_setelah_ulang(ctx, id_laporan, status):
    ctx["id_notif"] = _id_notif_baru(id_laporan, ctx["notif_sebelum"])
    assert _notif(ctx["id_notif"]).status_kirim == status


@then("the notification delivery attempt count is 4 (1 initial send + 3 retries)")
def empat_percobaan(ctx):
    assert _notif(ctx["id_notif"]).jumlah_percobaan == 4


@then('the notification appears on the "Notifikasi Gagal" page with the "Kirim Ulang" button')
def tampil_di_daftar(ctx, klik_dan_tunggu):
    _buka_lewat_menu(ctx, klik_dan_tunggu)
    baris = _baris(ctx, ctx["id_notif"])[0]
    assert baris.find_element(By.CSS_SELECTOR, "[data-percobaan]").text.strip() == "4"
    assert baris.find_element(By.CSS_SELECTOR, ".tombol-kirim-ulang").text.strip() == "Kirim Ulang"


@then(parsers.parse('the system displays the message "{pesan}"'))
def pesan_tampil(ctx, pesan):
    assert pesan == PESAN_KIRIM_ULANG_OK
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan


@then(parsers.parse('the notification delivery status is "{status}"'))
def status_kirim(ctx, status):
    assert _notif(ctx["id_notif"]).status_kirim == status


@then('the notification no longer appears on the "Notifikasi Gagal" page')
def hilang_dari_daftar(ctx):
    b = ctx["browser"]
    assert b.current_url.endswith("/notifikasi-gagal")
    assert not _baris(ctx, ctx["id_notif"])


@then('the head of division does not see the "Kirim Ulang" button')
def kabid_tanpa_tombol(ctx):
    b = ctx["browser"]
    assert not b.find_elements(By.CSS_SELECTOR, ".tombol-kirim-ulang")
    assert "Kirim Ulang" not in b.find_element(By.ID, "tabelNotifGagal").text


@then("a direct resend request by the head of division is rejected with status 403")
def kabid_post_403(ctx):
    # A real POST from the Kepala Bidang's own browser session (same cookie), bypassing the UI.
    kode = ctx["browser"].execute_async_script(
        "var selesai = arguments[arguments.length - 1];"
        "fetch('/notifikasi-gagal/' + arguments[0] + '/kirim-ulang', {method: 'POST', redirect: 'manual'})"
        "  .then(function (r) { selesai(r.status); }).catch(function (e) { selesai('galat: ' + e); });",
        ctx["id_notif"])
    assert kode == 403
    n = _notif(ctx["id_notif"])
    assert (n.status_kirim, n.jumlah_percobaan) == (KIRIM_GAGAL, 4)
