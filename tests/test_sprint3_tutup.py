"""
Fast tests (no browser) for Sprint 3 Bagian 1B:
  * PRD 5.3 BR-4/BR-5: final status "Ditutup" with a mandatory reason (Tolak at verification, or the
    inspector's closing recommendation confirmed by the Admin), and Ditutup kept out of every count
    of active / completed tickets;
  * PRD 5.3 BR-1: the AI never rejects a report; a valid photo it cannot classify goes to manual review.
"""
import csv
import io
import types
from urllib.parse import unquote

import pytest
from sqlalchemy import create_engine, inspect, text

from app.controllers.kontrol_dashboard import WARNA_DITUTUP, KontrolDashboard, warna_marker
from app.controllers.kontrol_inspeksi import KontrolInspeksi
from app.controllers.kontrol_lacak import PESAN_RATING_DITUTUP, KontrolLacak
from app.controllers.kontrol_laporan_kinerja import KontrolLaporanKinerja
from app.controllers.kontrol_master_data import KontrolMasterData
from app.controllers.kontrol_pelaporan import PESAN_PILIH_KATEGORI, KontrolPelaporan
from app.controllers.kontrol_penanganan import (
    PESAN_REKOMENDASI_TERTUNDA, PESAN_TANPA_REKOMENDASI, KontrolPenanganan,
)
from app.controllers.kontrol_penugasan import KontrolPenugasan
from app.controllers.kontrol_verifikasi import (
    AKSI_INSPEKSI, AKSI_SETUJUI, AKSI_TANPA_INSPEKSI, AKSI_TOLAK, PESAN_ALASAN_WAJIB, alasan_ditolak,
)
from app.database import SessionLocal, pastikan_kolom_terbaru
from app.models.entities import Inspeksi, Laporan, Notifikasi, Rating, RiwayatStatus, WorkOrder
from app.services import alur_status
from app.services.ai_service import AIService, VisiSimulasi, VisiYolo
from app.services.alur_status import (
    ALASAN_TUTUP, DITUTUP, TRANSISI_SAH, AlasanTutupTidakSah, TransisiTidakSah, boleh_transisi, ubah_status,
)
from tests.test_sprint2 import (  # noqa: F401 (db_bersih is a fixture)
    ADMIN, KABID, PENILIK, WARGA, WARGA_LAIN, ambil, db_bersih, hitung, jpeg, klien,
)

WO_JELAS = "REP-2026-00341"     # LAP-2026-0001, USR-01, 8.4 Urgent (seed: Disetujui)
WO_TUGAS = "REP-2026-00298"     # LAP-2026-0002, USR-03, Ditugaskan to PNL-01, 8.0 Urgent
WO_AMBIGU = "REP-2026-00355"    # Dilaporkan, 5.1 Borderline, no citizen report
ALASAN = "Laporan tidak valid"


def ke_dilaporkan(id_wo=WO_JELAS):
    db = SessionLocal()
    wo = db.get(WorkOrder, id_wo)
    wo.status_work_order = "Dilaporkan"
    for lap in db.query(Laporan).filter_by(id_work_order=id_wo):
        lap.status = "Dilaporkan"
    db.commit()
    db.close()


def tolak(id_wo=WO_JELAS, alasan=ALASAN, akun=ADMIN):
    return klien(akun).post(f"/verifikasi/{id_wo}/reject", data={"alasan_tutup": alasan}, follow_redirects=False)


def inspeksi_tutup(alasan="Sudah diperbaiki pihak lain", tingkat="", id_wo=WO_TUGAS, **ubah):
    data = {"rekomendasi": "Rekomendasikan Tutup", "alasan_rekomendasi": alasan, "tingkat_kerusakan": tingkat,
            "catatan_teknis": "dicek di lokasi"}
    data.update(ubah)
    return klien(PENILIK).post(f"/TugasLapangan/{id_wo}/inspeksi", data=data)


