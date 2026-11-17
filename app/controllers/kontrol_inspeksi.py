"""UC-E: Penilik Jalan mencatat hasil inspeksi lapangan."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Inspeksi, Laporan, PenilikJalan, Perbaikan, Wilayah, WorkOrder
from app.services import risk_scoring
from app.services.ai_service import KATEGORI_VALID, validasi_foto
from app.services.alur_status import (
    ALASAN_TIDAK_ADA_KERUSAKAN, ALASAN_TUTUP, DALAM_PROSES, SIAP_INSPEKSI, STATUS_FINAL, TERINSPEKSI, ubah_status,
)
from app.services.penyimpanan import id_berurutan, tulis_dengan_foto

PESAN_TIDAK_LENGKAP = "Lengkapi dimensi kerusakan dan rekomendasi teknis penanganan"
PESAN_OK = "Hasil inspeksi berhasil disimpan"
BATAS_RIWAYAT = 20  # completed tickets shown on /TugasLapangan
PESAN_STATUS_SALAH = "Tiket ini tidak sedang menunggu inspeksi lapangan"
PESAN_BUKAN_TUGAS = "Tiket ini bukan tugas Anda"
PESAN_TANPA_LAPORAN = "Tiket ini belum memiliki laporan warga yang dapat diinspeksi"
PESAN_TANPA_TINGKAT = "Pilih tingkat kerusakan hasil inspeksi lapangan"
PESAN_KATEGORI_TIDAK_VALID = "Pilih kategori kerusakan yang valid"
PESAN_ALASAN_REKOMENDASI = "Pilih alasan rekomendasi tutup tiket"
# PRD 5.3 BR-4 door (b): recommendation value that asks the Admin to close the ticket
REKOMENDASI_TUTUP = "Rekomendasikan Tutup"

REKOMENDASI_PENANGANAN = (
    "Tambal Hotmix",
    "Tambal Sulam Dingin (Cold Mix)",
    "Pelapisan Ulang (Overlay)",
    "Rekonstruksi Perkerasan",
    "Perbaikan Drainase",
)


class KontrolInspeksi:
    def __init__(self, db: Session):
        self.db = db

    def _penilik(self, id_penilik: str) -> Optional[PenilikJalan]:
        return self.db.get(PenilikJalan, id_penilik)

    @staticmethod
    def boleh_akses(wo: WorkOrder, penilik: PenilikJalan) -> bool:
        """An inspector only works on tickets in their own region that are assigned to them:
        Ditugaskan (UC-G) or Menunggu Inspeksi with them as inspector (UC-B). An approved but
        unassigned ticket is not their task until the Admin assigns it."""
        return bool(wo and penilik and wo.id_wilayah == penilik.id_wilayah
                    and wo.id_penilik is not None and wo.id_penilik == penilik.id_penilik)

    def daftar_tugas(self, id_penilik: str) -> dict:
        penilik = self._penilik(id_penilik)
        if not penilik:
            return {"inspeksi": [], "menunggu_spk": [], "perbaikan": [], "riwayat": [], "nama_wilayah": "-"}
        semua = (self.db.query(WorkOrder).filter_by(id_wilayah=penilik.id_wilayah)
                 .order_by(WorkOrder.risk_score.desc()).all())
        wilayah = self.db.get(Wilayah, penilik.id_wilayah)
        return {
            "inspeksi": [w for w in semua if w.status_work_order in SIAP_INSPEKSI and self.boleh_akses(w, penilik)],
            # inspected, waiting for the Admin to issue the SPK (so the inspector keeps track of it)
            "menunggu_spk": [w for w in semua if w.status_work_order == TERINSPEKSI and self.boleh_akses(w, penilik)],
            "perbaikan": [w for w in semua if w.status_work_order == DALAM_PROSES and self.boleh_akses(w, penilik)],
            # finished work: Selesai, and Ditutup (closed without repair, PRD 5.3 BR-4)
            "riwayat": sorted((w for w in semua if w.status_work_order in STATUS_FINAL and self.boleh_akses(w, penilik)),
                              key=lambda w: (w.tanggal_selesai or w.tanggal_ditutup or datetime.min).replace(tzinfo=None),
                              reverse=True)[:BATAS_RIWAYAT],
            "nama_wilayah": wilayah.nama_wilayah if wilayah else "-",
        }

    def detail(self, id_work_order: str, id_penilik: str) -> Optional[dict]:
        wo = self.db.get(WorkOrder, id_work_order)
        penilik = self._penilik(id_penilik)
        if not wo or not self.boleh_akses(wo, penilik):
            return None
        laporan = (self.db.query(Laporan).filter_by(id_work_order=wo.id_work_order)
                   .order_by(Laporan.tanggal_lapor).all())
        return {
            "wo": wo,
            "laporan": laporan,
            "inspeksi": (self.db.query(Inspeksi).filter_by(id_work_order=wo.id_work_order)
                         .order_by(Inspeksi.id_inspeksi.desc()).first()),
            "riwayat_perbaikan": (self.db.query(Perbaikan).filter_by(id_work_order=wo.id_work_order)
                                  .order_by(Perbaikan.waktu.desc()).all()),
            "bisa_inspeksi": wo.status_work_order in SIAP_INSPEKSI,
            "bisa_update_perbaikan": wo.status_work_order == DALAM_PROSES,
            "rekomendasi": REKOMENDASI_PENANGANAN,
            "rekomendasi_tutup": REKOMENDASI_TUTUP,
            "alasan_tutup": ALASAN_TUTUP,
            "kategori_valid": KATEGORI_VALID,
            "tingkat_kerusakan": [(nama, nilai, risk_scoring.KETERANGAN_TINGKAT[nama])
                                  for nama, nilai in risk_scoring.TINGKAT_KERUSAKAN.items()],
        }

    def simpan_inspeksi(
        self,
        id_work_order: str,
        id_penilik: str,
        dimensi: str,
        catatan: str,
        rekomendasi: str,
        nama_foto: str = "",
        foto_bytes: Optional[bytes] = None,
        tingkat_kerusakan: str = "",
        kategori_terkonfirmasi: str = "",
        alasan_rekomendasi: str = "",
    ) -> dict:
        """Save the field inspection (-> Terinspeksi) and recompute the Risk Score with the
        field severity of the chosen damage level instead of the AI severity (PRD 5.3 BR-2)."""
        wo = self.db.get(WorkOrder, id_work_order)
        penilik = self._penilik(id_penilik)
        if not wo or not self.boleh_akses(wo, penilik):
            return {"success": False, "message": PESAN_BUKAN_TUGAS}
        if wo.status_work_order not in SIAP_INSPEKSI:
            return {"success": False, "message": PESAN_STATUS_SALAH}
        dimensi = (dimensi or "").strip()
        rekomendasi = (rekomendasi or "").strip()
        alasan_tutup = (alasan_rekomendasi or "").strip()
        # PRD 5.3 BR-4 door (b): "Rekomendasikan Tutup" instead of a treatment, with a reason
        rekomendasi_tutup = rekomendasi == REKOMENDASI_TUTUP
        if rekomendasi_tutup:
            if alasan_tutup not in ALASAN_TUTUP:
                return {"success": False, "message": PESAN_ALASAN_REKOMENDASI}
        elif not dimensi or rekomendasi not in REKOMENDASI_PENANGANAN:
            return {"success": False, "message": PESAN_TIDAK_LENGKAP}
        tingkat = (tingkat_kerusakan or "").strip()
        severity_lapangan = risk_scoring.severity_tingkat(tingkat)
        # The damage level is optional only when the inspector found no damage at all
        # (team decision 5.9 no. 6); the Risk Score is then not recalculated.
        tingkat_opsional = rekomendasi_tutup and alasan_tutup == ALASAN_TIDAK_ADA_KERUSAKAN
        if severity_lapangan is None and not (tingkat_opsional and not tingkat):
            return {"success": False, "message": PESAN_TANPA_TINGKAT}
        # the form pre-fills the ticket's category; empty means "unchanged"
        kategori = (kategori_terkonfirmasi or "").strip() or wo.kategori_kerusakan
        if kategori not in KATEGORI_VALID:
            return {"success": False, "message": PESAN_KATEGORI_TIDAK_VALID}

        format_gambar = ""
        if foto_bytes:
            val = validasi_foto(nama_foto, 0, foto_bytes)
            if not val.valid:
                return {"success": False, "message": val.message}
            format_gambar = val.format_gambar
        if not self.db.query(Laporan).filter_by(id_work_order=wo.id_work_order).first():
            return {"success": False, "message": PESAN_TANPA_LAPORAN}
        catatan = (catatan or "").strip()
        id_penilik_ = penilik.id_penilik

        def langkah(url_foto):
            wo_ = self.db.get(WorkOrder, id_work_order)
            penilik_ = self._penilik(id_penilik_)
            if not self.boleh_akses(wo_, penilik_):
                return {"success": False, "message": PESAN_BUKAN_TUGAS}  # reassigned in the meantime
            if wo_.status_work_order not in SIAP_INSPEKSI:
                return {"success": False, "message": PESAN_STATUS_SALAH}
            laporan_pertama = (self.db.query(Laporan).filter_by(id_work_order=wo_.id_work_order)
                               .order_by(Laporan.tanggal_lapor).first())
            skor_lama = wo_.risk_score or 0.0
            if wo_.severity_ai is None:  # old ticket: keep the AI severity for comparison
                wo_.severity_ai = wo_.severity_score_kasus
            kategori_lama = wo_.kategori_kerusakan
            wo_.kategori_kerusakan = kategori
            hasil_risiko = None
            if severity_lapangan is not None:
                # The field severity replaces the AI severity; E, V and C are unchanged. Later
                # recomputes (e.g. a merged report raising exposure) keep using it.
                wo_.severity_score_kasus = severity_lapangan
                hasil_risiko = risk_scoring.terapkan_ke_work_order(wo_)
            self.db.add(Inspeksi(
                id_inspeksi=id_berurutan(self.db, Inspeksi.id_inspeksi, "INS"),
                id_laporan=laporan_pertama.id_laporan,
                id_penilik=penilik_.id_penilik,
                id_work_order=wo_.id_work_order,
                dimensi_kerusakan=dimensi[:50] or None,
                rekomendasi_penanganan=rekomendasi,
                hasil_temuan=catatan or "-",
                url_foto_temuan=url_foto,
                kategori_terkonfirmasi=kategori,
                tingkat_kerusakan=tingkat or None,
                severity_lapangan=severity_lapangan,
                rekomendasi_tutup=rekomendasi_tutup,
                alasan_rekomendasi=alasan_tutup if rekomendasi_tutup else None,
            ))
            keterangan = [f"Dimensi {dimensi}"] if dimensi else []
            if rekomendasi_tutup:
                keterangan.append(f"Rekomendasi penilik: tutup tiket ({alasan_tutup}), menunggu keputusan Admin")
            else:
                keterangan.append(f"rekomendasi {rekomendasi}")
            if severity_lapangan is not None:
                keterangan.append(f"tingkat kerusakan {tingkat} (severity {severity_lapangan:g})")
            if kategori != kategori_lama:
                keterangan.append(f"kategori dikoreksi {kategori_lama} → {kategori}")
            # one history entry (no extra status row): the recompute is part of the inspection
            if hasil_risiko:
                keterangan.append(f"Risk Score diperbarui {skor_lama:.1f} → {hasil_risiko.risk_score:.1f} "
                                  "berdasarkan inspeksi")
            else:
                keterangan.append("Risk Score tidak dihitung ulang (tidak ditemukan kerusakan)")
            ubah_status(self.db, wo_, TERINSPEKSI, "; ".join(keterangan), penilik_.nama_penilik)
            self.db.commit()
            return {"success": True, "message": PESAN_OK, "risk_score_lama": skor_lama,
                    "risk_score_baru": hasil_risiko.risk_score if hasil_risiko else skor_lama,
                    "prioritas": wo_.prioritas}

        return tulis_dengan_foto(self.db, foto_bytes, format_gambar, langkah)
