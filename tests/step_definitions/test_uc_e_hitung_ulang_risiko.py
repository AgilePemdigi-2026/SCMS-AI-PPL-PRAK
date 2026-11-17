"""Sprint 3 / CO-1 (PRD 5.3 BR-2): Risk Score recalculated with the field damage level.

Bagian 1A bound the three recompute scenarios one by one; since Bagian 1B (closing
recommendation) the whole feature is bound, including the Scenario Outline
"Damage level is optional only when no damage is found".
"""
import re

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from selenium.webdriver.common.by import By

from app.controllers.kontrol_dashboard import warna_marker, warna_prioritas
from app.database import SessionLocal
from app.models.entities import Inspeksi, Laporan, RiwayatStatus, WorkOrder
from database.seed import seed_data

scenarios("../features/uc_e_hitung_ulang_risiko.feature")

TOMBOL = {"Simpan Hasil Inspeksi": "simpanInspeksi"}


@pytest.fixture
def ctx(browser, live_server, login_as, alur):
    seed_data(verbose=False)
    login_as("budi.santoso@dpupr.surabaya.go.id")
    return {"browser": browser, "base": live_server, "alur": alur}


def _wo(id_wo):
    db = SessionLocal()
    try:
        wo = db.get(WorkOrder, id_wo)
        return {"risk_score": wo.risk_score, "prioritas": wo.prioritas, "severity_ai": wo.severity_ai,
                "severity_kasus": wo.severity_score_kasus, "warna_marker": warna_marker(wo),
                "status": wo.status_work_order}
    finally:
        db.close()


def _rgb(hex_warna: str) -> tuple:
    h = hex_warna.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ------------------------------------------------------------------- Given
@given(parsers.parse('the road inspector opens report details for "{id_laporan}" with status "{status}"'))
def buka_detail(ctx, id_laporan, status):
    if status in ctx["alur"]:
        ctx["alur"][status](id_laporan)  # REP-2026-00298 is already Ditugaskan to Budi Santoso in the seed
    assert ctx["alur"]["status"](id_laporan) == status
    ctx["status_awal"] = status
    ctx["id_laporan"] = id_laporan
    ctx["id_wo"] = ctx["alur"]["id_wo"](id_laporan)
    ctx["browser"].get(f"{ctx['base']}/TugasLapangan/{ctx['id_wo']}")
    assert ctx["browser"].find_element(By.ID, "formInspeksi")


@given(parsers.parse('the ticket "{id_wo}" has Risk Score "{skor}" with priority "{prioritas}"'))
def risk_score_awal(id_wo, skor, prioritas):
    wo = _wo(id_wo)
    assert (wo["risk_score"], wo["prioritas"]) == (float(skor), prioritas)


# -------------------------------------------------------------------- When
@when(parsers.parse('the road inspector confirms the category "{kategori}"'))
def konfirmasi_kategori(ctx, pilih_opsi, kategori):
    pilih_opsi("kategori_terkonfirmasi", kategori)


@when(parsers.parse('the road inspector selects damage level "{tingkat}"'))
def pilih_tingkat_kerusakan(pilih_tingkat, tingkat):
    pilih_tingkat(tingkat)


@when("the road inspector leaves the damage level empty")
def kosongkan_tingkat(ctx):
    terpilih = ctx["browser"].execute_script(
        "var r = document.querySelectorAll('input[name=\"tingkat_kerusakan\"]');"
        "r.forEach(function (x) { x.checked = false; }); return r.length;")
    assert terpilih == 4  # Ringan, Sedang, Berat, Sangat Berat


@when(parsers.parse('the road inspector fills in the remaining inspection fields and uploads survey photo "{foto}"'))
def isi_sisa_form(ctx, pilih_opsi, foto_uji, foto):
    b = ctx["browser"]
    dimensi = b.find_element(By.ID, "dimensi_kerusakan")
    dimensi.clear()
    dimensi.send_keys("1.5m x 1m x 0.1m")
    b.find_element(By.ID, "catatan_teknis").send_keys("Kondisi dicek langsung di lokasi")
    pilih_opsi("rekomendasi", "Tambal Hotmix")
    b.find_element(By.ID, "foto_survei").send_keys(foto_uji(foto))


@when(parsers.parse('the road inspector clicks the "{tombol}" button'))
def klik(ctx, klik_dan_tunggu, tombol):
    el = ctx["browser"].find_element(By.ID, TOMBOL[tombol])
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


# -------------------------------------------------------------------- Then
@then(parsers.parse('the system updates the report status of "{id_laporan}" to "{status}"'))
def status_laporan(ctx, id_laporan, status):
    db = SessionLocal()
    try:
        assert db.get(Laporan, id_laporan).status == status
    finally:
        db.close()
    assert "Hasil inspeksi berhasil disimpan" in ctx["browser"].page_source


@then(parsers.parse('the ticket "{id_wo}" has Risk Score "{skor}" with priority "{prioritas}"'))
def risk_score_baru(ctx, id_wo, skor, prioritas):
    wo = _wo(id_wo)
    assert (wo["risk_score"], wo["prioritas"]) == (float(skor), prioritas)
    # the header badge of the task page shows the recalculated priority and score
    lencana = ctx["browser"].find_element(By.CSS_SELECTOR, "#kepalaTiket .lencana-prioritas")
    assert lencana.get_attribute("data-prioritas") == prioritas
    assert f"Risk Score {skor}" in lencana.text