def notif_tutup(id_warga):
    db = SessionLocal()
    try:
        return [n.pesan for n in db.query(Notifikasi).filter_by(id_warga=id_warga, judul="Laporan ditutup")]
    finally:
        db.close()


def keterangan_riwayat(id_wo):
    db = SessionLocal()
    try:
        return [r.keterangan or "" for r in db.query(RiwayatStatus).filter_by(id_work_order=id_wo)]
    finally:
        db.close()


# ------------------------------------------------------------- status flow
def test_alasan_tutup_satu_sumber():
    assert ALASAN_TUTUP == ("Tidak ditemukan kerusakan", "Laporan tidak valid",
                            "Sudah diperbaiki pihak lain", "Di luar kewenangan DPUPR")
    assert alur_status.STATUS_FINAL == ("Selesai", "Ditutup")


def test_transisi_ke_ditutup_hanya_dari_dilaporkan_dan_terinspeksi():
    asal_sah = {dari for dari, ke in TRANSISI_SAH.items() if DITUTUP in ke}
    assert asal_sah == {"Dilaporkan", "Terinspeksi"}
    for dari in TRANSISI_SAH:
        assert boleh_transisi(dari, DITUTUP) is (dari in asal_sah or dari == DITUTUP)


def test_ditutup_final_tanpa_transisi_keluar():
    assert TRANSISI_SAH[DITUTUP] == set()
    for ke in TRANSISI_SAH:
        if ke != DITUTUP:
            assert not boleh_transisi(DITUTUP, ke), ke
    wo = types.SimpleNamespace(id_work_order="X", status_work_order=DITUTUP)
    with pytest.raises(TransisiTidakSah):
        ubah_status(None, wo, "Disetujui")


@pytest.mark.parametrize("alasan", ["", "  ", "Malas", "laporan tidak valid"])
def test_tutup_tiket_menolak_alasan_di_luar_daftar(db_bersih, alasan):
    ke_dilaporkan()
    db = SessionLocal()
    with pytest.raises(AlasanTutupTidakSah):
        alur_status.tutup_tiket(db, db.get(WorkOrder, WO_JELAS), alasan, ADMIN)
    db.rollback()
    db.close()
    assert ambil(WorkOrder, WO_JELAS).status_work_order == "Dilaporkan"


# ------------------------------------------------- door (a): Verifikasi
@pytest.mark.parametrize("id_wo, siapkan", [(WO_JELAS, True), (WO_AMBIGU, False)])
def test_tolak_untuk_skor_jelas_dan_ambigu(db_bersih, id_wo, siapkan):
    if siapkan:
        ke_dilaporkan()
    assert alasan_ditolak(ambil(WorkOrder, id_wo), AKSI_TOLAK) is None
    r = tolak(id_wo)
    assert r.status_code == 303 and "jenis=gagal" not in r.headers["location"]
    wo = ambil(WorkOrder, id_wo)
    assert (wo.status_work_order, wo.alasan_tutup, wo.ditutup_oleh) == (DITUTUP, ALASAN, ADMIN)
    assert wo.tanggal_ditutup is not None
    assert f"Ditutup: {ALASAN}" in keterangan_riwayat(id_wo)


@pytest.mark.parametrize("alasan", ["", "Malas"])
def test_tolak_tanpa_alasan_sah_ditolak(db_bersih, alasan):
    ke_dilaporkan()
    r = tolak(alasan=alasan)
    assert "jenis=gagal" in r.headers["location"]
    assert PESAN_ALASAN_WAJIB in unquote(r.headers["location"])
    html = klien(ADMIN).get(r.headers["location"]).text
    assert 'id="pesanVerifikasi"' in html and 'data-jenis="gagal"' in html
    assert ambil(WorkOrder, WO_JELAS).status_work_order == "Dilaporkan"
    assert notif_tutup("USR-01") == []


