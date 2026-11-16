"""
Regression tests for the pre-Sprint-3 audit (audit_sprint2.md), one or more per finding.
Each test failed on commit e5003cd (before the fix) and passes after it.

Business decisions applied (approved):
  A-07  ambiguous score in Verifikasi = 4.0 <= skor < 6.0 (BR-2 Borderline); 6.0 is a clear (Tinggi) score.
  A-10  an inspector only inspects tickets assigned to them (Ditugaskan, or Menunggu Inspeksi with their ID).
  B-04  one rating per (citizen, ticket); Laporan Kinerja averages one rating per unique citizen.
"""
import ast
import io
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.services.penyimpanan as modul_penyimpanan
from app.controllers.kontrol_master_data import STATUS_KETERSEDIAAN, KontrolMasterData
from app.database import SessionLocal
from app.main import app
from app.models.entities import Laporan, Notifikasi, PenilikJalan, Rating, RiwayatStatus, WorkOrder
from database.seed import seed_data

ROOT = Path(__file__).resolve().parents[1]
WARGA = "0812xxxxxxx"          # USR-01
ADMIN = "admin@dpupr.surabaya.go.id"
KABID = "kabid@dpupr.surabaya.go.id"
PENILIK = "budi.santoso@dpupr.surabaya.go.id"   # PNL-01, WIL-01
WO_DISETUJUI = "REP-2026-00341"   # Disetujui, no inspector, risk 8.4
WO_AMBIGU = "REP-2026-00355"      # Dilaporkan, risk 5.1 (Borderline)
WO_DITUGASKAN = "REP-2026-00298"  # Ditugaskan to PNL-01
WO_SELESAI = "REP-2026-00290"     # Selesai, LAP-2026-0003 of USR-01


def jpeg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (40, 30), (90, 90, 90)).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture
def db_bersih(tmp_path, monkeypatch):
    seed_data(verbose=False)
    monkeypatch.setattr(modul_penyimpanan, "DIREKTORI_UNGGAHAN", tmp_path)


def klien(identifier=None, password="password123") -> TestClient:
    c = TestClient(app)
    if identifier:
        r = c.post("/Login", data={"identifier": identifier, "password": password}, follow_redirects=False)
        assert r.status_code == 303, r.text[:300]
    return c


def ambil(model, kunci):
    db = SessionLocal()
    try:
        return db.get(model, kunci)
    finally:
        db.close()


def hitung(model, **filter_):
    db = SessionLocal()
    try:
        return db.query(model).filter_by(**filter_).count()
    finally:
        db.close()


def status(id_wo):
    return ambil(WorkOrder, id_wo).status_work_order


def ubah_wo(id_wo, **kolom):
    db = SessionLocal()
    wo = db.get(WorkOrder, id_wo)
    for k, v in kolom.items():
        setattr(wo, k, v)
    db.commit()
    db.close()


def penilik_baru(nip: str, nama: str, wilayah: str = "WIL-01") -> tuple[str, str]:
    """Add an inspector through UC-D; returns (id_penilik, temporary password)."""
    db = SessionLocal()
    hasil = KontrolMasterData(db).tambah_penilik(nip, nama, wilayah)
    db.close()
    assert hasil["success"], hasil["message"]
    id_p = SessionLocal().query(PenilikJalan).filter_by(nip=nip).one().id_penilik
    return id_p, hasil["akun_baru"]["sandi_sementara"]


def lapor(c, nama_foto="foto_jalan.jpg", lat="-7.30001", lng="112.70001", deskripsi="Lubang besar baru muncul setelah hujan",
          kategori="Jalan Berlubang"):
    return c.post("/lapor", data={"lokasi_jalan": "Jl. Uji Audit No. 999, Surabaya", "latitude": lat, "longitude": lng,
                                  "deskripsi": deskripsi, "kategori_pilihan": kategori, "id_wilayah": "WIL-01"},
                  files={"foto": (nama_foto, jpeg(), "image/jpeg")})


def tiket_terbaru_warga(id_warga="USR-01") -> str:
    db = SessionLocal()
    try:
        return (db.query(Laporan).filter_by(id_warga=id_warga)
                .order_by(Laporan.id_laporan.desc()).first().id_work_order)
    finally:
        db.close()


def angka(html: str, id_elemen: str) -> int:
    m = re.search(rf'id="{id_elemen}"[^>]*>\s*(\d+)', html)
    assert m, f"#{id_elemen} tidak ditemukan"
    return int(m.group(1))


