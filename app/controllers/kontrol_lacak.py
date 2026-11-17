"""UC-C (lacak status laporan) dan UC-J (rating & ulasan) untuk Warga."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Inspeksi, Laporan, Perbaikan, Rating, RiwayatStatus, WorkOrder
from app.services.alur_status import DALAM_PROSES, DITUTUP, SELESAI, tahapan_linimasa
from app.services.penyimpanan import dengan_coba_ulang, id_acak

PESAN_TIDAK_DITEMUKAN = "Nomor tiket laporan tidak ditemukan, periksa kembali ID Laporan Anda"
PESAN_RATING_KOSONG = "Silakan pilih bintang rating (1-5) terlebih dahulu"
PESAN_RATING_OK = "Terima kasih atas ulasan dan penilaian Anda"
PESAN_RATING_BELUM_SELESAI = "Rating hanya dapat diberikan untuk laporan yang sudah Selesai"
PESAN_RATING_SUDAH_ADA = "Laporan ini sudah Anda beri penilaian"
PESAN_RATING_DITUTUP = "Tiket ini ditutup tanpa perbaikan sehingga tidak dapat dinilai"
PESAN_RATING_TIKET_SUDAH_ADA = ("Tiket penanganan ini sudah Anda beri penilaian melalui laporan {id_laporan}. "
                                "Setiap warga memberi satu penilaian per tiket")


class KontrolLacak:
    def __init__(self, db: Session):
        self.db = db

    def daftar_laporan_warga(self, id_warga: str):
        return (self.db.query(Laporan).filter_by(id_warga=id_warga)
                .order_by(Laporan.tanggal_lapor.desc()).all())

    def _laporan_milik(self, id_laporan: str, id_warga: str) -> Optional[Laporan]:
        kode = (id_laporan or "").strip().upper()
        if not kode:
            return None
        # A citizen can only see their own reports; someone else's ID is "not found".
        return self.db.query(Laporan).filter_by(id_laporan=kode, id_warga=id_warga).first()

    def _rating_warga_untuk_tiket(self, id_work_order: Optional[str], id_warga: str) -> Optional[Rating]:
        """The rating this citizen already gave to the ticket through any of their reports
        (two reports merged into one ticket still get one rating per citizen, BR-3/UC-J)."""
        if not id_work_order:
            return None
        return (self.db.query(Rating).join(Laporan, Rating.id_laporan == Laporan.id_laporan)
                .filter(Laporan.id_work_order == id_work_order, Laporan.id_warga == id_warga)
                .order_by(Rating.tanggal_rating, Rating.id_rating).first())

    def detail_lacak(self, id_laporan: str, id_warga: str) -> dict:
        lap = self._laporan_milik(id_laporan, id_warga)
        if not lap:
            return {"success": False, "message": PESAN_TIDAK_DITEMUKAN}

        wo = self.db.get(WorkOrder, lap.id_work_order) if lap.id_work_order else None
        riwayat = []
        if wo:
            riwayat = (self.db.query(RiwayatStatus).filter_by(id_work_order=wo.id_work_order)
                       .order_by(RiwayatStatus.waktu, RiwayatStatus.id_riwayat).all())
        status_tercapai = {r.status for r in riwayat} | ({wo.status_work_order} if wo else set())
        inspeksi = None
        bukti_selesai = None
        if wo:
            inspeksi = (self.db.query(Inspeksi).filter_by(id_work_order=wo.id_work_order)
                        .order_by(Inspeksi.id_inspeksi.desc()).first())
            bukti_selesai = (self.db.query(Perbaikan)
                             .filter_by(id_work_order=wo.id_work_order, status_perbaikan=SELESAI)
                             .order_by(Perbaikan.waktu.desc()).first())
        rating = self.db.query(Rating).filter_by(id_laporan=lap.id_laporan).first()
        # rating given to the same ticket through the citizen's other (merged) report
        rating_tiket = None if rating else self._rating_warga_untuk_tiket(lap.id_work_order, id_warga)
        status = wo.status_work_order if wo else lap.status
        tahapan = tahapan_linimasa(status_tercapai)
        if status == DITUTUP:
            # PRD 5.3 BR-4: closed without repair. Keep the stages actually reached and end the
            # timeline with "Ditutup" and its reason instead of the repair stages.
            tahapan = [t for t in tahapan if t["selesai"]]
            tahapan.append({"label": f"Ditutup: {wo.alasan_tutup or '-'}", "selesai": True, "ditutup": True})
        jadwal = wo.jadwal_lanjutan_aktif if wo and status == DALAM_PROSES else None
        if jadwal:
            # Sprint 3 / CO-3: temporary repair, the permanent one follows on the planned visit date
            posisi = next((i + 1 for i, t in enumerate(tahapan) if t["label"] == "Perbaikan Berjalan"), len(tahapan))
            tahapan.insert(posisi, {"label": f"Kunjungan lanjutan dijadwalkan {jadwal.jadwal_tampil}",
                                    "selesai": False, "lanjutan": True})
        return {
            "success": True,
            "message": None,
            "laporan": lap,
            "wo": wo,
            "status": status,
            "riwayat": riwayat,
            "tahapan": tahapan,
            "ditutup": status == DITUTUP,
            "alasan_tutup": wo.alasan_tutup if wo else None,
            "inspeksi": inspeksi,
            "bukti_selesai": bukti_selesai,
            "rating": rating,
            "rating_tiket": rating_tiket,
            "boleh_rating": status == SELESAI and rating is None and rating_tiket is None,
        }

    def simpan_rating(self, id_laporan: str, id_warga: str, nilai_bintang, komentar: str = "") -> dict:
        try:
            nilai = int(str(nilai_bintang).strip())
        except (TypeError, ValueError):
            nilai = 0

        def langkah():
            lap = self._laporan_milik(id_laporan, id_warga)
            if not lap:
                return {"success": False, "message": PESAN_TIDAK_DITEMUKAN}
            wo = self.db.get(WorkOrder, lap.id_work_order) if lap.id_work_order else None
            if wo and wo.status_work_order == DITUTUP:
                return {"success": False, "message": PESAN_RATING_DITUTUP}
            if not wo or wo.status_work_order != SELESAI:
                return {"success": False, "message": PESAN_RATING_BELUM_SELESAI}
            if self.db.query(Rating).filter_by(id_laporan=lap.id_laporan).first():
                return {"success": False, "message": PESAN_RATING_SUDAH_ADA}
            lain = self._rating_warga_untuk_tiket(lap.id_work_order, id_warga)
            if lain:
                return {"success": False, "message": PESAN_RATING_TIKET_SUDAH_ADA.format(id_laporan=lain.id_laporan)}
            if not 1 <= nilai <= 5:
                return {"success": False, "message": PESAN_RATING_KOSONG}
            self.db.add(Rating(
                id_rating=id_acak("RTG"),
                id_laporan=lap.id_laporan,
                nilai_bintang=nilai,
                komentar=(komentar or "").strip()[:1000] or None,
            ))
            self.db.commit()
            return {"success": True, "message": PESAN_RATING_OK}

        # a simultaneous duplicate submit hits the UNIQUE constraint, is retried and reports "already rated"
        return dengan_coba_ulang(self.db, langkah)