def test_tolak_hanya_untuk_tiket_dilaporkan(db_bersih):
    r = tolak()  # seed: Disetujui
    assert "keputusan verifikasi sudah tidak dapat diubah" in unquote(r.headers["location"])
    assert ambil(WorkOrder, WO_JELAS).status_work_order == "Disetujui"


def test_tombol_tolak_dan_alasan_tampil_di_verifikasi(db_bersih):
    ke_dilaporkan()
    html = klien(ADMIN).get(f"/verifikasi?ticket_id={WO_JELAS}").text
    assert 'id="tombolTolak"' in html and 'id="tombolTutupTiket"' in html
    for a in ALASAN_TUTUP:
        assert f'<option value="{a}">{a}</option>' in html
    assert 'id="tombolTolak"' not in klien(KABID).get(f"/verifikasi?ticket_id={WO_JELAS}").text
    assert 'id="tombolTolak"' not in klien(ADMIN).get("/verifikasi?ticket_id=REP-2026-00360").text  # Disetujui


@pytest.mark.parametrize("akun, kode", [(KABID, 403), (WARGA, 403), (PENILIK, 403)])
def test_rbac_tolak(db_bersih, akun, kode):
    ke_dilaporkan()
    assert tolak(akun=akun).status_code == kode
    assert ambil(WorkOrder, WO_JELAS).status_work_order == "Dilaporkan"


def test_tolak_tanpa_login_dialihkan(db_bersih):
    r = klien().post(f"/verifikasi/{WO_JELAS}/reject", data={"alasan_tutup": ALASAN}, follow_redirects=False)
    assert r.headers["location"] == "/Login"


def test_notifikasi_tutup_memuat_alasan_satu_per_warga(db_bersih):
    # two reports of USR-01 and one of USR-03 merged into the same ticket
    db = SessionLocal()
    for id_warga in ("USR-01", "USR-03"):
        hasil = KontrolPelaporan(db).kirim_laporan(
            filename="jalan_berlubang_kertajaya.jpg", file_size_mb=1.0, lokasi_jalan="Jl. Raya Kertajaya No. 50",
            deskripsi="Lubang di jalur kiri Kertajaya", kategori_pilihan="Jalan Berlubang",
            latitude=-7.27971, longitude=112.76181, id_warga=id_warga)
        assert hasil["is_duplicate"] and hasil["ticket_id"] == WO_JELAS
    db.close()
    ke_dilaporkan()
    tolak()
    assert len(notif_tutup("USR-01")) == 1 and len(notif_tutup("USR-03")) == 1
    assert ALASAN in notif_tutup("USR-01")[0]


# ------------------------------------------------- door (b): inspection
def test_rekomendasi_tutup_tidak_ditemukan_kerusakan_tanpa_tingkat(db_bersih):
    r = inspeksi_tutup("Tidak ditemukan kerusakan", tingkat="")
    assert "Hasil inspeksi berhasil disimpan" in r.text
    wo = ambil(WorkOrder, WO_TUGAS)
    assert (wo.status_work_order, wo.risk_score, wo.prioritas, wo.severity_score_kasus) == ("Terinspeksi", 8.0, "Urgent", 8.0)
    db = SessionLocal()
    ins = db.query(Inspeksi).filter_by(id_work_order=WO_TUGAS).one()
    assert (ins.rekomendasi_tutup, ins.alasan_rekomendasi, ins.tingkat_kerusakan, ins.dimensi_kerusakan) == (
        True, "Tidak ditemukan kerusakan", None, None)
    assert db.get(WorkOrder, WO_TUGAS).rekomendasi_tutup_tertunda.id_inspeksi == ins.id_inspeksi
    db.close()