def inspeksi(c, id_wo):
    return c.post(f"/TugasLapangan/{id_wo}/inspeksi",
                  data={"dimensi_kerusakan": "2m x 1m", "catatan_teknis": "aspal terkelupas", "rekomendasi": "Tambal Hotmix"})


# --------------------------------------------------------------------------- #
# A-01: latitude without longitude must not crash the report form (500)
# --------------------------------------------------------------------------- #
def test_a01_latitude_tanpa_longitude_tidak_500(db_bersih):
    r = klien(WARGA).post("/lapor", data={"lokasi_jalan": "Jl. Uji No. 1", "latitude": "-7.25",
                                          "deskripsi": "Lubang besar di tengah jalan", "kategori_pilihan": "Jalan Berlubang",
                                          "id_wilayah": "WIL-01"},
                          files={"foto": ("lubang.jpg", jpeg(), "image/jpeg")})
    assert r.status_code == 200
    assert "latitude dan longitude" in r.text
    assert "Belum dipilih" in r.text  # the incomplete pair is not shown as a coordinate


# --------------------------------------------------------------------------- #
# A-02: Dashboard quick-approve cannot bypass the ambiguous-score decision (BR-2)
# --------------------------------------------------------------------------- #
def test_a02_aksi_cepat_tidak_tampil_untuk_tiket_ambigu(db_bersih):
    html = klien(ADMIN).get("/Dashboard").text
    assert f'action="/Dashboard/{WO_AMBIGU}/quick-approve"' not in html


def test_a02_aksi_cepat_ditolak_backend_untuk_tiket_ambigu(db_bersih):
    r = klien(ADMIN).post(f"/Dashboard/{WO_AMBIGU}/quick-approve")
    assert "tidak diubah" in r.text and "skor ambigu" in r.text
    assert status(WO_AMBIGU) == "Dilaporkan"
    assert hitung(RiwayatStatus, id_work_order=WO_AMBIGU, status="Disetujui") == 0


def test_a02_aksi_cepat_tetap_untuk_tiket_skor_jelas(db_bersih):
    lapor(klien(WARGA))
    tid = tiket_terbaru_warga()
    admin = klien(ADMIN)
    assert f'action="/Dashboard/{tid}/quick-approve"' in admin.get("/Dashboard").text
    r = admin.post(f"/Dashboard/{tid}/quick-approve")
    assert "berhasil diubah menjadi Disetujui" in r.text and status(tid) == "Disetujui"


# --------------------------------------------------------------------------- #
# A-03: Menunggu Inspeksi with an inspector is shown as "already assigned"
# --------------------------------------------------------------------------- #
def _panel(c, id_wo) -> str:
    return c.get(f"/work-orders?select_ticket={id_wo}").text


def test_a03_panel_menunggu_inspeksi_sudah_punya_penilik(db_bersih):
    klien(ADMIN).post(f"/verifikasi/{WO_AMBIGU}/inspect", data={"nama_penilik": "PNL-01"})
    assert status(WO_AMBIGU) == "Menunggu Inspeksi"

    admin = _panel(klien(ADMIN), WO_AMBIGU)
    assert 'id="infoSudahDitugaskan"' in admin and "Sudah ditugaskan kepada <strong>Budi Santoso</strong>" in admin
    assert "Tugaskan Penilik Jalan" not in admin and "Daftar Penilik Jalan Tersedia" not in admin

    penilik = _panel(klien(PENILIK), WO_AMBIGU)
    assert 'id="infoDitugaskanKepadaAnda"' in penilik
    assert f'href="/TugasLapangan/{WO_AMBIGU}"' in penilik
    assert "Hanya Admin (PPK)" not in penilik

    kabid = _panel(klien(KABID), WO_AMBIGU)
    assert "Sudah ditugaskan kepada <strong>Budi Santoso</strong>" in kabid and "Hanya Admin (PPK)" not in kabid


def test_a03_penilik_lain_melihat_info_bukan_teks_hanya_admin(db_bersih):
    _, sandi = penilik_baru("199005122022031005", "Rina Penilik")
    klien(ADMIN).post(f"/verifikasi/{WO_AMBIGU}/inspect", data={"nama_penilik": "PNL-01"})
    html = _panel(klien("199005122022031005", sandi), WO_AMBIGU)
    assert 'id="infoSudahDitugaskan"' in html and 'id="infoDitugaskanKepadaAnda"' not in html


