"""Sprint 3 / CO-3 (PRD 5.3 "Kunjungan lanjutan", decision 5.9 no. 7): a temporary repair keeps the
ticket "Dalam Proses" with one active follow-up visit date (a work plan, not a deadline); the ticket can
only become "Selesai" after that visit is recorded, which may happen before the planned date."""
from datetime import timedelta

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from selenium.webdriver.common.by import By

from app.controllers.kontrol_penanganan import KontrolPenanganan, hari_ini_wib
from app.database import SessionLocal
from app.models.entities import Laporan, Perbaikan, RiwayatStatus, WorkOrder
from database.seed import seed_data

scenarios("../features/uc_f_kunjungan_lanjutan.feature")

PENILIK = "budi.santoso@dpupr.surabaya.go.id"
TOMBOL = {"Perbarui Status Penanganan": "perbaruiStatus"}


@pytest.fixture
def ctx(browser, live_server, login_as, alur):
    seed_data(verbose=False)
    return {"browser": browser, "base": live_server, "login_as": login_as, "alur": alur}


def _db(fungsi):
    db = SessionLocal()
    try:
        return fungsi(db)
    finally:
        db.close()


def _tanggal(hari):
    return hari_ini_wib() + timedelta(days=hari)


def _jadwal(ctx):
    """All follow-up schedules of the ticket: [(status_jadwal, jadwal_lanjutan)]."""
    return _db(lambda db: [(p.status_jadwal, p.jadwal_lanjutan) for p in
                           db.query(Perbaikan).filter_by(id_work_order=ctx["id_wo"]).order_by(Perbaikan.id_perbaikan)
                           if p.status_jadwal])


def _buka_tugas(ctx):
    ctx["login_as"](PENILIK)
    ctx["browser"].get(f"{ctx['base']}/TugasLapangan/{ctx['id_wo']}")
    assert ctx["browser"].find_element(By.ID, "formProgres")


# ------------------------------------------------------------------ Given
@given(parsers.parse('report "{id_laporan}" is in "{status}" status assigned to road inspector "{nama}"'))
def laporan_dalam_proses(ctx, id_laporan, status, nama):
    ctx["alur"][status](id_laporan)  # Admin assigns PNL-01, inspection, SPK -> Dalam Proses
    ctx["id_laporan"], ctx["id_wo"] = id_laporan, ctx["alur"]["id_wo"](id_laporan)
    penilik = _db(lambda db: db.get(WorkOrder, ctx["id_wo"]).penilik.nama_penilik)
    assert (ctx["alur"]["status"](id_laporan), penilik) == (status, nama)
    _buka_tugas(ctx)


@given(parsers.parse('report "{id_laporan}" is "{status}" with a pending follow-up visit {hari:d} days from today'))
def laporan_dengan_jadwal(ctx, id_laporan, status, hari):
    ctx["alur"][status](id_laporan)
    ctx["id_laporan"], ctx["id_wo"] = id_laporan, ctx["alur"]["id_wo"](id_laporan)
    hasil = _db(lambda db: KontrolPenanganan(db).perbarui_progres(
        ctx["id_wo"], "Dalam Proses", "Ditambal sementara dengan cold mix", aktor="Budi Santoso",
        perbaikan_sementara=True, jadwal_lanjutan=_tanggal(hari).isoformat()))
    assert hasil["success"], hasil
    assert _jadwal(ctx) == [("Aktif", _tanggal(hari).isoformat())]
    _buka_tugas(ctx)


# ------------------------------------------------------------------- When
@when('the officer checks "Perbaikan sementara"')
def centang_sementara(ctx):
    b = ctx["browser"]
    kotak = b.find_element(By.ID, "perbaikan_sementara")
    kotak.click()  # toggles the date field (no navigation)
    assert kotak.is_selected() and b.find_element(By.ID, "jadwal_lanjutan").is_displayed()


def _isi_tanggal(ctx, tanggal):
    # set as ISO: a typed value would depend on the browser's date-input locale
    ctx["browser"].execute_script("document.getElementById('jadwal_lanjutan').value = arguments[0];", tanggal.isoformat())


