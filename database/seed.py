from passlib.context import CryptContext
from app.database import SessionLocal, engine, Base
from app.models.entities import Warga, Admin, Wilayah, PenilikJalan, WorkOrder, Laporan

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def seed_data():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    hashed_pw = pwd_context.hash("password123")

    wilayah_list = [
        Wilayah(id_wilayah="WIL-01", nama_wilayah="Wilayah Gubeng"),
        Wilayah(id_wilayah="WIL-02", nama_wilayah="Wilayah Benowo"),
        Wilayah(id_wilayah="WIL-03", nama_wilayah="Wonokromo"),
    ]
    db.add_all(wilayah_list)

    warga_list = [
        Warga(id_warga="USR-01", nama_warga="Bpk. Tri Wahyudi", email="tri.wahyudi@gmail.com", no_hp="0812xxxxxxx", password_hash=hashed_pw, is_active=True),
        Warga(id_warga="USR-02", nama_warga="Warga Nonaktif", email="nonaktif@gmail.com", no_hp="0899xxxxxxx", password_hash=hashed_pw, is_active=False)
    ]
    db.add_all(warga_list)

    admin_list = [
        Admin(id_admin="ADM-01", nama_admin="Ir. Hendra Kusuma, S.T., M.Eng.", email_admin="admin@dpupr.surabaya.go.id", password_hash=hashed_pw, is_kepala_bidang=False, is_active=True),
        Admin(id_admin="ADM-02", nama_admin="Ir. H. Bambang Soeprapto, M.T.", email_admin="kabid@dpupr.surabaya.go.id", password_hash=hashed_pw, is_kepala_bidang=True, is_active=True)
    ]
    db.add_all(admin_list)

    penilik_list = [
        PenilikJalan(id_penilik="PNL-01", id_wilayah="WIL-01", nama_penilik="Budi Santoso", email_penilik="budi.santoso@dpupr.surabaya.go.id", password_hash=hashed_pw, status_ketersediaan="Tersedia")
    ]
    db.add_all(penilik_list)

    wo_list = [
        WorkOrder(id_work_order="REP-2026-00341", id_wilayah="WIL-01", kategori_kerusakan="Jalan Berlubang", lokasi_jalan="Jl. Sudirman No. 45, Surabaya", severity_score_kasus=8.4, risk_score=8.4, prioritas="Urgent", status_work_order="Disetujui", sla_rekomendasi="24 jam"),
        WorkOrder(id_work_order="REP-2026-00355", id_wilayah="WIL-01", kategori_kerusakan="Jalan Berlubang", lokasi_jalan="Jl. Raya Gubeng No. 45", severity_score_kasus=5.1, risk_score=5.1, prioritas="Borderline", status_work_order="Dilaporkan", sla_rekomendasi="48 jam"),
        WorkOrder(id_work_order="REP-2026-00360", id_wilayah="WIL-02", kategori_kerusakan="Jalan Amblas", lokasi_jalan="Jl. Raya Benowo No. 10", severity_score_kasus=7.5, risk_score=7.5, prioritas="Tinggi", status_work_order="Disetujui", sla_rekomendasi="24 jam"),
        WorkOrder(id_work_order="REP-2026-00298", id_wilayah="WIL-01", kategori_kerusakan="Jalan Berlubang", lokasi_jalan="Jl. Sudirman No. 45, Surabaya", severity_score_kasus=8.0, risk_score=8.0, prioritas="Urgent", status_work_order="Selesai")
    ]
    db.add_all(wo_list)

    laporan_list = [
        Laporan(id_laporan="LAP-001", id_work_order="REP-2026-00341", id_warga="USR-01", id_wilayah="WIL-01", deskripsi="Lubang besar di jalur kiri, dalam +-15cm", url_foto="static/uploads/jalan_berlubang_sudirman.jpg", lokasi_teks="Jl. Sudirman No. 45, Surabaya", severity_score=8.4, status="Disetujui"),
        Laporan(id_laporan="LAP-002", id_work_order="REP-2026-00298", id_warga="USR-01", id_wilayah="WIL-01", deskripsi="Jalan berlubang dekat lampu merah Sudirman", url_foto="static/uploads/jalan_berlubang_sudirman_lama.jpg", lokasi_teks="Jl. Sudirman No. 45, Surabaya", severity_score=8.0, status="Selesai")
    ]
    db.add_all(laporan_list)

    db.commit()
    db.close()
    print("Database berhasil di-seed dengan Data Mockup & Skenario BDD!")

if __name__ == "__main__":
    seed_data()