# --------------------------------------------------------------------------- #
# A-04: the inspection's inspector cannot be swapped silently on /verifikasi
# --------------------------------------------------------------------------- #
def test_a04_ganti_penilik_inspeksi_lewat_verifikasi_ditolak(db_bersih):
    id_rina, _ = penilik_baru("199005122022031005", "Rina Penilik")
    admin = klien(ADMIN)
    admin.post(f"/verifikasi/{WO_AMBIGU}/inspect", data={"nama_penilik": "PNL-01"})
    riwayat = hitung(RiwayatStatus, id_work_order=WO_AMBIGU)
    r = admin.post(f"/verifikasi/{WO_AMBIGU}/inspect", data={"nama_penilik": id_rina})
    assert "tidak dapat diubah" in r.text
    assert ambil(WorkOrder, WO_AMBIGU).id_penilik == "PNL-01"
    assert hitung(RiwayatStatus, id_work_order=WO_AMBIGU) == riwayat


def test_a04_ganti_penilik_inspeksi_lewat_work_order_tercatat(db_bersih):
    id_rina, _ = penilik_baru("199005122022031005", "Rina Penilik")
    admin = klien(ADMIN)
    admin.post(f"/verifikasi/{WO_AMBIGU}/inspect", data={"nama_penilik": "PNL-01"})
    ganti = _panel(admin, WO_AMBIGU).split('id="gantiPenilik"', 1)[1].split("</details>", 1)[0]
    assert f'value="{id_rina}"' in ganti and 'value="PNL-01"' not in ganti
    admin.post(f"/work-orders/{WO_AMBIGU}/assign", data={"nama_penilik": id_rina})
    t = ambil(WorkOrder, WO_AMBIGU)
    assert (t.status_work_order, t.id_penilik) == ("Ditugaskan", id_rina)
    assert hitung(RiwayatStatus, id_work_order=WO_AMBIGU, keterangan="Ditugaskan kepada Rina Penilik") == 1
    db = SessionLocal()
    pelapor = {lap.id_warga for lap in db.query(Laporan).filter_by(id_work_order=WO_AMBIGU)}
    notif = (db.query(Notifikasi).join(Laporan, Notifikasi.id_laporan == Laporan.id_laporan)
             .filter(Laporan.id_work_order == WO_AMBIGU, Notifikasi.judul == "Petugas ditugaskan").count())
    db.close()
    assert notif == len(pelapor)
    # the previous inspector no longer has the task
    assert klien(PENILIK).get(f"/TugasLapangan/{WO_AMBIGU}").status_code == 404


def test_a04_penilik_sama_tidak_mengubah_menunggu_inspeksi(db_bersih):
    admin = klien(ADMIN)
    admin.post(f"/verifikasi/{WO_AMBIGU}/inspect", data={"nama_penilik": "PNL-01"})
    riwayat = hitung(RiwayatStatus, id_work_order=WO_AMBIGU)
    admin.post(f"/work-orders/{WO_AMBIGU}/assign", data={"nama_penilik": "PNL-01"})
    assert status(WO_AMBIGU) == "Menunggu Inspeksi"
    assert hitung(RiwayatStatus, id_work_order=WO_AMBIGU) == riwayat


# --------------------------------------------------------------------------- #
# A-05: extra inspection only for an available inspector
# --------------------------------------------------------------------------- #
def test_a05_inspeksi_tambahan_tidak_ke_penilik_cuti(db_bersih):
    id_rina, _ = penilik_baru("199005122022031005", "Rina Penilik")
    admin = klien(ADMIN)
    admin.post(f"/master-data/penilik/{id_rina}/ketersediaan", data={"status": "Cuti"})
    html = admin.get(f"/verifikasi?ticket_id={WO_AMBIGU}").text
    opsi = re.search(rf'<option value="{id_rina}"([^>]*)>([^<]*)<', html)
    assert opsi and "disabled" in opsi.group(1) and "Cuti" in opsi.group(2)
    assert re.search(r'<option value="PNL-01"\s*>[^<]*Tersedia', html)

    r = admin.post(f"/verifikasi/{WO_AMBIGU}/inspect", data={"nama_penilik": id_rina})
    assert "tidak berstatus Tersedia" in r.text
    assert status(WO_AMBIGU) == "Dilaporkan" and ambil(WorkOrder, WO_AMBIGU).id_penilik is None