@pytest.mark.parametrize("alasan", [a for a in ALASAN_TUTUP if a != "Tidak ditemukan kerusakan"])
def test_rekomendasi_tutup_alasan_lain_wajib_tingkat(db_bersih, alasan):
    r = inspeksi_tutup(alasan, tingkat="")
    assert "Pilih tingkat kerusakan hasil inspeksi lapangan" in r.text
    assert ambil(WorkOrder, WO_TUGAS).status_work_order == "Ditugaskan"
    r = inspeksi_tutup(alasan, tingkat="Ringan")  # with the level it is saved and recalculated
    assert "Hasil inspeksi berhasil disimpan" in r.text
    assert ambil(WorkOrder, WO_TUGAS).risk_score == 5.5


def test_rekomendasi_tutup_tanpa_alasan_ditolak(db_bersih):
    r = inspeksi_tutup("", tingkat="Ringan")
    assert "Pilih alasan rekomendasi tutup tiket" in r.text
    assert hitung(Inspeksi, id_work_order=WO_TUGAS) == 0


def test_penilik_hanya_tiket_yang_ditugaskan_kepadanya(db_bersih):
    r = inspeksi_tutup("Tidak ditemukan kerusakan", id_wo="REP-2026-00360")  # Benowo, not assigned
    assert r.status_code == 404
    assert ambil(WorkOrder, "REP-2026-00360").status_work_order == "Disetujui"


def test_spk_ditahan_selama_rekomendasi_tertunda(db_bersih):
    inspeksi_tutup("Tidak ditemukan kerusakan")
    html = klien(ADMIN).get(f"/work-orders?select_ticket={WO_TUGAS}").text
    assert 'id="panelRekomendasiTutup"' in html and 'id="terbitkanSpk"' not in html
    assert "Rekomendasi penilik: tutup tiket (Tidak ditemukan kerusakan)" in html
    r = klien(ADMIN).post(f"/work-orders/{WO_TUGAS}/spk", data={"nomor_spk": "SPK/X/1", "tim_pelaksana": "Satgas"})
    assert PESAN_REKOMENDASI_TERTUNDA in r.text  # flash shown on the page the POST redirects to
    assert ambil(WorkOrder, WO_TUGAS).status_work_order == "Terinspeksi" and ambil(WorkOrder, WO_TUGAS).nomor_spk is None


def test_tolak_rekomendasi_lalu_spk_boleh(db_bersih):
    inspeksi_tutup("Tidak ditemukan kerusakan")
    klien(ADMIN).post(f"/work-orders/{WO_TUGAS}/rekomendasi-tutup/tolak")
    wo = ambil(WorkOrder, WO_TUGAS)
    assert wo.status_work_order == "Terinspeksi"
    assert any("Rekomendasi tutup ditolak Admin" in k for k in keterangan_riwayat(WO_TUGAS))
    db = SessionLocal()
    assert db.query(Inspeksi).filter_by(id_work_order=WO_TUGAS).one().keputusan_rekomendasi == "Ditolak"
    db.close()
    assert 'id="terbitkanSpk"' in klien(ADMIN).get(f"/work-orders?select_ticket={WO_TUGAS}").text
    klien(ADMIN).post(f"/work-orders/{WO_TUGAS}/spk", data={"nomor_spk": "SPK/X/2", "tim_pelaksana": "Satgas"})
    assert ambil(WorkOrder, WO_TUGAS).status_work_order == "Dalam Proses"


def test_konfirmasi_tutup_dan_tidak_bisa_diulang(db_bersih):
    inspeksi_tutup("Sudah diperbaiki pihak lain", tingkat="Ringan")
    klien(ADMIN).post(f"/work-orders/{WO_TUGAS}/rekomendasi-tutup/konfirmasi")
    wo = ambil(WorkOrder, WO_TUGAS)
    assert (wo.status_work_order, wo.alasan_tutup) == (DITUTUP, "Sudah diperbaiki pihak lain")
    assert len(notif_tutup("USR-03")) == 1 and "Sudah diperbaiki pihak lain" in notif_tutup("USR-03")[0]
    db = SessionLocal()
    hasil = KontrolPenanganan(db).konfirmasi_tutup(WO_TUGAS, ADMIN)
    assert hasil == {"success": False, "message": PESAN_TANPA_REKOMENDASI}
    assert KontrolPenanganan(db).tolak_rekomendasi(WO_TUGAS, ADMIN)["success"] is False
    db.close()