@when(parsers.parse("the officer fills the follow-up visit date with the date {hari:d} days from today"))
def isi_tanggal(ctx, hari):
    _isi_tanggal(ctx, _tanggal(hari))


@when("the officer fills the follow-up visit date with yesterday's date")
def isi_kemarin(ctx):
    _isi_tanggal(ctx, _tanggal(-1))


@when(parsers.parse('the officer inputs progress notes "{catatan}"'))
def isi_catatan(ctx, catatan):
    el = ctx["browser"].find_element(By.ID, "catatan_progres")
    el.clear()
    el.send_keys(catatan)


@when(parsers.parse('the officer clicks the "{tombol}" button'))
def klik(ctx, klik_dan_tunggu, tombol):
    el = ctx["browser"].find_element(By.ID, TOMBOL[tombol])
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


@when(parsers.parse('the officer selects progress status "{status}" and uploads repair proof photo "{foto}"'))
def pilih_selesai(ctx, foto_uji, status, foto):
    b = ctx["browser"]
    opsi = b.find_element(By.CSS_SELECTOR, f"#status_baru option[value='{status}']")
    if opsi.get_attribute("disabled") is not None:
        # UI: "Selesai" is unavailable while a follow-up visit is pending, with an explanation.
        assert b.find_element(By.ID, "infoJadwalAktif").is_displayed()
        # Re-enable it to send the request anyway: the backend must refuse it too.
        assert opsi.text.strip() == "Selesai (catat kunjungan lanjutan dulu)"
        b.execute_script("arguments[0].disabled = false;", opsi)
        ctx["selesai_dipaksa"] = True
    b.execute_script("arguments[0].selected = true;", opsi)  # by value: the label may carry a hint
    assert b.find_element(By.ID, "status_baru").get_attribute("value") == status
    b.find_element(By.ID, "foto_selesai").send_keys(foto_uji(foto))


@when(parsers.parse('the officer records the follow-up visit today with notes "{catatan}"'))
def catat_kunjungan(ctx, klik_dan_tunggu, catatan):
    b = ctx["browser"]
    b.find_element(By.ID, "catatan_kunjungan").send_keys(catatan)
    tombol = b.find_element(By.ID, "catatKunjungan")
    assert tombol.text.strip() == "Catat Kunjungan Lanjutan"
    klik_dan_tunggu(tombol)


@when(parsers.parse("the officer reschedules the follow-up visit to the date {hari:d} days from today"))
def jadwal_ulang(ctx, klik_dan_tunggu, hari):
    centang_sementara(ctx)
    _isi_tanggal(ctx, _tanggal(hari))
    isi_catatan(ctx, "Pengaspalan hotmix bergeser karena hujan")
    klik(ctx, klik_dan_tunggu, "Perbarui Status Penanganan")


# ------------------------------------------------------------------- Then
@then(parsers.parse('the ticket "{id_wo}" keeps the status "{status}"'))
def status_tetap(ctx, id_wo, status):
    assert _db(lambda db: db.get(WorkOrder, id_wo).status_work_order) == status
    assert _jadwal(ctx) == [("Aktif", _tanggal(7).isoformat())]
    # same-status history entry: no new transition
    riwayat = _db(lambda db: [r.status for r in db.query(RiwayatStatus).filter_by(id_work_order=id_wo)])
    assert riwayat.count("Selesai") == 0 and riwayat[-1] == "Dalam Proses"


@then('the follow-up visit date is shown on the "Tugas Lapangan" page')
def jadwal_di_tugas_lapangan(ctx):
    b = ctx["browser"]
    tampil = _tanggal(7).strftime("%d/%m/%Y")
    assert tampil in b.find_element(By.ID, "infoJadwalAktif").text
    b.get(f"{ctx['base']}/TugasLapangan")
    kartu = b.find_element(By.CSS_SELECTOR, f"a[href='/TugasLapangan/{ctx['id_wo']}'] .jadwal-lanjutan")
    assert kartu.text.strip() == f"Kunjungan lanjutan dijadwalkan {tampil}"