# --------------------------------------------------------------------------- #
# A-06: "assigned to you" is decided by account ID, not by name
# --------------------------------------------------------------------------- #
def test_a06_penilik_bernama_sama_tidak_dianggap_pemilik_tugas(db_bersih):
    _, sandi = penilik_baru("199005122022031005", "Budi Santoso")   # same name as PNL-01
    kembar = klien("199005122022031005", sandi)
    html = _panel(kembar, WO_DITUGASKAN)
    assert 'id="infoDitugaskanKepadaAnda"' not in html
    assert 'id="infoSudahDitugaskan"' in html
    assert 'id="infoDitugaskanKepadaAnda"' in _panel(klien(PENILIK), WO_DITUGASKAN)


# --------------------------------------------------------------------------- #
# A-07: ambiguous = 4.0 <= score < 6.0; 6.0 is a clear (Tinggi) score
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("skor,ambigu", [(3.9, False), (4.0, True), (5.9, True), (5.99, True), (6.0, False), (8.4, False)])
def test_a07_definisi_skor_ambigu(skor, ambigu):
    from app.services.risk_scoring import klasifikasi_prioritas, skor_ambigu
    assert skor_ambigu(skor) is ambigu
    assert (klasifikasi_prioritas(skor) == "Borderline") is ambigu


def test_a07_skor_enam_diperlakukan_skor_jelas_di_verifikasi(db_bersih):
    ubah_wo(WO_AMBIGU, risk_score=6.0, prioritas="Tinggi")
    admin = klien(ADMIN)
    html = admin.get(f"/verifikasi?ticket_id={WO_AMBIGU}").text
    assert "Siap Disetujui" in html and "Butuh Verifikasi Lapangan" not in html
    assert f'action="/verifikasi/{WO_AMBIGU}/approve"' in html
    assert f'action="/verifikasi/{WO_AMBIGU}/inspect"' not in html
    r = admin.post(f"/verifikasi/{WO_AMBIGU}/skip-inspection")
    assert "skor jelas" in r.text and status(WO_AMBIGU) == "Dilaporkan"
    admin.post(f"/verifikasi/{WO_AMBIGU}/approve")
    assert status(WO_AMBIGU) == "Disetujui"


# --------------------------------------------------------------------------- #
# A-08: an already approved ticket offers no decision buttons and accepts none
# --------------------------------------------------------------------------- #
def test_a08_tiket_disetujui_tanpa_tombol_keputusan(db_bersih):
    html = klien(ADMIN).get(f"/verifikasi?ticket_id={WO_DISETUJUI}").text
    assert f'action="/verifikasi/{WO_DISETUJUI}/approve"' not in html
    assert "keputusan verifikasi sudah tidak dapat diubah" in html


def test_a08_aksi_pada_tiket_disetujui_ditolak_dengan_pesan_jujur(db_bersih):
    admin = klien(ADMIN)
    r = admin.post(f"/verifikasi/{WO_DISETUJUI}/approve")
    assert "tidak dapat disetujui" in r.text and f"Tiket {WO_DISETUJUI} disetujui" not in r.text
    # ambiguous ticket approved without inspection, then "skip" again: log must not be overwritten
    admin.post(f"/verifikasi/{WO_AMBIGU}/skip-inspection")
    ubah_wo(WO_AMBIGU, log_keputusan="Log Keputusan Manual - asli")
    r = admin.post(f"/verifikasi/{WO_AMBIGU}/skip-inspection")
    assert "tidak dapat diubah" in r.text and "Tercatat" not in r.text
    assert ambil(WorkOrder, WO_AMBIGU).log_keputusan == "Log Keputusan Manual - asli"
    html = admin.get(f"/verifikasi?ticket_id={WO_AMBIGU}").text
    assert f'action="/verifikasi/{WO_AMBIGU}/skip-inspection"' not in html


# --------------------------------------------------------------------------- #
# A-09: backend accepts exactly the actions the Verifikasi page offers
# --------------------------------------------------------------------------- #
def test_a09_inspeksi_dari_menunggu_penugasan_ditolak(db_bersih):
    admin = klien(ADMIN)
    admin.post(f"/verifikasi/{WO_AMBIGU}/skip-inspection")              # -> Disetujui
    admin.post("/master-data/penilik/PNL-01/ketersediaan", data={"status": "Cuti"})
    admin.post(f"/work-orders/{WO_AMBIGU}/assign", data={})             # -> Menunggu Penugasan
    assert status(WO_AMBIGU) == "Menunggu Penugasan"
    admin.post("/master-data/penilik/PNL-01/ketersediaan", data={"status": "Tersedia"})
    r = admin.post(f"/verifikasi/{WO_AMBIGU}/inspect", data={"nama_penilik": "PNL-01"})
    assert "tidak dapat diubah" in r.text and status(WO_AMBIGU) == "Menunggu Penugasan"