def test_keputusan_tanpa_rekomendasi_ditolak(db_bersih):
    klien(PENILIK).post(f"/TugasLapangan/{WO_TUGAS}/inspeksi", data={
        "dimensi_kerusakan": "1m", "rekomendasi": "Tambal Hotmix", "tingkat_kerusakan": "Berat"})
    db = SessionLocal()
    assert KontrolPenanganan(db).konfirmasi_tutup(WO_TUGAS, ADMIN)["message"] == PESAN_TANPA_REKOMENDASI
    db.close()
    assert ambil(WorkOrder, WO_TUGAS).status_work_order == "Terinspeksi"


@pytest.mark.parametrize("aksi", ["konfirmasi", "tolak"])
@pytest.mark.parametrize("akun", [KABID, PENILIK, WARGA])
def test_rbac_keputusan_rekomendasi(db_bersih, aksi, akun):
    inspeksi_tutup("Tidak ditemukan kerusakan")
    assert klien(akun).post(f"/work-orders/{WO_TUGAS}/rekomendasi-tutup/{aksi}").status_code == 403
    assert ambil(WorkOrder, WO_TUGAS).status_work_order == "Terinspeksi"


# --------------------------------------------- Ditutup is final everywhere
def _tutup_00341():
    ke_dilaporkan()
    tolak()


def test_ditutup_bukan_kandidat_deduplikasi(db_bersih):
    _tutup_00341()
    db = SessionLocal()
    hasil = KontrolPelaporan(db).kirim_laporan(
        filename="jalan_berlubang_kertajaya.jpg", file_size_mb=1.0, lokasi_jalan="Jl. Raya Kertajaya No. 50",
        deskripsi="Lubang di jalur kiri Kertajaya", kategori_pilihan="Jalan Berlubang",
        latitude=-7.27971, longitude=112.76181, id_warga="USR-03")
    db.close()
    assert hasil["success"] and not hasil["is_duplicate"] and hasil["ticket_id"] != WO_JELAS


def test_ditutup_tidak_bisa_dirating_dan_tampil_di_lacak(db_bersih):
    _tutup_00341()
    db = SessionLocal()
    assert KontrolLacak(db).simpan_rating("LAP-2026-0001", "USR-01", 5)["message"] == PESAN_RATING_DITUTUP
    detail = KontrolLacak(db).detail_lacak("LAP-2026-0001", "USR-01")
    db.close()
    assert detail["boleh_rating"] is False and detail["ditutup"] and detail["alasan_tutup"] == ALASAN
    assert detail["tahapan"][-1] == {"label": f"Ditutup: {ALASAN}", "selesai": True, "ditutup": True}
    assert all(t["selesai"] for t in detail["tahapan"])  # repair stages that never happened are not listed
    html = klien(WARGA).get("/lacak?id=LAP-2026-0001").text
    assert 'id="alasanDitutup"' in html and 'id="formRating"' not in html and "tahap-ditutup" in html
    klien(WARGA).post("/lacak/LAP-2026-0001/rating", data={"nilai_bintang": "5"})
    assert hitung(Rating, id_laporan="LAP-2026-0001") == 0


