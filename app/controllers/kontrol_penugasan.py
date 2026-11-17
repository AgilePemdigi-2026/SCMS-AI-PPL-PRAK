from datetime import date
from sqlalchemy.orm import Session
from app.models.entities import Inspeksi, Perbaikan, WorkOrder, PenilikJalan, Wilayah
from app.services.alur_status import (
    BOLEH_MENUNGGU_PENUGASAN, DALAM_PROSES, DILAPORKAN, DITUGASKAN, MENUNGGU_INSPEKSI, MENUNGGU_PENUGASAN,
    DITUTUP, SELESAI, SIAP_PENUGASAN, TERINSPEKSI, ubah_status,
)

# An inspector is already working on the ticket: assigned (UC-G) or chosen for an extra inspection (UC-B).
STATUS_BERPENILIK = (MENUNGGU_INSPEKSI, DITUGASKAN)
# Field work by an inspector or repair team has started or is about to.
STATUS_DIKERJAKAN = (MENUNGGU_INSPEKSI, DITUGASKAN, TERINSPEKSI, DALAM_PROSES)


def sudah_ditugaskan(wo: WorkOrder) -> bool:
    return wo.status_work_order in STATUS_BERPENILIK and bool(wo.id_penilik)


def cari_penilik(db: Session, pilihan: str, id_wilayah: str, hanya_tersedia: bool = False):
    """Resolve an inspector chosen in a form by ID (preferred, names can repeat) or by name."""
    if not pilihan:
        return None
    q = db.query(PenilikJalan).filter_by(id_wilayah=id_wilayah, is_active=True)
    if hanya_tersedia:
        q = q.filter_by(status_ketersediaan="Tersedia")
    return (q.filter(PenilikJalan.id_penilik == pilihan).first()
            or q.filter(PenilikJalan.nama_penilik == pilihan).order_by(PenilikJalan.id_penilik).first())


def label_penilik(p: PenilikJalan) -> str:
    return f"{p.nama_penilik} ({p.nip})" if p.nip else p.nama_penilik