def test_a09_inspect_dan_skip_ditolak_untuk_skor_jelas(db_bersih):
    lapor(klien(WARGA))
    tid = tiket_terbaru_warga()
    admin = klien(ADMIN)
    html = admin.get(f"/verifikasi?ticket_id={tid}").text
    assert f'action="/verifikasi/{tid}/inspect"' not in html and f'action="/verifikasi/{tid}/approve"' in html
    r = admin.post(f"/verifikasi/{tid}/inspect", data={"nama_penilik": "PNL-01"})
    assert "skor jelas" in r.text
    r = admin.post(f"/verifikasi/{tid}/skip-inspection")
    assert "skor jelas" in r.text
    t = ambil(WorkOrder, tid)
    assert (t.status_work_order, t.log_keputusan, t.id_penilik) == ("Dilaporkan", None, None)


def test_a09_setujui_ditolak_untuk_skor_ambigu(db_bersih):
    r = klien(ADMIN).post(f"/verifikasi/{WO_AMBIGU}/approve")
    assert "tidak dapat disetujui" in r.text and "skor ambigu" in r.text
    assert status(WO_AMBIGU) == "Dilaporkan"


# --------------------------------------------------------------------------- #
# A-10: an inspector only inspects tickets assigned to them
# --------------------------------------------------------------------------- #
def test_a10_tiket_disetujui_belum_ditugaskan_bukan_tugas_inspeksi(db_bersih):
    c = klien(PENILIK)
    assert WO_DISETUJUI not in c.get("/TugasLapangan").text
    assert c.get(f"/TugasLapangan/{WO_DISETUJUI}").status_code == 404
    assert inspeksi(c, WO_DISETUJUI).status_code == 404
    assert status(WO_DISETUJUI) == "Disetujui" and hitung(RiwayatStatus, id_work_order=WO_DISETUJUI, status="Terinspeksi") == 0


def test_a10_controller_menolak_inspeksi_tanpa_penugasan(db_bersih):
    from app.controllers.kontrol_inspeksi import KontrolInspeksi
    db = SessionLocal()
    hasil = KontrolInspeksi(db).simpan_inspeksi(WO_DISETUJUI, "PNL-01", "1m", "", "Tambal Hotmix")
    db.close()
    assert not hasil["success"] and status(WO_DISETUJUI) == "Disetujui"


def test_a10_alur_status_mewajibkan_penugasan_sebelum_inspeksi():
    from app.services.alur_status import SIAP_INSPEKSI, boleh_transisi
    assert "Disetujui" not in SIAP_INSPEKSI
    assert not boleh_transisi("Disetujui", "Terinspeksi")
    assert boleh_transisi("Ditugaskan", "Terinspeksi") and boleh_transisi("Menunggu Inspeksi", "Terinspeksi")


def test_a10_setelah_ditugaskan_penilik_bisa_menginspeksi(db_bersih):
    klien(ADMIN).post(f"/work-orders/{WO_DISETUJUI}/assign", data={"nama_penilik": "PNL-01"})
    c = klien(PENILIK)
    assert WO_DISETUJUI in c.get("/TugasLapangan").text
    inspeksi(c, WO_DISETUJUI)
    assert status(WO_DISETUJUI) == "Terinspeksi"


def test_a10_menunggu_inspeksi_hanya_untuk_penilik_yang_dipilih(db_bersih):
    _, sandi = penilik_baru("199005122022031005", "Rina Penilik")
    lapor(klien(WARGA), nama_foto="retak_permukaan.jpg", kategori="Retak Permukaan",
          deskripsi="Retak memanjang di permukaan aspal dekat halte")   # simulated AI: ambiguous score
    tid = tiket_terbaru_warga()
    assert 4.0 <= ambil(WorkOrder, tid).risk_score < 6.0
    klien(ADMIN).post(f"/verifikasi/{tid}/inspect", data={"nama_penilik": "PNL-01"})
    assert status(tid) == "Menunggu Inspeksi"
    lain = klien("199005122022031005", sandi)
    assert tid not in lain.get("/TugasLapangan").text
    assert inspeksi(lain, tid).status_code == 404
    inspeksi(klien(PENILIK), tid)
    assert status(tid) == "Terinspeksi"


