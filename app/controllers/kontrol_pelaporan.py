import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import SUMBER_TEMUAN, SUMBER_WARGA, Laporan, PenilikJalan, Wilayah, WorkOrder
from app.services import penyimpanan, risk_scoring
from app.services.ai_service import KATEGORI_VALID, AIService, VisiYolo, get_ai_service
from app.services.alur_status import DILAPORKAN, catat_riwayat, kirim_notifikasi
from app.services.deduplikasi import cari_duplikat

POLA_ID_WORK_ORDER = r"REP-\d{4}-(\d+)"
PESAN_KOORDINAT_TIDAK_LENGKAP = "Koordinat lokasi tidak lengkap, latitude dan longitude harus diisi keduanya"
PESAN_PILIH_KATEGORI = "Pilih kategori kerusakan jalan: foto perlu tinjauan manual sehingga AI tidak memberi rekomendasi"
PESAN_TOKEN_TERPAKAI = "Formulir laporan ini sudah dipakai. Muat ulang halaman Buat Laporan lalu kirim kembali."
PANJANG_TOKEN_KIRIM = 40


def _nomor_berikutnya(nilai: list[str], pola: str) -> int:
    angka = [int(m.group(1)) for v in nilai if (m := re.fullmatch(pola, v or ""))]
    return max(angka, default=0) + 1


def normalisasi_token(token: Optional[str]) -> Optional[str]:
    """Form token of /lapor (hidden input token_kirim). Empty or missing = no idempotency check."""
    token = (token or "").strip()[:PANJANG_TOKEN_KIRIM]
    return token or None


def severity_laporan(kategori_final: str, kategori_ai: Optional[str], severity_ai: float) -> float:
    """AI severity when the citizen keeps the AI category, otherwise the chosen category's base value."""
    if kategori_final == kategori_ai:
        return severity_ai
    return VisiYolo.BASE_SEVERITY.get(kategori_final, severity_ai)