@then(parsers.parse('the citizen timeline of "{id_laporan}" shows "{teks}"'))
def linimasa_warga(ctx, id_laporan, teks):
    ctx["login_as"]("0812xxxxxxx")
    b = ctx["browser"]
    b.get(f"{ctx['base']}/lacak?id={id_laporan}")
    tampil = _tanggal(7).strftime("%d/%m/%Y")
    assert f"{teks} {tampil}" in b.find_element(By.CSS_SELECTOR, "#linimasa .tahap-lanjutan").text
    assert f"{teks} {tampil}" in b.find_element(By.ID, "riwayatStatus").text


@then("the system rejects the WorkOrder status update")
def ditolak(ctx):
    assert ctx.get("selesai_dipaksa") is True
    assert ctx["alur"]["status"](ctx["id_laporan"]) == "Dalam Proses"
    assert _db(lambda db: db.query(Perbaikan).filter_by(id_work_order=ctx["id_wo"], status_perbaikan="Selesai").count()) == 0


@then(parsers.parse('the system displays an error message "{pesan}"'))
@then(parsers.parse('the system displays a warning message "{pesan}"'))
def pesan(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan


@then(parsers.parse('no follow-up visit is saved for "{id_wo}"'))
def tanpa_jadwal(ctx, id_wo):
    assert _jadwal(ctx) == []
    assert _db(lambda db: db.get(WorkOrder, id_wo).status_work_order) == "Dalam Proses"


@then("the follow-up visit is saved even though its scheduled date has not arrived")
def kunjungan_tersimpan(ctx):
    def cek(db):
        p = db.query(Perbaikan).filter_by(id_work_order=ctx["id_wo"], status_jadwal="Tercatat").one()
        return p.tanggal_lanjutan, p.kunjungan_dicatat_pada, p.catatan_kunjungan, db.get(WorkOrder, ctx["id_wo"]).jadwal_lanjutan_aktif
    tanggal, dicatat, catatan, aktif = _db(cek)
    assert dicatat is not None and tanggal > hari_ini_wib() and aktif is None
    assert catatan == "Hotmix permanen sudah dipasang"
    b = ctx["browser"]
    assert "Kunjungan lanjutan berhasil dicatat" in b.page_source
    assert b.find_element(By.CSS_SELECTOR, "#status_baru option[value='Selesai']").get_attribute("disabled") is None


@then(parsers.parse('the system updates the WorkOrder status and report status of "{id_laporan}" to "{status}"'))
def selesai(ctx, id_laporan, status):
    assert ctx["alur"]["status"](id_laporan) == status
    assert _db(lambda db: db.get(Laporan, id_laporan).status) == status


@then(parsers.parse('"{id_wo}" has exactly one active follow-up visit, dated {hari:d} days from today'))
def satu_jadwal_aktif(ctx, id_wo, hari):
    assert _jadwal(ctx) == [("Diganti", _tanggal(7).isoformat()), ("Aktif", _tanggal(hari).isoformat())]
    assert _db(lambda db: db.get(WorkOrder, id_wo).jadwal_lanjutan_aktif.tanggal_lanjutan) == _tanggal(hari)


@then(parsers.parse('the earlier schedule is kept in the status history as "{teks}"'))
def riwayat_jadwal_ulang(ctx, teks):
    riwayat = _db(lambda db: [r.keterangan or "" for r in db.query(RiwayatStatus).filter_by(id_work_order=ctx["id_wo"])])
    lama, baru = _tanggal(7).strftime("%d/%m/%Y"), _tanggal(14).strftime("%d/%m/%Y")
    assert any(f"{teks} ke {baru} (sebelumnya {lama})" in k for k in riwayat), riwayat


@then(parsers.parse('the "Tugas Lapangan" page shows only the date {hari:d} days from today'))
def hanya_jadwal_baru(ctx, hari):
    b = ctx["browser"]
    b.get(f"{ctx['base']}/TugasLapangan")
    kartu = b.find_elements(By.CSS_SELECTOR, f"a[href='/TugasLapangan/{ctx['id_wo']}'] .jadwal-lanjutan")
    assert [k.get_attribute("data-tanggal") for k in kartu] == [_tanggal(hari).isoformat()]
    assert _tanggal(7).strftime("%d/%m/%Y") not in b.page_source