def test_kpi_dashboard_dan_work_order_tanpa_ditutup(db_bersih):
    _tutup_00341()
    db = SessionLocal()
    semua = db.query(WorkOrder).all()
    kpi = KontrolDashboard.ringkasan_kpi(semua)
    assert (kpi["total"], kpi["aktif"], kpi["selesai"], kpi["ditutup"]) == (5, 3, 1, 1)
    assert kpi["persen_selesai"] == 25.0  # 1 Selesai of the 4 tickets that are not Ditutup
    wo_kpi = KontrolPenugasan.ringkasan_kpi(semua)
    assert (wo_kpi["selesai"], wo_kpi["ditutup"], wo_kpi["lainnya"]) == (1, 1, 0)
    assert sum(v for k, v in wo_kpi.items() if k != "total") == wo_kpi["total"]
    assert warna_marker(db.get(WorkOrder, WO_JELAS)) == WARNA_DITUTUP
    db.close()
    html = klien(ADMIN).get("/Dashboard").text
    assert 'id="kartuDitutup">1<' in html and 'id="kartuAktif">3<' in html
    assert 'id="kartuDitutupWo">1<' in klien(ADMIN).get("/work-orders").text


def test_beban_penilik_tidak_menghitung_ditutup(db_bersih):
    db = SessionLocal()
    sebelum = {r["p"].id_penilik: r["beban_aktif"] for r in KontrolMasterData(db).muat()["penilik"]}["PNL-01"]
    db.close()
    inspeksi_tutup("Tidak ditemukan kerusakan")
    klien(ADMIN).post(f"/work-orders/{WO_TUGAS}/rekomendasi-tutup/konfirmasi")
    db = SessionLocal()
    data = KontrolMasterData(db).muat()
    tugas = KontrolInspeksi(db).daftar_tugas("PNL-01")
    db.close()
    assert WO_TUGAS in [w.id_work_order for w in tugas["riwayat"]]
    assert WO_TUGAS not in [w.id_work_order for k in ("inspeksi", "menunggu_spk", "perbaikan") for w in tugas[k]]
    beban = {r["p"].id_penilik: r["beban_aktif"] for r in data["penilik"]}["PNL-01"]
    assert beban == sebelum - 1  # the closed ticket is no longer the inspector's active workload


def test_laporan_kinerja_memisahkan_ditutup(db_bersih):
    _tutup_00341()
    db = SessionLocal()
    k = KontrolLaporanKinerja(db)
    data = k.rekap("2026-10-01", "2026-10-31")
    assert data["total"]["total"] == 4 and data["total"]["selesai"] == 1
    assert data["total"]["tingkat_penyelesaian"] == 25.0
    assert WO_JELAS not in [b["id_work_order"] for b in data["tiket"]]
    urgent = next(p for p in data["per_prioritas"] if p["prioritas"] == "Urgent")
    assert urgent["total"] == 1
    assert data["ditutup"]["jumlah"] == 1
    assert {r["alasan"]: r["jumlah"] for r in data["ditutup"]["per_alasan"]}[ALASAN] == 1
    gubeng = next(r for r in data["per_wilayah"] if r["nama_wilayah"] == "Wilayah Gubeng")
    assert (gubeng["total"], gubeng["jumlah_ditutup"]) == (3, 1)
    baris_csv = list(csv.reader(io.StringIO(k.csv_per_wilayah(data).lstrip("﻿"))))
    kolom = baris_csv[0].index("Ditutup (tidak dihitung)")
    assert {b[0]: b[kolom] for b in baris_csv[1:]}["Wilayah Gubeng"] == "1"
    assert WO_JELAS not in k.csv_per_tiket(data)
    db.close()
    html = klien(KABID).get("/laporan-kinerja?tanggal_mulai=2026-10-01&tanggal_akhir=2026-10-31").text
    assert 'id="ringkasanDitutup"' in html and f'data-alasan="{ALASAN}"' in html


def test_laporan_kinerja_hanya_tiket_ditutup_bukan_periode_kosong(db_bersih):
    _tutup_00341()
    db = SessionLocal()
    for r in db.query(RiwayatStatus).filter_by(id_work_order=WO_JELAS):
        r.waktu = r.waktu.replace(year=2025, month=3)
    db.commit()
    data = KontrolLaporanKinerja(db).rekap("2025-03-01", "2025-03-31")
    db.close()
    assert data["message"] is None and data["tiket"] == [] and data["ditutup"]["jumlah"] == 1