class KontrolPelaporan:
    def __init__(self, db: Session, ai: Optional[AIService] = None):
        self.db = db
        self.ai = ai or get_ai_service()

    # ---- helpers kept for the BDD step definitions --------------------------
    def validasi_foto(self, filename: str, file_size_mb: float, data: Optional[bytes] = None):
        hasil = self.ai.validasi_foto(filename, file_size_mb, data)
        return {"valid": hasil.valid, "message": hasil.message}

    def analisis_ai_cv(self, filename: str, data: Optional[bytes] = None):
        h = self.ai.analisis_foto(filename, data)
        return {
            "detected": h.detected,
            "message": h.message,
            "rekomendasi_kategori": h.rekomendasi_kategori,
            "severity_score": h.severity_score,
            "confidence": h.confidence,
            "sumber": h.sumber,
            "tinjauan_manual": h.tinjauan_manual,
        }

    # ---- ID generation -------------------------------------------------------
    def _id_work_order_baru(self) -> str:
        tahun = datetime.now(timezone.utc).year
        semua = [r[0] for r in self.db.query(WorkOrder.id_work_order).all()]
        nomor = _nomor_berikutnya(semua, POLA_ID_WORK_ORDER)
        return f"REP-{tahun}-{nomor:05d}"

    def _id_laporan_baru(self) -> str:
        # Citizen-facing tracking ID, e.g. LAP-2026-0001 (UC-C)
        return penyimpanan.id_berurutan(self.db, Laporan.id_laporan, "LAP")

    # ---- main flow (UC-A) ----------------------------------------------------
    def kirim_laporan(
        self,
        filename: str,
        file_size_mb: float,
        lokasi_jalan: str,
        deskripsi: str,
        kategori_pilihan: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        id_warga: str = "USR-01",
        id_wilayah: str = "WIL-01",
        foto_bytes: Optional[bytes] = None,
        sumber: str = SUMBER_WARGA,
        id_penilik_pencatat: Optional[str] = None,
        saat_tersimpan: Optional[Callable[[Laporan, WorkOrder], None]] = None,
        token_kirim: Optional[str] = None,
    ):
        """UC-A report flow, shared by citizen reports and inspector findings (PRD 5.3 "Temuan baru"):
        same photo validation and AI analysis (BR-1), Risk Score (BR-2) and deduplication (BR-3).
        A finding has sumber="Temuan Penilik", no citizen (id_warga=None) and the recording inspector
        in id_penilik_pencatat. `saat_tersimpan(laporan, work_order)` runs in the same transaction,
        right before the commit (used to record the finding on the inspected ticket).

        `token_kirim` makes a submit idempotent (double click on a slow YOLO server): when a report
        with the same token exists, no new report is made and the result points to that report.
        Two simultaneous requests are settled by the UNIQUE index on laporan.token_kirim."""
        token_kirim = normalisasi_token(token_kirim)
        if token_kirim:
            sudah_ada = self._hasil_token_terpakai(token_kirim, id_warga)
            if sudah_ada:
                return sudah_ada
        temuan = sumber == SUMBER_TEMUAN
        if temuan:
            id_warga = None
        pencatat = self.db.get(PenilikJalan, id_penilik_pencatat) if temuan and id_penilik_pencatat else None
        asal = f"Temuan penilik {pencatat.nama_penilik if pencatat else '-'}" if temuan else "Laporan warga"
        # Step 1: file format & size, checked against the real bytes when given (REQ-RPT-1)
        val = self.ai.validasi_foto(filename, file_size_mb, foto_bytes)
        if not val.valid:
            return {"success": False, "step": 1, "message": val.message}

        # Step 2: location (REQ-RPT-4)
        lokasi = (lokasi_jalan or "").strip()
        if not lokasi:
            return {"success": False, "step": 2, "message": "Lokasi kerusakan jalan wajib ditentukan"}
        if (latitude is None) != (longitude is None):
            return {"success": False, "step": 2, "message": PESAN_KOORDINAT_TIDAK_LENGKAP}
        if latitude is not None and longitude is not None:
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                return {"success": False, "step": 2, "message": "Koordinat lokasi tidak valid"}
        if not self.db.get(Wilayah, id_wilayah):
            return {"success": False, "step": 2, "message": "Wilayah rayon tidak valid"}

        # Step 3: damage detection & description (REQ-RPT-2, 3, 5, 6)
        cv = self.ai.analisis_foto(filename, foto_bytes)
        # PRD 5.3 BR-1: a valid photo the AI cannot classify is accepted for manual review;
        # only a missing photo (YOLO needs the bytes) still stops here.
        tinjauan_manual = cv.tinjauan_manual
        if not cv.detected and not tinjauan_manual:
            return {"success": False, "step": 3, "message": cv.message}
        deskripsi = (deskripsi or "").strip()
        if len(deskripsi) < 10:
            return {"success": False, "step": 3, "message": "Deskripsi laporan minimal harus terdiri dari 10 karakter"}

        kategori = kategori_pilihan if kategori_pilihan in KATEGORI_VALID else cv.rekomendasi_kategori
        if kategori not in KATEGORI_VALID:  # manual review: there is no AI category to fall back on
            return {"success": False, "step": 3, "message": PESAN_PILIH_KATEGORI}
        # PRD BR-2: the AI severity only describes the AI's category. When the citizen picks
        # another category, use that category's base severity (reviewed later by an officer).
        severity = severity_laporan(kategori, cv.rekomendasi_kategori, cv.severity_score)
        lokasi_simpan = lokasi[:100]
        lokasi_teks = lokasi[:100]
        # real boxes only (YOLO); the simulation backend has none, and none are invented
        kotak_deteksi = json.dumps(cv.kotak) if cv.kotak else None

        # Step 4: spatial-semantic deduplication (REQ-RPT-7, REQ-RPT-8, PRD BR-3)
        duplikat = cari_duplikat(self.db, self.ai, kategori, lokasi, deskripsi, latitude, longitude)
        id_wo_duplikat = duplikat.work_order.id_work_order if duplikat else None

        def laporan_sama_sudah_ada(url_foto):
            # Checked inside every (re)try: after the IntegrityError of a simultaneous request with
            # the same token, the retry finds that request's report, drops the photo written for
            # this one (no orphan file) and returns the existing report.
            hasil = self._hasil_token_terpakai(token_kirim, id_warga) if token_kirim else None
            if hasil and foto_bytes is not None:
                penyimpanan.hapus_foto(url_foto)
            return hasil

        def gabungkan(url_foto):
            if (ada := laporan_sama_sudah_ada(url_foto)):
                return ada
            wo = self.db.get(WorkOrder, id_wo_duplikat)
            # Exposure = number of DIFFERENT citizens reporting this damage; the same
            # citizen reporting again is recorded but does not raise the priority.
            # An inspector's finding is not a reporter: it never raises the exposure (PRD 5.3).
            sudah_melapor = temuan or self.db.query(Laporan).filter_by(
                id_work_order=wo.id_work_order, id_warga=id_warga).first()
            if not sudah_melapor:
                # atomic increment, so two simultaneous merges both count
                (self.db.query(WorkOrder).filter_by(id_work_order=wo.id_work_order)
                 .update({WorkOrder.exposure_count: func.coalesce(WorkOrder.exposure_count, 1) + 1},
                         synchronize_session=False))
                self.db.refresh(wo)
            # AI severity of the case: the highest among its citizen reports (kept for comparison)
            wo.severity_ai = max(wo.severity_ai_awal or 0.0, severity)
            # PRD 5.3 BR-2: once a field inspection set the severity, it replaces the AI severity
            # for every later recompute; only the exposure of the new citizen changes the score.
            if wo.severity_lapangan is None:
                wo.severity_score_kasus = max(wo.severity_score_kasus or 0.0, severity)
            risk_scoring.terapkan_ke_work_order(wo)
            lap = Laporan(
                id_laporan=self._id_laporan_baru(),
                id_warga=id_warga,
                id_work_order=wo.id_work_order,
                id_wilayah=wo.id_wilayah,
                url_foto=url_foto,
                lokasi_teks=lokasi_teks,
                latitude=latitude,
                longitude=longitude,
                deskripsi=deskripsi,
                severity_score=severity,
                kotak_deteksi=kotak_deteksi,
                perlu_tinjauan_manual=tinjauan_manual,
                sumber=sumber,
                id_penilik_pencatat=pencatat.id_penilik if pencatat else None,
                status=wo.status_work_order,  # a report always shows its ticket's status
                token_kirim=token_kirim,
            )
            self.db.add(lap)
            catat_riwayat(self.db, wo, wo.status_work_order,
                          f"{asal} {lap.id_laporan} digabungkan ke tiket ini (jumlah pelapor: {wo.exposure_count})"
                          if temuan else
                          f"Laporan baru dari warga digabungkan ke tiket ini (jumlah pelapor: {wo.exposure_count})")
            # Team decision 5.9 no. 10: a report the AI recognises ends the manual review, but only
            # while the ticket is still being verified; after verification the label stays.
            if wo.perlu_tinjauan_manual and not tinjauan_manual and wo.status_work_order == DILAPORKAN:
                wo.perlu_tinjauan_manual = False
                catat_riwayat(self.db, wo, wo.status_work_order,
                              f"Tinjauan manual tidak lagi diperlukan: laporan {lap.id_laporan} terdeteksi AI")
            kirim_notifikasi(self.db, lap, "Laporan digabungkan",
                             f"Laporan Anda digabungkan dengan laporan serupa yang sudah aktif ({wo.id_work_order}).")
            if saat_tersimpan:
                saat_tersimpan(lap, wo)
            self.db.commit()
            return self._hasil(True, wo, cv, kategori, severity, latitude, longitude,
                               f"Laporan Anda telah digabungkan dengan laporan serupa yang sudah aktif ({wo.id_work_order})",
                               lap.id_laporan)

        def buat_baru(url_foto):
            if (ada := laporan_sama_sudah_ada(url_foto)):
                return ada
            # New Work Order (REQ-RPT-9)
            wo = WorkOrder(
                id_work_order=self._id_work_order_baru(),
                id_wilayah=id_wilayah,
                kategori_kerusakan=kategori,
                lokasi_jalan=lokasi_simpan,
                latitude=latitude,
                longitude=longitude,
                kelas_jalan=risk_scoring.KELAS_JALAN_DEFAULT,
                severity_score_kasus=severity,
                severity_ai=severity,
                perlu_tinjauan_manual=tinjauan_manual,
                exposure_count=1,
                vulnerability_score=risk_scoring.VULNERABILITY_DEFAULT,
                status_work_order=DILAPORKAN,
            )
            risk_scoring.terapkan_ke_work_order(wo)
            self.db.add(wo)
            self.db.flush()
            lap = Laporan(
                id_laporan=self._id_laporan_baru(),
                id_warga=id_warga,
                id_work_order=wo.id_work_order,
                id_wilayah=id_wilayah,
                url_foto=url_foto,
                lokasi_teks=lokasi_teks,
                latitude=latitude,
                longitude=longitude,
                deskripsi=deskripsi,
                severity_score=severity,
                kotak_deteksi=kotak_deteksi,
                perlu_tinjauan_manual=tinjauan_manual,
                sumber=sumber,
                id_penilik_pencatat=pencatat.id_penilik if pencatat else None,
                status=DILAPORKAN,
                token_kirim=token_kirim,
            )
            self.db.add(lap)
            catat_riwayat(self.db, wo, DILAPORKAN, f"{asal} diterima sistem")
            kirim_notifikasi(self.db, lap, "Laporan diterima",
                             f"Laporan Anda diterima dengan nomor tiket {wo.id_work_order}.")
            if saat_tersimpan:
                saat_tersimpan(lap, wo)
            self.db.commit()
            return self._hasil(False, wo, cv, kategori, severity, latitude, longitude,
                               f"Laporan berhasil dikirim dengan nomor tiket {wo.id_work_order}", lap.id_laporan)

        langkah = gabungkan if duplikat else buat_baru
        try:
            if foto_bytes is None:
                # No bytes (BDD steps / scripts calling the controller directly): no file is
                # written, only a reference to the original name is kept.
                url_nama = f"static/uploads/{Path(filename).name}"[:255]
                return penyimpanan.dengan_coba_ulang(self.db, lambda: langkah(url_nama))
            # The photo is written first and deleted again if the database write fails (no orphans).
            return penyimpanan.tulis_dengan_foto(self.db, foto_bytes, val.format_gambar or val.ekstensi, langkah)
        except IntegrityError:
            self.db.rollback()
            return {"success": False, "step": 4, "message": "Gagal menerbitkan nomor tiket, silakan coba lagi"}

    def _hasil_token_terpakai(self, token_kirim: str, id_warga: Optional[str]) -> Optional[dict]:
        """Result for a form token that was already used, or None when the token is new.
        Same keys as a normal success, so /lapor shows the same result card again."""
        lap = self.db.query(Laporan).filter_by(token_kirim=token_kirim).first()
        if not lap:
            return None
        if lap.id_warga != id_warga:  # a token is random per form; never show another citizen's report
            return {"success": False, "step": 4, "message": PESAN_TOKEN_TERPAKAI}
        wo = lap.work_order
        pertama = (self.db.query(Laporan.id_laporan).filter_by(id_work_order=wo.id_work_order)
                   .order_by(Laporan.tanggal_lapor, Laporan.id_laporan).first())
        is_duplikat = bool(pertama and pertama[0] != lap.id_laporan)
        pesan = (f"Laporan Anda telah digabungkan dengan laporan serupa yang sudah aktif ({wo.id_work_order})"
                 if is_duplikat else f"Laporan berhasil dikirim dengan nomor tiket {wo.id_work_order}")
        kategori = wo.kategori_kerusakan
        return {
            "success": True,
            "id_laporan": lap.id_laporan,
            "is_duplicate": is_duplikat,
            "ticket_id": wo.id_work_order,
            "status_work_order": wo.status_work_order,
            "exposure_count": wo.exposure_count,
            "risk_score": wo.risk_score,
            "prioritas": wo.prioritas,
            # the AI output of the first submit is not stored; the report keeps its own severity
            "rekomendasi_kategori": None if lap.perlu_tinjauan_manual else kategori,
            "kategori_final": kategori,
            "severity_score": lap.severity_score,
            "confidence": None,
            "mode_ai": self.ai.mode_cv,
            "perlu_tinjauan_manual": bool(lap.perlu_tinjauan_manual),
            "koordinat": (f"{lap.latitude:.5f}, {lap.longitude:.5f}"
                          if lap.latitude is not None and lap.longitude is not None else "-"),
            "message": pesan,
            "token_sudah_dipakai": True,
        }

    def _hasil(self, is_duplikat, wo, cv, kategori, severity, lat, lng, pesan, id_laporan):
        return {
            "success": True,
            "id_laporan": id_laporan,
            "is_duplicate": is_duplikat,
            "ticket_id": wo.id_work_order,
            "status_work_order": wo.status_work_order,
            "exposure_count": wo.exposure_count,
            "risk_score": wo.risk_score,
            "prioritas": wo.prioritas,
            "rekomendasi_kategori": cv.rekomendasi_kategori,
            "kategori_final": kategori,
            "severity_score": severity,
            "confidence": cv.confidence,
            "mode_ai": cv.sumber,
            "perlu_tinjauan_manual": cv.tinjauan_manual,
            "koordinat": f"{lat:.5f}, {lng:.5f}" if lat is not None and lng is not None else "-",
            "message": pesan,
        }