# --------------------------------------------------------------------------- #
# B-01: Dashboard KPI cards follow the table's filter; each card means something different
# --------------------------------------------------------------------------- #
def test_b01_kartu_dashboard_mengikuti_filter(db_bersih):
    from app.controllers.kontrol_dashboard import KontrolDashboard
    admin = klien(ADMIN)
    html = admin.get("/Dashboard?status=Selesai").text
    db = SessionLocal()
    baris = KontrolDashboard(db).filter_dashboard(status="Selesai")["daftar_tiket"]
    db.close()
    assert angka(html, "kartuTotal") == len(baris) == 1
    assert angka(html, "kartuAktif") == 0 and angka(html, "kartuSelesai") == 1
    assert "sesuai filter" in html


def test_b01_kartu_dashboard_punya_arti_berbeda(db_bersih):
    html = klien(ADMIN).get("/Dashboard").text
    # seed: 5 tickets, 1 Selesai; only REP-2026-00298 (Ditugaskan) is in field handling
    assert angka(html, "kartuTotal") == 5 and angka(html, "kartuAktif") == 4
    assert angka(html, "kartuPenanganan") == 1 and angka(html, "kartuBelumDitangani") == 3
    assert angka(html, "kartuPenanganan") + angka(html, "kartuBelumDitangani") == angka(html, "kartuAktif")


# --------------------------------------------------------------------------- #
# B-02: Work Order cards follow the filter and add up to the total
# --------------------------------------------------------------------------- #
def test_b02_kartu_work_order_konsisten_dengan_tabel(db_bersih):
    admin = klien(ADMIN)
    admin.post(f"/verifikasi/{WO_AMBIGU}/inspect", data={"nama_penilik": "PNL-01"})   # Menunggu Inspeksi
    html = admin.get("/work-orders").text
    total = angka(html, "kartuTotalWo")
    assert total == 5 == int(re.search(r"Menampilkan (\d+) tiket", html).group(1))
    assert angka(html, "kartuSiapDitugaskan") == 2      # 00341, 00360 (Disetujui)
    assert angka(html, "kartuDikerjakan") == 2          # 00298 Ditugaskan, 00355 Menunggu Inspeksi
    assert angka(html, "kartuSelesaiWo") == 1
    assert (angka(html, "kartuBelumVerifikasi") + angka(html, "kartuSiapDitugaskan")
            + angka(html, "kartuDikerjakan") + angka(html, "kartuSelesaiWo")) == total


def test_b02_kartu_work_order_mengikuti_filter(db_bersih):
    html = klien(ADMIN).get("/work-orders?status=Selesai").text
    assert angka(html, "kartuTotalWo") == 1 and angka(html, "kartuSelesaiWo") == 1
    assert angka(html, "kartuSiapDitugaskan") == 0 and "sesuai filter" in html


# --------------------------------------------------------------------------- #
# B-03: one notification per citizen per status change
# --------------------------------------------------------------------------- #
def test_b03_warga_dengan_dua_laporan_digabung_mendapat_satu_notifikasi(db_bersih):
    warga = klien(WARGA)
    lapor(warga)
    lapor(warga, deskripsi="Lubangnya makin dalam dan berbahaya untuk motor")
    tid = tiket_terbaru_warga()
    assert hitung(Laporan, id_work_order=tid, id_warga="USR-01") == 2   # merged (BR-3)
    klien(ADMIN).post(f"/verifikasi/{tid}/approve")
    assert status(tid) == "Disetujui"
    db = SessionLocal()
    n = (db.query(Notifikasi).join(Laporan, Notifikasi.id_laporan == Laporan.id_laporan)
         .filter(Laporan.id_work_order == tid, Notifikasi.id_warga == "USR-01",
                 Notifikasi.judul == "Laporan diverifikasi").count())
    db.close()
    assert n == 1


def test_b03_warga_berbeda_tetap_masing_masing_mendapat_notifikasi():
    from app.services.alur_status import laporan_per_warga
    a1 = Laporan(id_laporan="LAP-2026-0010", id_warga="USR-01")
    a2 = Laporan(id_laporan="LAP-2026-0012", id_warga="USR-01")
    b1 = Laporan(id_laporan="LAP-2026-0011", id_warga="USR-03")
    hasil = {lap.id_laporan for lap in laporan_per_warga([a1, b1, a2])}
    assert hasil == {"LAP-2026-0012", "LAP-2026-0011"}