# ----------------------------------------------- BR-1: manual review
def _ai_yolo_tanpa_deteksi():
    from tests.test_keamanan_dan_logika import KONFIG_V4, NAMA_V4, _FakeYoloV4
    lemah = _FakeYoloV4([(0, 0.10, [0.5, 0.5, 0.3, 0.3])], NAMA_V4)  # below every class threshold
    return AIService(visi=VisiYolo(model=lemah, config=KONFIG_V4))


@pytest.mark.parametrize("nama", ["kucing.jpg", "selfie_di_jalan.jpg", "tanpa_deteksi_jl_kenjeran.jpg"])
def test_simulasi_tidak_pernah_menolak_foto_valid(nama):
    h = VisiSimulasi().analisis(nama, jpeg())
    assert (h.detected, h.tinjauan_manual, h.rekomendasi_kategori, h.kotak) == (False, True, None, [])
    assert h.message.startswith("Perlu tinjauan manual")


def test_yolov8_tanpa_deteksi_jadi_tinjauan_manual():
    ai = _ai_yolo_tanpa_deteksi()
    h = ai.analisis_foto("jalan.jpg", jpeg())
    assert (h.detected, h.tinjauan_manual, h.sumber) == (False, True, "yolov8")
    tanpa_bytes = ai.analisis_foto("jalan.jpg", None)
    assert tanpa_bytes.detected is False and tanpa_bytes.tinjauan_manual is False  # no photo: still an error


@pytest.mark.parametrize("pakai_yolo", [False, True])
def test_laporan_tinjauan_manual_diterima_di_kedua_mode(db_bersih, pakai_yolo):
    db = SessionLocal()
    ai = _ai_yolo_tanpa_deteksi() if pakai_yolo else AIService(visi=VisiSimulasi())
    hasil = KontrolPelaporan(db, ai=ai).kirim_laporan(
        filename="kucing.jpg", file_size_mb=0.1, lokasi_jalan="Jl. Kenjeran No. 210", deskripsi="Aspal rusak di depan pasar",
        kategori_pilihan="Retak Permukaan", latitude=-7.2440, longitude=112.7960, foto_bytes=jpeg())
    assert hasil["success"] and hasil["perlu_tinjauan_manual"] and hasil["status_work_order"] == "Dilaporkan"
    lap = db.get(Laporan, hasil["id_laporan"])
    wo = db.get(WorkOrder, hasil["ticket_id"])
    assert lap.perlu_tinjauan_manual is True and lap.kotak_deteksi is None
    assert (wo.kategori_kerusakan, wo.severity_score_kasus, wo.severity_ai) == ("Retak Permukaan", 4.5, 4.5)
    assert wo.perlu_tinjauan_manual is True
    db.close()


def test_tinjauan_manual_wajib_pilih_kategori(db_bersih):
    db = SessionLocal()
    hasil = KontrolPelaporan(db).kirim_laporan(
        filename="tanpa_deteksi.jpg", file_size_mb=0.1, lokasi_jalan="Jl. Kenjeran No. 210",
        deskripsi="Aspal rusak di depan pasar", latitude=-7.2440, longitude=112.7960)
    db.close()
    assert hasil == {"success": False, "step": 3, "message": PESAN_PILIH_KATEGORI}


def test_api_analisis_foto_tinjauan_manual_tanpa_error(db_bersih):
    r = klien(WARGA).post("/api/analisis-foto", files={"foto": ("kucing.jpg", jpeg(), "image/jpeg")})
    h = r.json()
    assert r.status_code == 200 and h["valid"] and not h["detected"] and h["tinjauan_manual"]
    assert h["message"].startswith("Perlu tinjauan manual") and h["kategori"] is None
    tidak_valid = klien(WARGA).post("/api/analisis-foto", files={"foto": ("x.jpg", b"%PDF", "image/jpeg")}).json()
    assert not tidak_valid["valid"] and "Format harus JPG/PNG" in tidak_valid["message"]