class KontrolPenugasan:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def ringkasan_kpi(wo_list) -> dict:
        """Work Order cards, counted from the same (filtered) list as the table.
        The groups split the total: belum_verifikasi + siap + dikerjakan + selesai + ditutup + lainnya == total.
        Ditutup (PRD 5.3 BR-4) is final but is not counted as Selesai."""
        hasil = {"total": len(wo_list), "belum_verifikasi": 0, "siap": 0, "dikerjakan": 0, "selesai": 0,
                 "ditutup": 0, "lainnya": 0}
        for wo in wo_list:
            if wo.status_work_order == SELESAI:
                hasil["selesai"] += 1
            elif wo.status_work_order == DITUTUP:
                hasil["ditutup"] += 1
            elif wo.status_work_order == DILAPORKAN:
                hasil["belum_verifikasi"] += 1
            elif wo.status_work_order in SIAP_PENUGASAN and not sudah_ditugaskan(wo):
                hasil["siap"] += 1          # the panel shows the "Tugaskan Penilik Jalan" form
            elif wo.status_work_order in STATUS_DIKERJAKAN:
                hasil["dikerjakan"] += 1    # Menunggu Inspeksi / Ditugaskan / Terinspeksi / Dalam Proses
            else:
                hasil["lainnya"] += 1       # unknown status (old data)
        return hasil

    def get_semua_work_order(self, filter_wilayah: str = None, filter_status: str = None):
        query = self.db.query(WorkOrder)
        if filter_wilayah and filter_wilayah != "Semua":
            query = query.filter(WorkOrder.id_wilayah == filter_wilayah)
        if filter_status and filter_status != "Semua":
            query = query.filter(WorkOrder.status_work_order == filter_status)
            
        wo_list = query.order_by(WorkOrder.risk_score.desc()).all()
        
        hasil = []
        for wo in wo_list:
            wilayah = self.db.query(Wilayah).filter_by(id_wilayah=wo.id_wilayah).first()
            penilik = self.db.query(PenilikJalan).filter_by(id_penilik=wo.id_penilik).first() if wo.id_penilik else None
            penilik_tersedia = self.db.query(PenilikJalan).filter_by(
                id_wilayah=wo.id_wilayah,
                status_ketersediaan="Tersedia"
            ).all()
            
            hasil.append({
                "wo": wo,
                "nama_wilayah": wilayah.nama_wilayah if wilayah else "-",
                "nama_penilik": penilik.nama_penilik if penilik else "Belum Ditugaskan",
                "penilik_tersedia": [p.nama_penilik for p in penilik_tersedia]
            })
        return hasil

    def cek_ketersediaan_penilik(self, id_work_order: str):
        """Assignment panel data: ticket priority (no time target) and available inspectors."""
        wo = self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()
        if not wo:
            return None

        wilayah = self.db.query(Wilayah).filter_by(id_wilayah=wo.id_wilayah).first()
        penilik_tersedia = self.db.query(PenilikJalan).filter_by(
            id_wilayah=wo.id_wilayah,
            status_ketersediaan="Tersedia"
        ).all()

        # An assigned ticket (Ditugaskan, or Menunggu Inspeksi with its inspector) stays in
        # SIAP_PENUGASAN so the admin can swap the inspector, but the panel must show
        # "already assigned" instead of the first-assignment form.
        penilik_aktif = (self.db.query(PenilikJalan).filter_by(id_penilik=wo.id_penilik).first()
                         if wo.id_penilik else None)

        return {
            "sudah_ditugaskan": sudah_ditugaskan(wo),
            "penilik_ditugaskan": penilik_aktif.nama_penilik if penilik_aktif else None,
            # compared with the logged-in account's ID (names can repeat)
            "id_penilik_ditugaskan": wo.id_penilik,
            "tanggal_ditugaskan": wo.tanggal_ditugaskan,
            # Same pool tugaskan_penilik() accepts (Tersedia + active), minus the current inspector.
            "opsi_ganti_penilik": [(p.id_penilik, label_penilik(p)) for p in penilik_tersedia
                                   if p.id_penilik != wo.id_penilik and p.is_active],
            "id_work_order": wo.id_work_order,
            "kategori_kerusakan": wo.kategori_kerusakan,
            "lokasi_jalan": wo.lokasi_jalan,
            "prioritas": wo.prioritas,
            "risk_score": wo.risk_score,
            "status_work_order": wo.status_work_order,
            "nama_wilayah": wilayah.nama_wilayah if wilayah else "",
            "daftar_penilik": [p.nama_penilik for p in penilik_tersedia],
            "opsi_penilik": [(p.id_penilik, label_penilik(p)) for p in penilik_tersedia],
            "boleh_ditugaskan": wo.status_work_order in SIAP_PENUGASAN,
            "wo": wo,
            "inspeksi": self.db.query(Inspeksi).filter_by(id_work_order=wo.id_work_order)
                            .order_by(Inspeksi.id_inspeksi.desc()).first(),
            "riwayat_perbaikan": self.db.query(Perbaikan).filter_by(id_work_order=wo.id_work_order)
                                     .order_by(Perbaikan.waktu.desc()).all(),
        }

    def tugaskan_penilik(self, id_work_order: str, nama_penilik: str = None):
        wo = self.db.query(WorkOrder).filter_by(id_work_order=id_work_order).first()
        if not wo:
            return None
        if wo.status_work_order not in SIAP_PENUGASAN:
            return wo  # not verified yet, or field work already started/finished
        ada_tersedia = self.db.query(PenilikJalan).filter_by(
            id_wilayah=wo.id_wilayah, status_ketersediaan="Tersedia", is_active=True,
        ).first()

        if not ada_tersedia:
            # Park only tickets nobody is working on; never move an assigned ticket backwards.
            if wo.status_work_order in BOLEH_MENUNGGU_PENUGASAN:
                ubah_status(self.db, wo, MENUNGGU_PENUGASAN, "Tidak ada Penilik Jalan tersedia di wilayah ini")
                self.db.commit()
            return wo

        penilik = cari_penilik(self.db, nama_penilik, wo.id_wilayah, hanya_tersedia=True)
        if not penilik:
            return wo
        if sudah_ditugaskan(wo) and penilik.id_penilik == wo.id_penilik:
            return wo  # same inspector again: nothing changes
        wo.id_penilik = penilik.id_penilik
        wo.tanggal_ditugaskan = date.today()
        # Changing the inspector is always recorded and notified: Menunggu Inspeksi -> Ditugaskan,
        # or a same-status entry when the ticket was already Ditugaskan.
        ubah_status(self.db, wo, DITUGASKAN, f"Ditugaskan kepada {penilik.nama_penilik}",
                    catat_walau_sama=wo.status_work_order == DITUGASKAN)
        self.db.commit()
        return wo