# --------------------------------------------------------------------------- #
# B-04: one rating per (citizen, ticket); Kinerja averages per unique citizen
# --------------------------------------------------------------------------- #
def _laporan_kedua_di_tiket_selesai(id_laporan="LAP-2026-0099"):
    db = SessionLocal()
    db.add(Laporan(id_laporan=id_laporan, id_work_order=WO_SELESAI, id_warga="USR-01", id_wilayah="WIL-01",
                   deskripsi="Laporan kedua di titik yang sama", url_foto="static/uploads/x.jpg", status="Selesai"))
    db.commit()
    db.close()
    return id_laporan


def test_b04_rating_kedua_untuk_tiket_yang_sama_ditolak(db_bersih):
    kedua = _laporan_kedua_di_tiket_selesai()
    c = klien(WARGA)
    c.post("/lacak/LAP-2026-0003/rating", data={"nilai_bintang": "5"})
    assert hitung(Rating, id_laporan="LAP-2026-0003") == 1
    r = c.post(f"/lacak/{kedua}/rating", data={"nilai_bintang": "1"})
    assert "sudah Anda beri penilaian melalui laporan LAP-2026-0003" in r.text
    assert hitung(Rating, id_laporan=kedua) == 0
    html = c.get(f"/lacak?id={kedua}").text
    assert 'id="formRating"' not in html and 'id="ratingTiketSudahAda"' in html


def test_b04_rata_rata_kinerja_satu_rating_per_warga(db_bersih):
    from app.controllers.kontrol_laporan_kinerja import KontrolLaporanKinerja
    kedua = _laporan_kedua_di_tiket_selesai()
    awal = datetime.now(timezone.utc) - timedelta(days=1)
    db = SessionLocal()
    # old data from before the rule: the same citizen rated the ticket through both reports
    db.add(Rating(id_rating="RTG-UJI-1", id_laporan="LAP-2026-0003", nilai_bintang=5, tanggal_rating=awal))
    db.add(Rating(id_rating="RTG-UJI-2", id_laporan=kedua, nilai_bintang=1, tanggal_rating=awal + timedelta(hours=1)))
    db.commit()
    data = KontrolLaporanKinerja(db).rekap()
    db.close()
    baris = next(b for b in data["tiket"] if b["id_work_order"] == WO_SELESAI)
    assert baris["rating"] == [5]
    assert data["total"]["jumlah_rating"] == 1 and data["total"]["rata_rating"] == 5.0


# --------------------------------------------------------------------------- #
# C-05 / C-06: master data validation
# --------------------------------------------------------------------------- #
def test_c05_nip_angka_full_width_ditolak(db_bersih):
    nip = "１９９００５１２２０２２０３１００５"   # 18 full-width digits
    r = klien(ADMIN).post("/master-data/penilik", data={"nip": nip, "nama_penilik": "X", "id_wilayah": "WIL-01"})
    assert "Format NIP tidak valid" in r.text and hitung(PenilikJalan, nip=nip) == 0


def test_c06_status_ketersediaan_tidak_valid_bukan_404(db_bersih):
    admin = klien(ADMIN)
    r = admin.post("/master-data/penilik/PNL-01/ketersediaan", data={"status": "Liburan"})
    assert r.status_code == 400 and "Status ketersediaan tidak valid" in r.text
    assert ambil(PenilikJalan, "PNL-01").status_ketersediaan == "Tersedia"
    assert admin.post("/master-data/penilik/PNL-99/ketersediaan", data={"status": "Cuti"}).status_code == 404


# --------------------------------------------------------------------------- #
# D-02 / D-03 / D-04: code matches design.md / BR-2
# --------------------------------------------------------------------------- #
def test_d02_tombol_progres_admin_punya_id(db_bersih):
    klien(ADMIN).post(f"/work-orders/{WO_DISETUJUI}/assign", data={"nama_penilik": "PNL-01"})
    inspeksi(klien(PENILIK), WO_DISETUJUI)
    admin = klien(ADMIN)
    admin.post(f"/work-orders/{WO_DISETUJUI}/spk", data={"nomor_spk": "SPK/UJI/001", "tim_pelaksana": "Satgas Rayon Gubeng"})
    html = _panel(admin, WO_DISETUJUI)
    assert 'id="formProgresAdmin"' in html and 'id="perbaruiStatus"' in html


def test_d02_id_dom_di_design_md_ada_di_template():
    design = (ROOT / "design.md").read_text(encoding="utf-8")
    template = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "app/views/templates").glob("*.html"))
    hilang = [i for i in re.findall(r"`#([A-Za-z_][\w-]*)`", design)
              if not re.fullmatch(r"[0-9A-Fa-f]{6}", i)                       # colour codes
              if f'id="{i}"' not in template and f"'{i}'" not in template and f'"{i}"' not in template]
    assert hilang == []


