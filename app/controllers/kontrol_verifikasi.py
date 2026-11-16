"""UC-B: Admin memverifikasi laporan (tiket) yang baru masuk.

A verification decision is made once, on a ticket that is still "Dilaporkan":
  * clear score (not ambiguous)  -> "Setujui Tiket"            -> Disetujui
  * ambiguous score (BR-2 Borderline, 4.0 <= score < 6.0)
        -> "Tugaskan Inspeksi Tambahan" (inspector must be Tersedia) -> Menunggu Inspeksi
        -> "Lanjutkan Tanpa Inspeksi" (recorded in log_keputusan)    -> Disetujui
The backend accepts exactly the actions the page offers; changing the inspector of a
running inspection is done on the Work Order page (UC-G), where it is recorded.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import Admin, Laporan, PenilikJalan, Wilayah, WorkOrder
from app.controllers.kontrol_penugasan import cari_penilik, label_penilik
from app.services.alur_status import DILAPORKAN, DISETUJUI, MENUNGGU_INSPEKSI, ubah_status
from app.services.risk_scoring import skor_ambigu

# Verification decisions are only possible on a ticket that has not been verified yet.
SIAP_VERIFIKASI = (DILAPORKAN,)

AKSI_SETUJUI = "approve"
AKSI_INSPEKSI = "inspect"
AKSI_TANPA_INSPEKSI = "skip"


def tiket_ambigu(wo: WorkOrder) -> bool:
    return skor_ambigu(wo.risk_score)


def alasan_ditolak(wo: Optional[WorkOrder], aksi: str) -> Optional[str]:
    """None when `aksi` is allowed on this ticket, otherwise the reason shown to the admin."""
    if wo is None:
        return "Tiket tidak ditemukan."
    if wo.status_work_order not in SIAP_VERIFIKASI:
        return (f"Tiket {wo.id_work_order} berstatus {wo.status_work_order}: "
                f"keputusan verifikasi sudah tidak dapat diubah.")
    ambigu = tiket_ambigu(wo)
    if aksi == AKSI_SETUJUI and ambigu:
        return (f"Tiket {wo.id_work_order} memiliki skor ambigu ({wo.risk_score}): pilih Tugaskan Inspeksi "
                f"Tambahan atau Lanjutkan Tanpa Inspeksi di halaman Verifikasi.")
    if aksi in (AKSI_INSPEKSI, AKSI_TANPA_INSPEKSI) and not ambigu:
        return (f"Tiket {wo.id_work_order} memiliki skor jelas ({wo.risk_score}): "
                f"inspeksi tambahan hanya untuk skor ambigu, gunakan Setujui Tiket.")
    return None


class KontrolVerifikasi:
    def __init__(self, db: Session):
        self.db = db

    def _wo(self, id_work_order: str) -> Optional[WorkOrder]:
        return self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()

    def _catat_admin(self, wo: WorkOrder, email_admin: Optional[str]):
        if email_admin:
            admin = self.db.query(Admin).filter_by(email_admin=email_admin).first()
            if admin:
                wo.id_admin = admin.id_admin

    def muat_daftar_tiket(self):
        return self.db.query(WorkOrder).order_by(WorkOrder.risk_score.desc()).all()

    def lihat_detail_tiket(self, id_work_order: str):
        wo = self._wo(id_work_order)
        if not wo:
            return None

        laporan = self.db.query(Laporan).filter_by(id_work_order=id_work_order).first()
        wilayah = self.db.query(Wilayah).filter_by(id_wilayah=wo.id_wilayah).first()
        penilik_list = (self.db.query(PenilikJalan).filter_by(id_wilayah=wo.id_wilayah)
                        .order_by(PenilikJalan.nama_penilik).all())

        is_ambiguous = tiket_ambigu(wo)
        aksi = (AKSI_INSPEKSI, AKSI_TANPA_INSPEKSI) if is_ambiguous else (AKSI_SETUJUI,)
        bisa_diputuskan = all(alasan_ditolak(wo, a) is None for a in aksi)
        opsi_verifikasi = "Butuh Verifikasi Lapangan" if is_ambiguous else "Siap Disetujui"

        return {
            "wo": wo,
            "laporan": laporan,
            "nama_wilayah": wilayah.nama_wilayah if wilayah else "Kota Surabaya",
            "daftar_penilik": [p.nama_penilik for p in penilik_list],
            # every active inspector with their availability; only "Tersedia" can be chosen
            "opsi_penilik": [(p.id_penilik, label_penilik(p), p.status_ketersediaan,
                              p.status_ketersediaan == "Tersedia")
                             for p in penilik_list if p.is_active],
            "is_ambiguous": is_ambiguous,
            "opsi_verifikasi": opsi_verifikasi,
            "risk_score_label": f"{wo.risk_score} ({wo.prioritas})",
            "bisa_diputuskan": bisa_diputuskan,
            "penilik_inspeksi": (self.db.get(PenilikJalan, wo.id_penilik)
                                 if wo.status_work_order == MENUNGGU_INSPEKSI and wo.id_penilik else None),
        }

    def setujui_tiket(self, id_work_order: str, email_admin: Optional[str] = None):
        wo = self._wo(id_work_order)
        if alasan_ditolak(wo, AKSI_SETUJUI) is None:
            ubah_status(self.db, wo, DISETUJUI, "Disetujui oleh Admin", email_admin)
            self._catat_admin(wo, email_admin)
            self.db.commit()
        return wo

    def tugaskan_inspeksi_tambahan(self, id_work_order: str, nama_penilik: str, email_admin: Optional[str] = None):
        wo = self._wo(id_work_order)
        if alasan_ditolak(wo, AKSI_INSPEKSI) is not None:
            return wo
        # Only an available inspector from the ticket's own region can be assigned (same rule as UC-G).
        penilik = cari_penilik(self.db, nama_penilik, wo.id_wilayah, hanya_tersedia=True)
        if penilik:
            wo.id_penilik = penilik.id_penilik
            ubah_status(self.db, wo, MENUNGGU_INSPEKSI, f"Inspeksi tambahan oleh {penilik.nama_penilik}", email_admin)
            self._catat_admin(wo, email_admin)
            self.db.commit()
        return wo

    def lanjutkan_tanpa_inspeksi(self, id_work_order: str, email_admin: str = "admin@dpupr.surabaya.go.id"):
        wo = self._wo(id_work_order)
        if alasan_ditolak(wo, AKSI_TANPA_INSPEKSI) is None:
            wo.log_keputusan = f"Log Keputusan Manual - {email_admin}"
            ubah_status(self.db, wo, DISETUJUI, "Disetujui tanpa inspeksi tambahan", email_admin)
            self._catat_admin(wo, email_admin)
            self.db.commit()
        return wo
