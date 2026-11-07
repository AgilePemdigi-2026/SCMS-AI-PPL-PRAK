# System Architecture Document (`architecture.md`)
# SCMS-AI: Smart Complaint Management System — Dinas PUPR Kota Surabaya

**Versi Dokumen:** 2.0 (Sprint 1 & Sprint 2 Integrated)  
**Pola Arsitektur:** Layered MVC (Model-View-Controller) + Service-Oriented AI & Atomic Workflow Pipeline  
**Framework Utama:** FastAPI (Python 3.10+), SQLAlchemy ORM, Jinja2 Templates, Pytest-BDD & Selenium WebDriver  

---

## 1. Gambaran Umum Arsitektur (Architectural Overview)

**SCMS-AI** dibangun menggunakan arsitektur **Layered Model-View-Controller (MVC) + Service Layer** di atas *framework* **FastAPI**. Pemisahan tanggung jawab (*Separation of Concerns*) diterapkan secara ketat agar logika bisnis pada setiap *Controller* dan *Service* dapat diuji baik secara langsung (*fast unit/integration tests*) maupun melalui *End-to-End Browser Automation* (**Pytest-BDD + Selenium WebDriver**).

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER (VIEW)                           │
│  • Jinja2 HTML Templates (app/views/templates/*.html + _layout.html)       │
│  • Tailwind CSS (Responsive Government Enterprise UI)                      │
│  • Leaflet.js + OpenStreetMap + Nominatim Geocoding API (Client-Side GIS)  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ HTTP GET / POST + Signed Session Cookie
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                   ROUTING, SESSION & RBAC LAYER                            │
│  • FastAPI Application Router (app/main.py)                                │
│  • Session & Role Guard: app/auth.py (Depends(wajib_peran(...)))           │
│  • Dependency Injection: Database Session (Depends(get_db))                │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ Method Invocation
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                   BUSINESS LOGIC LAYER (10 CONTROLLERS)                    │
│  Sprint 1:                              Sprint 2:                          │
│  • KontrolAutentikasi (UC-K)            • KontrolLacak       (UC-C & UC-J) │
│  • KontrolPelaporan   (UC-A)            • KontrolMasterData  (UC-D)        │
│  • KontrolVerifikasi  (UC-B)            • KontrolInspeksi    (UC-E)        │
│  • KontrolPenugasan   (UC-G)            • KontrolPenanganan  (UC-F)        │
│  • KontrolDashboard   (UC-H)            • KontrolNotifikasi  (UC-I)        │
└──────────────────┬──────────────────────────────────┬──────────────────────┘
                   │                                  │
                   ▼                                  ▼
┌──────────────────────────────────────┐   ┌─────────────────────────────────┐
│       DOMAIN SERVICES LAYER          │   │    DATA ACCESS LAYER (MODEL)    │
│  • ai_service.py (Simulasi/YOLOv8/ST)│   │  • SQLAlchemy ORM Entities      │
│  • deduplikasi.py (50m Spatial+NLP)  │   │    (app/models/entities.py)     │
│  • risk_scoring.py (Formula BR-2)    │   │  • Auto-Migration Schema Sync   │
│  • alur_status.py (Atomic CAS + Log) │   │    (pastikan_kolom_terbaru)     │
│  • penyimpanan.py (Retry & File Safe)│   │  • PostgreSQL / SQLite Engine   │
└──────────────────────────────────────┘   └──────────────────┬──────────────┘
                                                              │
                                                              ▼
                                           ┌─────────────────────────────────┐
                                           │  RELATIONAL DATABASE (11 ENT.)  │
                                           │  PostgreSQL / SQLite + seed.py  │
                                           └─────────────────────────────────┘

1. **Presentation Layer (View):** Jinja2 HTML Templates (`app/views/templates/*.html` + `_layout.html`), Tailwind CSS, Leaflet.js + OpenStreetMap + Nominatim Geocoding API.
2. **Routing, Session & RBAC Layer:** FastAPI Application Router (`app/main.py`), Session & Role Guard (`app/auth.py` dengan `Depends(wajib_peran(...))`), Dependency Injection Database Session (`Depends(get_db)`).
3. **Business Logic Layer (10 Controllers):**
   - **Sprint 1:** `KontrolAutentikasi` (UC-K), `KontrolPelaporan` (UC-A), `KontrolVerifikasi` (UC-B), `KontrolPenugasan` (UC-G), `KontrolDashboard` (UC-H).
   - **Sprint 2:** `KontrolLacak` (UC-C & UC-J), `KontrolMasterData` (UC-D), `KontrolInspeksi` (UC-E), `KontrolPenanganan` (UC-F), `KontrolNotifikasi` (UC-I).
4. **Domain Services Layer (`app/services/`):**
   - `ai_service.py` (Validasi bytes foto JPEG/PNG <= 10MB, CV Simulasi/YOLOv8, NLP Leksikal/Sentence-Transformers).
   - `deduplikasi.py` (Deduplikasi spasial radius <= 50m Haversine + kemiripan semantik deskripsi).
   - `risk_scoring.py` (Formula Risk Score BR-2, klasifikasi prioritas & rekomendasi SLA).
   - `alur_status.py` (Transisi status Compare-and-Set atomik, pencegahan status mundur, log `RiwayatStatus`, dan pengiriman `Notifikasi` otomatis ke semua pelapor).
   - `penyimpanan.py` (Penyimpanan file aman dengan auto-cleanup saat rollback dan auto-retry saat ID bentrok).
5. **Data Access Layer (Model):** SQLAlchemy 2.0 ORM (`app/models/entities.py`) dengan 11 entitas tabel dan auto-migration (`pastikan_kolom_terbaru()` di `app/database.py`).

## 2. Tumpukan Teknologi (Technology Stack)
| Lapisan (Layer) | Teknologi / Pustaka | Peran & Justifikasi Teknis |
| :--- | :--- | :--- |
| **Web Framework & Auth** | FastAPI, Uvicorn, Starlette SessionMiddleware, itsdangerous, passlib[bcrypt] | HTTP routing, form parsing, signed session cookie (`SCMS_SECRET_KEY`), bcrypt password hashing, dan RBAC 4 peran. |
| **Template Engine & UI** | Jinja2 & Tailwind CSS | Server-Side Rendering dengan shared layout (`_layout.html`) dan badge notifikasi belum dibaca. |
| **Geospatial & Mapping** | Leaflet.js 1.9.4, OpenStreetMap, Nominatim API | Visualisasi titik kerusakan jalan, lingkaran heatmap severity, serta Forward & Reverse Geocoding. |
| **ORM & Database** | SQLAlchemy 2.0, PostgreSQL (`psycopg2-binary`), SQLite | Pemetaan 11 tabel ORM, menggunakan SQLite terpisah (`scms_test.db`) saat pengujian otomatis. |
| **AI Pipeline (CV & NLP)** | Pillow, YOLOv8 (`ultralytics`), Sentence-Transformers | Validasi foto asli, deteksi kerusakan jalan, dan kemiripan semantik deskripsi. |
| **Automated Testing** | Pytest, Pytest-BDD, Selenium WebDriver, FastAPI TestClient | Menjalankan 162 pengujian otomatis (29 skenario BDD + 3 E2E Selenium + 130 fast integration tests). |

## 3. Lapisan Model & Entitas (`app/models/entities.py` — 11 Tabel)
1. **`Warga` (`warga`):** `id_warga` (PK), `nik`, `nama_warga`, `email`, `no_hp`, `password_hash`, `alamat_domisili`, `is_active`.
2. **`Admin` (`admin`):** `id_admin` (PK), `nama_admin`, `email_admin`, `password_hash`, `is_kepala_bidang`, `is_active`.
3. **`Wilayah` (`wilayah`):** `id_wilayah` (PK), `nama_wilayah`, `kecamatan`.
4. **`PenilikJalan` (`penilik_jalan`):** `id_penilik` (PK), `id_wilayah` (FK), `nip` (18 digit unik), `nama_penilik`, `email_penilik`, `password_hash`, `status_ketersediaan` (`Tersedia`/`Bertugas`/`Cuti`), `is_active`.
5. **`WorkOrder` (`work_order`):** `id_work_order` (PK), `id_admin` (FK), `id_penilik` (FK), `id_wilayah` (FK), `kategori_kerusakan`, `lokasi_jalan`, `latitude`, `longitude`, `severity_score_kasus`, `exposure_count`, `vulnerability_score`, `kelas_jalan`, `risk_score`, `prioritas`, `status_work_order`, `sla_rekomendasi`, `log_keputusan`, `nomor_spk` (unik), `tim_pelaksana`, `tanggal_ditugaskan`, `tanggal_selesai`.
6. **`Laporan` (`laporan`):** `id_laporan` (PK, format `LAP-YYYY-XXXX`), `id_work_order` (FK), `id_warga` (FK), `id_wilayah` (FK), `deskripsi`, `url_foto`, `lokasi_teks`, `latitude`, `longitude`, `severity_score`, `status`, `tanggal_lapor`.
7. **`Inspeksi` (`inspeksi`):** `id_inspeksi` (PK), `id_laporan` (FK), `id_penilik` (FK), `dimensi_kerusakan`, `rekomendasi`, `catatan_teknis`, `hasil_temuan`, `url_foto_temuan`, `tanggal_inspeksi`.
8. **`Perbaikan` (`perbaikan`):** `id_perbaikan` (PK), `id_work_order` (FK), `status_perbaikan`, `catatan`, `foto_sesudah`, `jadwal_lanjutan`, `tanggal_selesai`.
9. **`Notifikasi` (`notifikasi`):** `id_notifikasi` (PK), `id_laporan` (FK), `id_warga` (FK), `judul`, `pesan`, `status_baca`, `status_kirim`, `waktu_kirim`.
10. **`Rating` (`rating`):** `id_rating` (PK), `id_laporan` (FK, Unique), `nilai_bintang` (1-5), `komentar`, `tanggal_ulasan`.
11. **`RiwayatStatus` (`riwayat_status`):** `id_riwayat` (PK), `id_work_order` (FK), `status`, `keterangan`, `waktu`.

## 4. Peta Routing & Endpoint HTTP (`app/main.py`)
| Method | URL Endpoint | Peran Diizinkan | Controller | Use Case |
| :--- | :--- | :--- | :--- | :--- |
| `GET/POST` | `/Login`, `/Register`, `/Logout` | Publik | `KontrolAutentikasi` | `UC-K` |
| `GET` | `/Beranda` | Warga | Query `Laporan` | `UC-A/C` |
| `GET/POST` | `/lapor`, `/api/analisis-foto` | Warga | `KontrolPelaporan`, `AIService` | `UC-A` |
| `GET` | `/lacak` | Warga | `KontrolLacak.cari_laporan_warga()` | `UC-C` |
| `POST` | `/lacak/{id_laporan}/rating` | Warga | `KontrolLacak.simpan_rating()` | `UC-J` |
| `GET/POST` | `/notifikasi`, `/notifikasi/{id}/buka`, `/notifikasi/baca-semua` | Warga | `KontrolNotifikasi` | `UC-I` |
| `GET/POST` | `/Dashboard`, `/Dashboard/{id}/quick-approve` | Staf / Admin | `KontrolDashboard`, `KontrolVerifikasi` | `UC-H` |
| `GET/POST` | `/verifikasi`, `/verifikasi/{id}/approve\|inspect\|skip-inspection` | Admin, Kabid | `KontrolVerifikasi` | `UC-B` |
| `GET/POST` | `/work-orders`, `/work-orders/{id}/assign` | Staf / Admin | `KontrolPenugasan` | `UC-G` |
| `POST` | `/work-orders/{id}/spk`, `/work-orders/{id}/progres` | Admin | `KontrolPenanganan` | `UC-F` |
| `GET/POST` | `/TugasLapangan`, `/TugasLapangan/{id}/inspeksi\|progres` | Penilik Jalan | `KontrolInspeksi`, `KontrolPenanganan` | `UC-E, UC-F` |
| `GET/POST` | `/master-data`, `/master-data/wilayah\|penilik` | Admin, Kabid | `KontrolMasterData` | `UC-D` |