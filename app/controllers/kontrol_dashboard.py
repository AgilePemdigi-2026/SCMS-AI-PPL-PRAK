from sqlalchemy.orm import Session
from app.models.entities import WorkOrder, Wilayah
from app.services.alur_status import (
    DALAM_PROSES, DITUGASKAN, DITUTUP, MENUNGGU_INSPEKSI, SELESAI, STATUS_FINAL, TERINSPEKSI,
)
from app.services.risk_scoring import skor_ambigu

# Map marker colours (design.md): risk band, and green for finished tickets.
WARNA_URGENT = "#DC2626"      # >= 8.0
WARNA_TINGGI = "#EA580C"      # 6.0 - 7.9
WARNA_BORDERLINE = "#D97706"  # 4.0 - 5.9
WARNA_RENDAH = "#16A34A"      # < 4.0, and every Selesai ticket
WARNA_DITUTUP = "#64748B"     # Ditutup (closed without repair, PRD 5.3 BR-4): not an active risk

# Same colours per BR-2 priority level, for priority badges outside the map.
WARNA_PRIORITAS = {"Urgent": WARNA_URGENT, "Tinggi": WARNA_TINGGI,
                   "Borderline": WARNA_BORDERLINE, "Rendah": WARNA_RENDAH}


def warna_prioritas(prioritas: str) -> str:
    return WARNA_PRIORITAS.get(prioritas, WARNA_RENDAH)

# "In field handling": an inspector or repair team is working on the ticket.
STATUS_PENANGANAN = (MENUNGGU_INSPEKSI, DITUGASKAN, TERINSPEKSI, DALAM_PROSES)


def warna_marker(wo: WorkOrder) -> str:
    if wo.status_work_order == SELESAI:
        return WARNA_RENDAH
    if wo.status_work_order == DITUTUP:
        return WARNA_DITUTUP
    skor = wo.risk_score or 0.0
    if skor >= 8.0:
        return WARNA_URGENT
    if skor >= 6.0:
        return WARNA_TINGGI
    if skor >= 4.0:
        return WARNA_BORDERLINE
    return WARNA_RENDAH

class KontrolDashboard:
    def __init__(self, db: Session):
        self.db = db

    def muat_dashboard(self):
        wo_list = self.db.query(WorkOrder).order_by(WorkOrder.risk_score.desc()).all()
        return self._format_hasil(wo_list)

    def filter_dashboard(self, wilayah: str = None, status: str = None, kategori: str = None):
        query = self.db.query(WorkOrder)

        if wilayah and wilayah != "Semua":
            wil_obj = self.db.query(Wilayah).filter(
                (Wilayah.nama_wilayah.ilike(f"%{wilayah}%")) | (Wilayah.id_wilayah == wilayah)
            ).first()
            if wil_obj:
                query = query.filter(WorkOrder.id_wilayah == wil_obj.id_wilayah)
            else:
                return {
                    "daftar_tiket": [],
                    "top_ticket_label": None,
                    "message": "Tidak ada laporan sesuai filter"
                }

        if status and status != "Semua":
            query = query.filter(WorkOrder.status_work_order == status)

        if kategori and kategori != "Semua":
            query = query.filter(WorkOrder.kategori_kerusakan.ilike(f"%{kategori}%"))

        wo_list = query.order_by(WorkOrder.risk_score.desc()).all()
        if not wo_list:
            return {
                "daftar_tiket": [],
                "top_ticket_label": None,
                "message": "Tidak ada laporan sesuai filter"
            }

        return self._format_hasil(wo_list)

    def _format_hasil(self, wo_list):
        wilayah_map = {w.id_wilayah: w.nama_wilayah for w in self.db.query(Wilayah).all()}

        hasil_tiket = []
        for wo in wo_list:
            # Tickets without stored coordinates are listed but get no map marker (lat/lng None).
            lat, lng = wo.latitude, wo.longitude

            hasil_tiket.append({
                "wo": wo,
                "nama_wilayah": wilayah_map.get(wo.id_wilayah, "Kota Surabaya"),
                "label_skor": f"{wo.id_work_order} ({wo.risk_score})",
                "lat": lat,
                "lng": lng,
                "warna_marker": warna_marker(wo),
                # ambiguous scores and manual-review tickets (PRD 5.3 BR-1) need the decision on
                # /verifikasi, not a one-click approve
                "ambigu": skor_ambigu(wo.risk_score) or wo.perlu_tinjauan_manual,
                "tinjauan_manual": wo.perlu_tinjauan_manual,
            })

        top_label = hasil_tiket[0]["label_skor"] if hasil_tiket else None
        return {
            "has_color_gradation": True,
            "daftar_tiket": hasil_tiket,
            "top_ticket_label": top_label,
            "message": None
        }

    @staticmethod
    def ringkasan_kpi(wo_list) -> dict:
        """KPI cards, counted from the same tickets as the (filtered) table.
        aktif = penanganan + other active tickets (not yet verified/assigned).
        Ditutup (PRD 5.3 BR-4) is final: neither active nor Selesai, and left out of the
        completion percentage."""
        total = len(wo_list)
        aktif = [w for w in wo_list if w.status_work_order not in STATUS_FINAL]
        selesai = sum(1 for w in wo_list if w.status_work_order == SELESAI)
        ditutup = sum(1 for w in wo_list if w.status_work_order == DITUTUP)
        dihitung = total - ditutup
        return {
            "total": total,
            "aktif": len(aktif),
            "urgent": sum(1 for w in aktif if (w.risk_score or 0.0) >= 8.0),
            "penanganan": sum(1 for w in aktif if w.status_work_order in STATUS_PENANGANAN),
            "belum_ditangani": sum(1 for w in aktif if w.status_work_order not in STATUS_PENANGANAN),
            "selesai": selesai,
            "ditutup": ditutup,
            "persen_selesai": round(selesai / dihitung * 100, 1) if dihitung else 0.0,
        }