@then(parsers.parse('the ticket keeps the AI severity "{severity_ai}" for comparison next to the field severity "{severity_lapangan}"'))
def severity_berdampingan(ctx, severity_ai, severity_lapangan):
    wo = _wo(ctx["id_wo"])
    assert wo["severity_ai"] == float(severity_ai)
    assert wo["severity_kasus"] == float(severity_lapangan)  # the field severity is what BR-2 now uses
    b = ctx["browser"]
    assert float(b.find_element(By.ID, "severityAi").get_attribute("data-nilai")) == float(severity_ai)
    assert float(b.find_element(By.ID, "severityLapangan").get_attribute("data-nilai")) == float(severity_lapangan)
    db = SessionLocal()
    try:
        ins = db.query(Inspeksi).filter_by(id_work_order=ctx["id_wo"]).one()
        assert ins.severity_lapangan == float(severity_lapangan)
        assert ins.kategori_terkonfirmasi == "Jalan Berlubang"
    finally:
        db.close()


@then(parsers.parse('the status history of "{id_wo}" contains "{teks}"'))
def riwayat_berisi(id_wo, teks):
    db = SessionLocal()
    try:
        keterangan = [r.keterangan or "" for r in db.query(RiwayatStatus).filter_by(id_work_order=id_wo).all()]
        assert any(teks in k for k in keterangan), keterangan
        # the recompute is recorded on the inspection entry: no extra status row
        assert sum(1 for r in db.query(RiwayatStatus).filter_by(id_work_order=id_wo, status="Terinspeksi")) == 1
    finally:
        db.close()


@then(parsers.parse('the priority badge of "{id_wo}" on the Dashboard uses the colour of priority "{prioritas}"'))
def warna_dashboard(ctx, id_wo, prioritas):
    b = ctx["browser"]
    b.get(f"{ctx['base']}/Dashboard")
    lencana = b.find_element(By.XPATH, f"//tr[@data-tiket='{id_wo}']//span[contains(@class,'lencana-prioritas')]")
    assert lencana.get_attribute("data-prioritas") == prioritas
    warna = re.findall(r"\d+", lencana.value_of_css_property("background-color"))[:3]
    assert tuple(int(x) for x in warna) == _rgb(warna_prioritas(prioritas))
    assert _wo(id_wo)["warna_marker"] == warna_prioritas(prioritas)  # same colour as the map marker


@then("the system aborts saving the inspection data")
def batal(ctx):
    db = SessionLocal()
    try:
        assert db.query(Inspeksi).filter_by(id_work_order=ctx["id_wo"]).count() == 0
    finally:
        db.close()
    assert ctx["alur"]["status"](ctx["id_laporan"]) == ctx["status_awal"]


@then(parsers.parse('the system displays a warning message "{pesan}"'))
def peringatan(ctx, pesan):
    assert ctx["browser"].find_element(By.ID, "pesanSistem").text.strip() == pesan


@then(parsers.parse('the ticket "{id_wo}" still has Risk Score "{skor}" with priority "{prioritas}"'))
def risk_score_tetap(id_wo, skor, prioritas):
    wo = _wo(id_wo)
    assert (wo["risk_score"], wo["prioritas"], wo["severity_kasus"]) == (float(skor), prioritas, wo["severity_ai"])


# ------------------------------------------- Bagian 1B: closing recommendation (Outline)
@when(parsers.parse('the road inspector selects recommendation "{rekomendasi}" with reason "{alasan}"'))
def pilih_rekomendasi_tutup(ctx, pilih_opsi, rekomendasi, alasan):
    pilih_opsi("rekomendasi", rekomendasi)
    ctx["browser"].execute_script("tampilkanAlasanTutup();")  # what the select's onchange does
    pilih_opsi("alasan_rekomendasi", alasan)
    ctx["alasan"] = alasan


@when(parsers.parse('the road inspector uploads survey photo "{foto}" and clicks the "{tombol}" button'))
def unggah_dan_simpan(ctx, foto_uji, klik_dan_tunggu, foto, tombol):
    b = ctx["browser"]
    b.find_element(By.ID, "foto_survei").send_keys(foto_uji(foto))
    el = b.find_element(By.ID, TOMBOL[tombol])
    assert el.text.strip() == tombol
    klik_dan_tunggu(el)


@then(parsers.parse('the inspection result is "{hasil}"'))
def hasil_inspeksi(ctx, hasil):
    b = ctx["browser"]
    db = SessionLocal()
    try:
        wo = db.get(WorkOrder, ctx["id_wo"])
        inspeksi = db.query(Inspeksi).filter_by(id_work_order=ctx["id_wo"]).all()
        if hasil == "Terinspeksi":
            # "Tidak ditemukan kerusakan": saved without a damage level, Risk Score not recalculated
            assert wo.status_work_order == "Terinspeksi" and len(inspeksi) == 1
            ins = inspeksi[0]
            assert (ins.rekomendasi_tutup, ins.alasan_rekomendasi, ins.tingkat_kerusakan, ins.severity_lapangan) == (
                True, ctx["alasan"], None, None)
            assert "Hasil inspeksi berhasil disimpan" in b.page_source
            assert any("Risk Score tidak dihitung ulang" in (r.keterangan or "")
                       for r in db.query(RiwayatStatus).filter_by(id_work_order=ctx["id_wo"], status="Terinspeksi"))
        else:
            # any other closing reason still needs the damage level
            assert wo.status_work_order == ctx["status_awal"] and inspeksi == []
            assert b.find_element(By.ID, "pesanSistem").text.strip() == hasil
    finally:
        db.close()