def _tiket_manual(kategori="Jalan Berlubang"):
    db = SessionLocal()
    hasil = KontrolPelaporan(db).kirim_laporan(
        filename="tanpa_deteksi_kenjeran.jpg", file_size_mb=0.1, lokasi_jalan="Jl. Kenjeran No. 100",
        deskripsi="Aspal mengelupas di depan pasar", kategori_pilihan=kategori,
        latitude=-7.2471, longitude=112.7972, foto_bytes=jpeg())
    db.close()
    return hasil["ticket_id"]


def test_tinjauan_manual_diperlakukan_seperti_skor_ambigu(db_bersih):
    id_wo = _tiket_manual()
    db = SessionLocal()
    wo = db.get(WorkOrder, id_wo)
    assert wo.risk_score == 6.5  # a clear score on its own...
    assert alasan_ditolak(wo, AKSI_SETUJUI) and "perlu tinjauan manual" in alasan_ditolak(wo, AKSI_SETUJUI)
    assert alasan_ditolak(wo, AKSI_INSPEKSI) is None and alasan_ditolak(wo, AKSI_TANPA_INSPEKSI) is None
    assert alasan_ditolak(wo, AKSI_TOLAK) is None
    assert alasan_ditolak(wo, "hapus") == "Aksi verifikasi tidak dikenal."
    db.close()
    html = klien(ADMIN).get(f"/verifikasi?ticket_id={id_wo}").text
    assert "Perlu Tinjauan Manual" in html and f"/verifikasi/{id_wo}/approve" not in html
    assert f"/verifikasi/{id_wo}/skip-inspection" in html and 'id="tombolTolak"' in html
    klien(ADMIN).post(f"/verifikasi/{id_wo}/approve")
    klien(ADMIN).post(f"/Dashboard/{id_wo}/quick-approve")
    assert ambil(WorkOrder, id_wo).status_work_order == "Dilaporkan"
    dash = klien(ADMIN).get("/Dashboard").text
    assert f'action="/Dashboard/{id_wo}/quick-approve"' not in dash and "label-tinjauan-manual" in dash
    klien(ADMIN).post(f"/verifikasi/{id_wo}/skip-inspection")
    assert ambil(WorkOrder, id_wo).status_work_order == "Disetujui"


def test_laporan_terdeteksi_digabung_mengakhiri_tinjauan_manual(db_bersih):
    id_wo = _tiket_manual()
    db = SessionLocal()
    hasil = KontrolPelaporan(db).kirim_laporan(
        filename="jalan_berlubang_kenjeran.jpg", file_size_mb=0.1, lokasi_jalan="Jl. Kenjeran No. 100",
        deskripsi="Lubang di depan pasar Kenjeran", kategori_pilihan="Jalan Berlubang",
        latitude=-7.24712, longitude=112.79721, id_warga="USR-03")
    assert hasil["is_duplicate"] and hasil["ticket_id"] == id_wo
    assert db.get(WorkOrder, id_wo).perlu_tinjauan_manual is False  # the AI now recognised the damage
    db.close()


# ------------------------------------------------------------ old database
def test_database_lama_mendapat_kolom_bagian_1b(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'lama.db'}")
    with eng.begin() as conn:
        for tabel in ("work_order", "laporan", "inspeksi"):
            conn.execute(text(f"CREATE TABLE {tabel} (id VARCHAR(20) PRIMARY KEY)"))
    pastikan_kolom_terbaru(eng)
    kolom = {t: {c["name"] for c in inspect(eng).get_columns(t)} for t in ("work_order", "laporan", "inspeksi")}
    assert {"alasan_tutup", "ditutup_oleh", "tanggal_ditutup"} <= kolom["work_order"]
    assert "perlu_tinjauan_manual" in kolom["laporan"]
    assert {"rekomendasi_tutup", "alasan_rekomendasi", "keputusan_rekomendasi", "diputuskan_oleh"} <= kolom["inspeksi"]