@pytest.mark.parametrize("skor,status_wo,warna", [
    (8.4, "Dilaporkan", "#DC2626"), (6.0, "Disetujui", "#EA580C"), (5.1, "Dilaporkan", "#D97706"),
    (3.5, "Dilaporkan", "#16A34A"), (8.4, "Selesai", "#16A34A"),
])
def test_d03_warna_peta_sesuai_design(skor, status_wo, warna):
    from app.controllers.kontrol_dashboard import warna_marker
    assert warna_marker(WorkOrder(risk_score=skor, status_work_order=status_wo)) == warna


def test_d04_default_kolom_work_order_sesuai_br2(db_bersih):
    from app.services.risk_scoring import KELAS_JALAN_DEFAULT, klasifikasi_prioritas
    db = SessionLocal()
    db.add(WorkOrder(id_work_order="REP-UJI-DEFAULT", kategori_kerusakan="Jalan Berlubang"))
    db.commit()
    wo = db.get(WorkOrder, "REP-UJI-DEFAULT")
    hasil = (wo.kelas_jalan, wo.prioritas, wo.sla_rekomendasi)
    db.close()
    # sla_rekomendasi is deprecated (SLA removed): no default value any more
    assert hasil == (KELAS_JALAN_DEFAULT, klasifikasi_prioritas(0.0), None)


# --------------------------------------------------------------------------- #
# Documentation consistency: B-05, D-01, D-04, D-05, E-01, architecture.md BR-3 line
# --------------------------------------------------------------------------- #
def _baca(nama):
    return (ROOT / nama).read_text(encoding="utf-8")


def test_b05_prd_br3_sesuai_kode():
    prd = _baca("prd.md")
    assert '"Digabungkan"' not in prd and "`Digabungkan`" not in prd
    assert "status laporan yang digabung mengikuti status tiket" in prd.lower()


def test_d01_status_ketersediaan_di_dokumen_sesuai_kode():
    for nama in ("design.md", "architecture.md"):
        isi = _baca(nama)
        assert "Bertugas" not in isi, nama
        assert all(s in isi for s in STATUS_KETERSEDIAAN), nama


def test_d04_dokumen_br2_tanpa_target_waktu():
    # D-04 used to check that the SLA ranges in README matched BR-2. The SLA was removed
    # (teaching assistant's review), so README must list the BR-2 priority levels without time targets.
    readme = _baca("README.md")
    assert re.search(r"4,0 ≤ skor < 6,0 Borderline", readme)
    assert not re.search(r"\d\s*[x×]\s*24 jam", readme)


def test_d05_dokumen_hak_akses_dan_rute_lengkap():
    prd, readme, arsitektur = _baca("prd.md"), _baca("README.md"), _baca("architecture.md")
    assert "/laporan-kinerja" in prd
    assert re.search(r"^\|\s*`/laporan-kinerja", readme, re.M), "README: baris /laporan-kinerja di tabel hak akses"
    assert "/master-data/penilik/{id}/ketersediaan" in arsitektur
    assert "Menunggu Penugasan" in readme
    from app.services import alur_status
    assert "Menunggu Penugasan" in alur_status.__doc__


def test_arsitektur_menyebut_deduplikasi_dua_tingkat():
    arsitektur = _baca("architecture.md")
    assert "50m Spatial+NLP" not in arsitektur
    assert "15 m" in arsitektur and "50 m" in arsitektur


def test_e01_jumlah_tes_di_dokumen_sesuai_koleksi():
    hasil = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                           cwd=ROOT, capture_output=True, text=True, timeout=300)
    jumlah = int(re.search(r"(\d+) tests? collected", hasil.stdout).group(1))
    for nama in ("CLAUDE.md", "README.md", "architecture.md"):
        assert f"{jumlah} tes" in _baca(nama) or f"{jumlah} tests" in _baca(nama), nama


def test_e04_tidak_ada_import_entitas_yang_tidak_dipakai():
    sumber = (ROOT / "tests/test_sprint2.py").read_text(encoding="utf-8")
    pohon = ast.parse(sumber)
    diimpor = [a.asname or a.name for n in ast.walk(pohon) if isinstance(n, ast.ImportFrom)
               and n.module == "app.models.entities" for a in n.names]
    dipakai = {n.id for n in ast.walk(pohon) if isinstance(n, ast.Name)}
    assert [nama for nama in diimpor if nama not in dipakai] == []
