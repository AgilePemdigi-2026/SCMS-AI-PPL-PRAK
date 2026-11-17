"""UC-F: Admin menerbitkan SPK; petugas memperbarui progres sampai Selesai."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import JADWAL_AKTIF, JADWAL_DIGANTI, JADWAL_TERCATAT, Perbaikan, WorkOrder
from app.services.ai_service import validasi_foto
from app.services.alur_status import DALAM_PROSES, SELESAI, TERINSPEKSI, catat_riwayat, tutup_tiket, ubah_status
from app.services.penyimpanan import dengan_coba_ulang, id_berurutan, tulis_dengan_foto

PESAN_FOTO_WAJIB = "Foto bukti penyelesaian perbaikan wajib diunggah untuk menutup laporan"
PESAN_OK = "Status perbaikan berhasil diperbarui"
PESAN_SPK_OK = "SPK berhasil diterbitkan, status tiket menjadi Dalam Proses"
PESAN_SPK_TIDAK_LENGKAP = "Nomor SPK dan tim pelaksana wajib diisi"
PESAN_SPK_DUPLIKAT = "Nomor SPK sudah dipakai tiket lain"
PESAN_BELUM_INSPEKSI = "SPK hanya dapat diterbitkan untuk tiket berstatus Terinspeksi"
PESAN_BUKAN_PROSES = "Progres hanya dapat diperbarui untuk tiket berstatus Dalam Proses"
PESAN_CATATAN_WAJIB = "Isi catatan progres pengerjaan"
PESAN_STATUS_TIDAK_VALID = "Pilih status progres yang valid"
PESAN_REKOMENDASI_TERTUNDA = ("Penilik merekomendasikan tiket ini ditutup: konfirmasi atau tolak rekomendasi "
                              "tersebut sebelum menerbitkan SPK")
PESAN_TANPA_REKOMENDASI = "Tidak ada rekomendasi tutup dari penilik yang menunggu keputusan"
PESAN_KONFIRMASI_OK = "Tiket ditutup sesuai rekomendasi penilik"
PESAN_TOLAK_REKOMENDASI_OK = "Rekomendasi tutup ditolak; SPK dapat diterbitkan"
KEPUTUSAN_DIKONFIRMASI = "Dikonfirmasi"
# Sprint 3 / CO-3 (PRD 5.3 "Kunjungan lanjutan"): the date is a work plan, not a deadline.
PESAN_JADWAL_WAJIB = "Isi jadwal kunjungan lanjutan untuk perbaikan sementara"
PESAN_JADWAL_TIDAK_VALID = "Jadwal kunjungan lanjutan harus tanggal setelah hari ini"
PESAN_SEMENTARA_BUKAN_SELESAI = "Perbaikan sementara disimpan sebagai Dalam Proses, bukan Selesai"
PESAN_KUNJUNGAN_BELUM_DICATAT = "Catat kunjungan lanjutan terlebih dahulu sebelum menyelesaikan tiket"
PESAN_TANPA_JADWAL = "Tidak ada kunjungan lanjutan yang sedang dijadwalkan untuk tiket ini"
PESAN_CATATAN_KUNJUNGAN = "Isi catatan kunjungan lanjutan"
PESAN_JADWAL_OK = "Perbaikan sementara tercatat; kunjungan lanjutan dijadwalkan"
PESAN_KUNJUNGAN_OK = "Kunjungan lanjutan berhasil dicatat"
WIB = timezone(timedelta(hours=7))


def hari_ini_wib() -> date:
    return datetime.now(WIB).date()


def baca_jadwal_lanjutan(teks: str):
    """(date, None) for a valid follow-up date after today (WIB), else (None, message)."""
    teks = (teks or "").strip()
    if not teks:
        return None, PESAN_JADWAL_WAJIB
    try:
        tanggal = date.fromisoformat(teks)
    except ValueError:
        return None, PESAN_JADWAL_TIDAK_VALID
    if tanggal <= hari_ini_wib():
        return None, PESAN_JADWAL_TIDAK_VALID
    return tanggal, None
KEPUTUSAN_DITOLAK = "Ditolak"

STATUS_PROGRES = (DALAM_PROSES, SELESAI)


class KontrolPenanganan:
    def __init__(self, db: Session):
        self.db = db

    def terbitkan_spk(self, id_work_order: str, nomor_spk: str, tim_pelaksana: str,
                      status_awal: str = DALAM_PROSES, aktor: Optional[str] = None) -> dict:
        wo = self.db.get(WorkOrder, id_work_order)
        if not wo:
            return {"success": False, "message": PESAN_BELUM_INSPEKSI}
        if wo.status_work_order != TERINSPEKSI:
            return {"success": False, "message": PESAN_BELUM_INSPEKSI}
        if wo.rekomendasi_tutup_tertunda:  # PRD 5.3 BR-4: the closing recommendation is decided first
            return {"success": False, "message": PESAN_REKOMENDASI_TERTUNDA}
        nomor_spk = (nomor_spk or "").strip()
        tim_pelaksana = (tim_pelaksana or "").strip()
        if not nomor_spk or not tim_pelaksana:
            return {"success": False, "message": PESAN_SPK_TIDAK_LENGKAP}
        if status_awal != DALAM_PROSES:
            return {"success": False, "message": PESAN_STATUS_TIDAK_VALID}
        def langkah():
            wo_ = self.db.get(WorkOrder, id_work_order)
            if wo_.status_work_order != TERINSPEKSI:
                return {"success": False, "message": PESAN_BELUM_INSPEKSI}
            if wo_.rekomendasi_tutup_tertunda:
                return {"success": False, "message": PESAN_REKOMENDASI_TERTUNDA}
            if self.db.query(WorkOrder).filter(func.upper(WorkOrder.nomor_spk) == nomor_spk.upper()).first():
                return {"success": False, "message": PESAN_SPK_DUPLIKAT}
            wo_.nomor_spk = nomor_spk[:50]
            wo_.tim_pelaksana = tim_pelaksana[:100]
            self.db.add(Perbaikan(
                id_perbaikan=id_berurutan(self.db, Perbaikan.id_perbaikan, "PRB"),
                id_work_order=wo_.id_work_order,
                status_perbaikan=DALAM_PROSES,
                catatan=f"SPK {wo_.nomor_spk} diterbitkan untuk {wo_.tim_pelaksana}",
                dicatat_oleh=aktor,
            ))
            ubah_status(self.db, wo_, DALAM_PROSES, f"SPK {wo_.nomor_spk} - {wo_.tim_pelaksana}", aktor)
            self.db.commit()
            return {"success": True, "message": PESAN_SPK_OK}

        return dengan_coba_ulang(self.db, langkah)

    def perbarui_progres(self, id_work_order: str, status_baru: str, catatan: str,
                         nama_foto: str = "", foto_bytes: Optional[bytes] = None,
                         aktor: Optional[str] = None, perbaikan_sementara: bool = False,
                         jadwal_lanjutan: str = "") -> dict:
        """Progress update of a ticket "Dalam Proses" (UC-F). Sprint 3 (PRD 5.3, CO-3): a temporary
        repair needs a follow-up visit date after today; the ticket stays Dalam Proses, the schedule
        becomes the single active one (an earlier active schedule is replaced and recorded), and the
        ticket cannot become Selesai until that visit is recorded."""
        wo = self.db.get(WorkOrder, id_work_order)
        if not wo or wo.status_work_order != DALAM_PROSES:
            return {"success": False, "message": PESAN_BUKAN_PROSES}
        if status_baru not in STATUS_PROGRES:
            return {"success": False, "message": PESAN_STATUS_TIDAK_VALID}
        catatan = (catatan or "").strip()
        tanggal_lanjutan = None
        if perbaikan_sementara:
            if status_baru != DALAM_PROSES:
                return {"success": False, "message": PESAN_SEMENTARA_BUKAN_SELESAI}
            tanggal_lanjutan, pesan = baca_jadwal_lanjutan(jadwal_lanjutan)
            if pesan:
                return {"success": False, "message": pesan}
        if status_baru == SELESAI and wo.jadwal_lanjutan_aktif:
            return {"success": False, "message": PESAN_KUNJUNGAN_BELUM_DICATAT}

        format_gambar = ""
        if foto_bytes:
            val = validasi_foto(nama_foto, 0, foto_bytes)
            if not val.valid:
                return {"success": False, "message": val.message}
            format_gambar = val.format_gambar
        if status_baru == SELESAI and not foto_bytes:
            return {"success": False, "message": PESAN_FOTO_WAJIB}
        if status_baru == DALAM_PROSES and not catatan:
            return {"success": False, "message": PESAN_CATATAN_WAJIB}

        def langkah(url_foto):
            wo_ = self.db.get(WorkOrder, id_work_order)
            if wo_.status_work_order != DALAM_PROSES:
                return {"success": False, "message": PESAN_BUKAN_PROSES}
            lama = wo_.jadwal_lanjutan_aktif
            if status_baru == SELESAI and lama:  # a schedule was added in the meantime
                return {"success": False, "message": PESAN_KUNJUNGAN_BELUM_DICATAT}
            sekarang = datetime.now(timezone.utc)
            keterangan = catatan
            if tanggal_lanjutan:
                tampil = tanggal_lanjutan.strftime("%d/%m/%Y")
                if lama:
                    lama.status_jadwal = JADWAL_DIGANTI
                    rencana = f"Kunjungan lanjutan dijadwalkan ulang ke {tampil} (sebelumnya {lama.jadwal_tampil})"
                else:
                    rencana = f"Kunjungan lanjutan dijadwalkan {tampil}"
                keterangan = f"Perbaikan sementara: {catatan}; {rencana}"
            self.db.add(Perbaikan(
                id_perbaikan=id_berurutan(self.db, Perbaikan.id_perbaikan, "PRB"),
                id_work_order=wo_.id_work_order,
                status_perbaikan=status_baru,
                catatan=catatan or None,
                foto_sesudah=url_foto,
                tanggal_selesai=sekarang if status_baru == SELESAI else None,
                dicatat_oleh=aktor,
                perbaikan_sementara=bool(tanggal_lanjutan),
                jadwal_lanjutan=tanggal_lanjutan.isoformat() if tanggal_lanjutan else None,
                status_jadwal=JADWAL_AKTIF if tanggal_lanjutan else None,
            ))
            if status_baru == SELESAI:
                wo_.tanggal_selesai = sekarang
            # same-status entry while Dalam Proses: history + citizen notification, no new transition
            ubah_status(self.db, wo_, status_baru, keterangan, aktor, catat_walau_sama=True)
            self.db.commit()
            return {"success": True, "message": PESAN_JADWAL_OK if tanggal_lanjutan else PESAN_OK}

        return tulis_dengan_foto(self.db, foto_bytes, format_gambar, langkah)

    def catat_kunjungan_lanjutan(self, id_work_order: str, catatan: str, nama_foto: str = "",
                                 foto_bytes: Optional[bytes] = None, aktor: Optional[str] = None) -> dict:
        """Record the follow-up visit of the active schedule (allowed before its planned date,
        decision 5.9 no. 7). The schedule stops being active, so the ticket may then become Selesai."""
        wo = self.db.get(WorkOrder, id_work_order)
        if not wo or wo.status_work_order != DALAM_PROSES:
            return {"success": False, "message": PESAN_BUKAN_PROSES}
        if not wo.jadwal_lanjutan_aktif:
            return {"success": False, "message": PESAN_TANPA_JADWAL}
        catatan = (catatan or "").strip()
        if not catatan:
            return {"success": False, "message": PESAN_CATATAN_KUNJUNGAN}
        format_gambar = ""
        if foto_bytes:
            val = validasi_foto(nama_foto, 0, foto_bytes)
            if not val.valid:
                return {"success": False, "message": val.message}
            format_gambar = val.format_gambar

        def langkah(url_foto):
            wo_ = self.db.get(WorkOrder, id_work_order)
            jadwal = wo_.jadwal_lanjutan_aktif if wo_.status_work_order == DALAM_PROSES else None
            if not jadwal:
                return {"success": False, "message": PESAN_TANPA_JADWAL}
            jadwal.status_jadwal = JADWAL_TERCATAT
            jadwal.kunjungan_dicatat_pada = datetime.now(timezone.utc)
            jadwal.catatan_kunjungan = catatan
            jadwal.foto_kunjungan = url_foto
            ubah_status(self.db, wo_, DALAM_PROSES,
                        f"Kunjungan lanjutan dicatat (jadwal {jadwal.jadwal_tampil}): {catatan}", aktor,
                        catat_walau_sama=True)
            self.db.commit()
            return {"success": True, "message": PESAN_KUNJUNGAN_OK}

        return tulis_dengan_foto(self.db, foto_bytes, format_gambar, langkah)

    # ---- PRD 5.3 BR-4 door (b): Admin decides on the inspector's closing recommendation --------
    def _rekomendasi_tertunda(self, id_work_order: str):
        wo = self.db.get(WorkOrder, id_work_order)
        if not wo or wo.status_work_order != TERINSPEKSI:
            return wo, None
        return wo, wo.rekomendasi_tutup_tertunda

    def konfirmasi_tutup(self, id_work_order: str, aktor: Optional[str] = None) -> dict:
        """Confirm the recommendation: Terinspeksi -> Ditutup with the inspector's reason."""
        def langkah():
            wo, ins = self._rekomendasi_tertunda(id_work_order)
            if ins is None:
                return {"success": False, "message": PESAN_TANPA_REKOMENDASI}
            ins.keputusan_rekomendasi = KEPUTUSAN_DIKONFIRMASI
            ins.diputuskan_oleh = (aktor or "")[:100] or None
            tutup_tiket(self.db, wo, ins.alasan_rekomendasi, aktor)
            self.db.commit()
            return {"success": True, "message": PESAN_KONFIRMASI_OK}

        return dengan_coba_ulang(self.db, langkah)

    def tolak_rekomendasi(self, id_work_order: str, aktor: Optional[str] = None) -> dict:
        """Reject the recommendation: the ticket stays Terinspeksi (no status change, recorded in the
        history) and the SPK can be issued."""
        def langkah():
            wo, ins = self._rekomendasi_tertunda(id_work_order)
            if ins is None:
                return {"success": False, "message": PESAN_TANPA_REKOMENDASI}
            ins.keputusan_rekomendasi = KEPUTUSAN_DITOLAK
            ins.diputuskan_oleh = (aktor or "")[:100] or None
            catat_riwayat(self.db, wo, TERINSPEKSI,
                          f"Rekomendasi tutup ditolak Admin ({ins.alasan_rekomendasi}); lanjut ke penerbitan SPK", aktor)
            self.db.commit()
            return {"success": True, "message": PESAN_TOLAK_REKOMENDASI_OK}

        return dengan_coba_ulang(self.db, langkah)
