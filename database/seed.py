# database/seed.py
from passlib.context import CryptContext
from app.database import SessionLocal, engine, Base
from app.models.entities import (
    Warga, Admin, Wilayah, PenilikJalan, WorkOrder, Laporan
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def seed_data():
    # 1. Buat ulang semua tabel
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    hashed_pw = pwd_context.hash("password123")

    # 2. Seed Wilayah (Sesuai Skenario UC-G & UC-H)
    wilayah_list = [
        Wilayah(id_wilayah="WIL-01", nama_wilayah="Wilayah Gubeng"),
        Wilayah(id_wilayah="WIL-02", nama_wilayah="Wilayah Benowo"),
        Wilayah(id_wilayah="WIL-03", nama_wilayah="Wonokromo"),
    ]
    db.add_all(wilayah_list)

    # 3. Seed Akun Warga (Sesuai Mockup Citizen Home & Skenario UC-K)
    warga_list = [
        Warga(
            id_warga="USR-01",
            nik="3578010101900001",  # <-- Tambahkan NIK Warga 1
            nama_warga="Bpk. Tri Wahyudi",
            email="tri.wahyudi@gmail.com",
            no_hp="0812xxxxxxx", # Persis skenario BDD UC-K
            password_hash=hashed_pw,
            is_active=True
        ),
        Warga(
            id_warga="USR-02",
            nik="3578010101900002",  # <-- Tambahkan NIK Warga 2
            nama_warga="Warga Nonaktif",
            email="nonaktif@gmail.com",
            no_hp="0899xxxxxxx",
            password_hash=hashed_pw,
            is_active=False # Untuk test skenario akun tidak aktif UC-K
        )
    ]
    db.add_all(warga_list)

    # 4. Seed Akun Admin & Kepala Bidang (Sesuai Mockup & Skenario UC-B, UC-K)
    admin_list = [
        Admin(
            id_admin="ADM-01",
            nama_admin="Ir. Hendra Kusuma, S.T., M.Eng.",
            email_admin="admin@dpupr.surabaya.go.id", # Persis skenario BDD UC-B & UC-K
            password_hash=hashed_pw,
            is_kepala_bidang=False,
            is_active=True
        ),
        Admin(
            id_admin="ADM-02",
            nama_admin="Ir. H. Bambang Soeprapto, M.T.",
            email_admin="kabid@dpupr.surabaya.go.id",
            password_hash=hashed_pw,
            is_kepala_bidang=True,
            is_active=True
        )
    ]
    db.add_all(admin_list)

    # 5. Seed Penilik Jalan (Sesuai Skenario UC-G & UC-B: Budi Santoso di Wilayah Gubeng)
    # Catatan: Wilayah Benowo (WIL-02) sengaja TIDAK diberi petugas tersedia untuk test skenario "No Penilik Jalan Available"
    penilik_list = [
        PenilikJalan(
            id_penilik="PNL-01",
            id_wilayah="WIL-01", # Wilayah Gubeng
            nama_penilik="Budi Santoso",
            email_penilik="budi.santoso@dpupr.surabaya.go.id",
            password_hash=hashed_pw,
            status_ketersediaan="Tersedia"
        )
    ]
    db.add_all(penilik_list)

    # 6. Seed Work Order / Tiket (Sesuai Skenario UC-A, UC-B, UC-C, UC-G, UC-H)
    wo_list = [
        # Tiket utama untuk test Verifikasi (UC-B), Penugasan (UC-G), dan Dashboard (UC-H)
        WorkOrder(
            id_work_order="REP-2026-00341",
            id_wilayah="WIL-01", # Wilayah Gubeng
            kategori_kerusakan="Jalan Berlubang",
            lokasi_jalan="Jl. Sudirman No. 45, Surabaya",
            severity_score_kasus=8.4,
            risk_score=8.4,
            prioritas="Urgent",
            status_work_order="Disetujui", # Siap ditugaskan di UC-G
            sla_rekomendasi="24 jam"
        ),
        # Tiket skor ambigu/borderline untuk test UC-B & UC-D
        WorkOrder(
            id_work_order="REP-2026-00355",
            id_wilayah="WIL-01",
            kategori_kerusakan="Jalan Berlubang",
            lokasi_jalan="Jl. Raya Gubeng No. 45",
            severity_score_kasus=5.1,
            risk_score=5.1,
            prioritas="Borderline",
            status_work_order="Dilaporkan",
            sla_rekomendasi="48 jam"
        ),
        # Tiket di Wilayah Benowo (tanpa penilik jalan tersedia) untuk test UC-G Scenario 2
        WorkOrder(
            id_work_order="REP-2026-00360",
            id_wilayah="WIL-02", # Wilayah Benowo
            kategori_kerusakan="Jalan Amblas",
            lokasi_jalan="Jl. Raya Benowo No. 10",
            severity_score_kasus=7.5,
            risk_score=7.5,
            prioritas="Tinggi",
            status_work_order="Disetujui",
            sla_rekomendasi="24 jam"
        ),
        # Tiket selesai untuk test Duplikat (UC-A) & Rating (UC-C)
        WorkOrder(
            id_work_order="REP-2026-00298",
            id_wilayah="WIL-01",
            kategori_kerusakan="Jalan Berlubang",
            lokasi_jalan="Jl. Sudirman No. 45, Surabaya",
            severity_score_kasus=8.0,
            risk_score=8.0,
            prioritas="Urgent",
            status_work_order="Selesai"
        )
    ]
    db.add_all(wo_list)

    # 7. Seed Laporan Warga terkait tiket di atas
    laporan_list = [
        Laporan(
            id_laporan="LAP-001",
            id_work_order="REP-2026-00341",
            id_warga="USR-01",
            id_wilayah="WIL-01",
            deskripsi="Lubang besar di jalur kiri, dalam ±15cm",
            url_foto="static/uploads/jalan_berlubang_sudirman.jpg",
            lokasi_teks="Jl. Sudirman No. 45, Surabaya",
            severity_score=8.4,
            status="Disetujui"
        ),
        Laporan(
            id_laporan="LAP-002",
            id_work_order="REP-2026-00298",
            id_warga="USR-01",
            id_wilayah="WIL-01",
            deskripsi="Jalan berlubang dekat lampu merah Sudirman",
            url_foto="static/uploads/jalan_berlubang_sudirman_lama.jpg",
            lokasi_teks="Jl. Sudirman No. 45, Surabaya",
            severity_score=8.0,
            status="Selesai"
        )
    ]
    db.add_all(laporan_list)

    db.commit()
    db.close()
    print("✅ Database berhasil dibuat dan diisi dengan Data Mockup & Skenario BDD!")

if __name__ == "__main__":
    seed_data()