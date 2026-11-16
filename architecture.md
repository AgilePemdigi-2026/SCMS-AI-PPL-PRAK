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
│                   BUSINESS LOGIC LAYER (11 CONTROLLERS)                    │
│  Sprint 1:                              Sprint 2:                          │
│  • KontrolAutentikasi (UC-K)            • KontrolLacak       (UC-C & UC-J) │
│  • KontrolPelaporan   (UC-A)            • KontrolMasterData  (UC-D)        │
│  • KontrolVerifikasi  (UC-B)            • KontrolInspeksi    (UC-E)        │
│  • KontrolPenugasan   (UC-G)            • KontrolPenanganan  (UC-F)        │
│  • KontrolDashboard   (UC-H)            • KontrolNotifikasi  (UC-I)        │
│                                         • KontrolLaporanKinerja (UC-L)     │
└──────────────────┬──────────────────────────────────┬──────────────────────┘
                   │                                  │
                   ▼                                  ▼
┌──────────────────────────────────────┐   ┌─────────────────────────────────┐
│       DOMAIN SERVICES LAYER          │   │    DATA ACCESS LAYER (MODEL)    │
│  • ai_service.py (Simulasi/YOLOv8/ST)│   │  • SQLAlchemy ORM Entities      │
│  • deduplikasi.py (15m / 50m + NLP)  │   │    (app/models/entities.py)     │
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
3. **Business Logic Layer (11 Controllers):**
   - **Sprint 1:** `KontrolAutentikasi` (UC-K), `KontrolPelaporan` (UC-A), `KontrolVerifikasi` (UC-B), `KontrolPenugasan` (UC-G), `KontrolDashboard` (UC-H).
   - **Sprint 2:** `KontrolLacak` (UC-C & UC-J), `KontrolMasterData` (UC-D), `KontrolInspeksi` (UC-E), `KontrolPenanganan` (UC-F), `KontrolNotifikasi` (UC-I), `KontrolLaporanKinerja` (UC-L).
4. **Domain Services Layer (`app/services/`):**
   - `ai_service.py` (Validasi bytes foto JPEG/PNG <= 10MB, CV Simulasi/YOLOv8 v4 dengan ambang confidence per kelas dari `model_config.json` dan kotak deteksi, NLP Leksikal/Sentence-Transformers).
   - `deduplikasi.py` (Deduplikasi dua tingkat, jarak Haversine terhadap WorkOrder aktif berkategori sama: <= 15 m langsung duplikat tanpa cek deskripsi; > 15–50 m wajib kemiripan deskripsi >= ambang NLP; > 50 m bukan duplikat. Mengembalikan `KandidatDuplikat` dengan `dasar` penggabungan).
   - `risk_scoring.py` (Formula Risk Score BR-2, klasifikasi tingkat prioritas tanpa target waktu (SLA dihapus atas masukan asisten dosen), serta `skor_ambigu()` = Borderline `4.0 <= skor < 6.0` yang dipakai Verifikasi dan Dashboard).
   - `alur_status.py` (Transisi status Compare-and-Set atomik sesuai `TRANSISI_SAH`, pencegahan status mundur, log `RiwayatStatus`, dan `Notifikasi` otomatis — satu per warga pelapor unik per perubahan status. Inspeksi hanya dari `Ditugaskan` / `Menunggu Inspeksi` oleh penilik yang ditugaskan; `Disetujui` wajib ditugaskan dulu).
   - `penyimpanan.py` (Penyimpanan file aman dengan auto-cleanup saat rollback dan auto-retry saat ID bentrok).
5. **Data Access Layer (Model):** SQLAlchemy 2.0 ORM (`app/models/entities.py`) dengan 11 entitas tabel dan auto-migration (`pastikan_kolom_terbaru()` di `app/database.py`).

## 2. Tumpukan Teknologi (Technology Stack)
| Lapisan (Layer) | Teknologi / Pustaka | Peran & Justifikasi Teknis |
| :--- | :--- | :--- |
| **Web Framework & Auth** | FastAPI, Uvicorn, Starlette SessionMiddleware, itsdangerous, passlib[bcrypt] | HTTP routing, form parsing, signed session cookie (`SCMS_SECRET_KEY`), bcrypt password hashing, dan RBAC 4 peran. |
| **Template Engine & UI** | Jinja2 & Tailwind CSS | Server-Side Rendering dengan shared layout (`_layout.html`) dan badge notifikasi belum dibaca. |
| **Geospatial & Mapping** | Leaflet.js 1.9.4, OpenStreetMap, Nominatim API | Visualisasi titik kerusakan jalan, lingkaran heatmap severity, serta Forward & Reverse Geocoding. |
| **ORM & Database** | SQLAlchemy 2.0, PostgreSQL (`psycopg2-binary`), SQLite | Pemetaan 11 tabel ORM, menggunakan SQLite terpisah (`scms_test.db`) saat pengujian otomatis. |
| **AI Pipeline (CV & NLP)** | Pillow, YOLOv8 v4 (`ultralytics` + `model_config.json`), Sentence-Transformers | Validasi foto asli, deteksi kerusakan jalan dengan ambang per kelas & kotak deteksi, dan kemiripan semantik deskripsi. |
| **Automated Testing** | Pytest, Pytest-BDD, Selenium WebDriver, FastAPI TestClient | Menjalankan 350 tes otomatis (31 skenario BDD + 3 E2E Selenium + 316 fast integration tests). |

## 3. Lapisan Model & Entitas (`app/models/entities.py` — 11 Tabel)
1. **`Warga` (`warga`):** `id_warga` (PK), `nik`, `nama_warga`, `email`, `no_hp`, `password_hash`, `alamat_domisili`, `is_active`.
2. **`Admin` (`admin`):** `id_admin` (PK), `nama_admin`, `email_admin`, `password_hash`, `is_kepala_bidang`, `is_active`.
3. **`Wilayah` (`wilayah`):** `id_wilayah` (PK), `nama_wilayah`, `kecamatan`.
4. **`PenilikJalan` (`penilik_jalan`):** `id_penilik` (PK), `id_wilayah` (FK), `nip` (18 digit unik), `nama_penilik`, `email_penilik`, `password_hash`, `status_ketersediaan` (`Tersedia`/`Penuh`/`Cuti`), `is_active`.
5. **`WorkOrder` (`work_order`):** `id_work_order` (PK), `id_admin` (FK), `id_penilik` (FK), `id_wilayah` (FK), `kategori_kerusakan`, `lokasi_jalan`, `latitude`, `longitude`, `severity_score_kasus`, `exposure_count`, `vulnerability_score`, `kelas_jalan` (default `Kolektor`), `risk_score`, `prioritas` (default `Rendah`), `status_work_order`, `sla_rekomendasi` (**usang/deprecated**: SLA dihapus, kolom tidak lagi diisi/dibaca dan dipertahankan hanya agar tidak perlu migrasi), `log_keputusan`, `nomor_spk` (unik), `tim_pelaksana`, `tanggal_ditugaskan`, `tanggal_selesai`.
6. **`Laporan` (`laporan`):** `id_laporan` (PK, format `LAP-YYYY-XXXX`), `id_work_order` (FK), `id_warga` (FK), `id_wilayah` (FK), `deskripsi`, `url_foto`, `lokasi_teks`, `latitude`, `longitude`, `severity_score`, `status`, `tanggal_lapor`. `kotak_deteksi` (TEXT JSON, nullable; kotak deteksi YOLO asli saat laporan dikirim, ditambahkan lewat `pastikan_kolom_terbaru()`; NULL untuk laporan lama & mode simulasi; dibaca lewat properti tervalidasi `daftar_kotak`).
7. **`Inspeksi` (`inspeksi`):** `id_inspeksi` (PK), `id_laporan` (FK), `id_penilik` (FK), `dimensi_kerusakan`, `rekomendasi`, `catatan_teknis`, `hasil_temuan`, `url_foto_temuan`, `tanggal_inspeksi`.
8. **`Perbaikan` (`perbaikan`):** `id_perbaikan` (PK), `id_work_order` (FK), `status_perbaikan`, `catatan`, `foto_sesudah`, `jadwal_lanjutan`, `tanggal_selesai`.
9. **`Notifikasi` (`notifikasi`):** `id_notifikasi` (PK), `id_laporan` (FK), `id_warga` (FK), `judul`, `pesan`, `status_baca`, `status_kirim`, `waktu_kirim`.
10. **`Rating` (`rating`):** `id_rating` (PK), `id_laporan` (FK, Unique), `nilai_bintang` (1-5), `komentar`, `tanggal_rating`. Aturan aplikasi: satu rating per (warga, tiket) — dicek di `KontrolLacak.simpan_rating()` lintas laporan warga yang digabung ke tiket yang sama.
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
| `GET/POST` | `/Dashboard`, `/Dashboard/{id}/quick-approve` | Staf / Admin (quick-approve hanya tiket `Dilaporkan` berskor jelas) | `KontrolDashboard`, `KontrolVerifikasi` | `UC-H` |
| `GET/POST` | `/verifikasi`, `/verifikasi/{id}/approve\|inspect\|skip-inspection` | Admin, Kabid | `KontrolVerifikasi` | `UC-B` |
| `GET/POST` | `/work-orders`, `/work-orders/{id}/assign` | Staf / Admin | `KontrolPenugasan` | `UC-G` |
| `POST` | `/work-orders/{id}/spk`, `/work-orders/{id}/progres` | Admin | `KontrolPenanganan` | `UC-F` |
| `GET/POST` | `/TugasLapangan`, `/TugasLapangan/{id}`, `/TugasLapangan/{id}/inspeksi\|progres` | Penilik Jalan (hanya tiket yang ditugaskan kepadanya) | `KontrolInspeksi`, `KontrolPenanganan` | `UC-E, UC-F` |
| `GET/POST` | `/master-data`, `/master-data/wilayah\|penilik` | Admin, Kabid (POST hanya Admin) | `KontrolMasterData` | `UC-D` |
| `POST` | `/master-data/penilik/{id}/ketersediaan` | Admin | `KontrolMasterData.ubah_ketersediaan()` (404 penilik tidak ada, 400 status tidak valid) | `UC-D` |
| `GET` | `/laporan-kinerja`, `/laporan-kinerja/unduh?jenis=wilayah\|tiket` | Admin, Kabid | `KontrolLaporanKinerja` | `UC-L` |

## 5. Integrasi Model AI YOLOv8 v4 (`app/services/ai_service.py` — `VisiYolo`)
1. **Konfigurasi Inferensi:** Bobot `SCMS_YOLO_WEIGHTS` (mis. `models/scms_v4/yolov8_infra_best.pt`) dibaca bersama `model_config.json` di folder yang sama (atau `SCMS_YOLO_CONFIG`) melalui `baca_konfigurasi_model()`. Kunci yang dipakai: `conf_per_class`, `infer_imgsz` (800), `nms_iou` (0,6), `agnostic_nms` (mati), dan `versi`. Tanpa file konfigurasi, dipakai satu ambang `conf_minimum` (0,35).
2. **Ambang Confidence per Kelas:** Nama kelas model dipetakan ke kategori SCMS (`petakan_kelas()`), lalu tiap deteksi disaring dengan `ambang(kategori)`: **Jalan Berlubang 0,26** dan **Retak Permukaan 0,20**. `predict()` dijalankan dengan ambang terendah, sehingga penyaringan per kelas terjadi setelahnya. Model v4 hanya mengenali dua kelas; Jalan Amblas tetap dipilih oleh warga/petugas.
3. **Kotak Deteksi:** Foto diputar tegak sesuai EXIF (`ImageOps.exif_transpose`) sebelum inferensi. Setiap deteksi yang lolos ambang dikembalikan sebagai kotak ternormalisasi (`kategori`, `confidence` %, `x1`, `y1`, `x2`, `y2` dalam 0–1), maksimal 20 kotak terurut confidence, melalui field `kotak` pada respons `/api/analisis-foto`.
4. **Severity AI:** Kategori terpilih adalah deteksi dengan skor `conf × (0,5 + luas)` tertinggi; `severity = min(10, BASE_SEVERITY[kategori] + 2,5 × cakupan × conf)`.
5. **Aturan Severity saat Kategori Diganti (PRD BR-2):** `severity_laporan()` di `KontrolPelaporan` memakai severity AI hanya jika `kategori_pilihan` warga sama dengan rekomendasi AI. Jika berbeda, dipakai nilai dasar `VisiYolo.BASE_SEVERITY` (Jalan Berlubang `7.0`, Jalan Amblas `7.5`, Retak Permukaan `4.5`) yang kemudian ditinjau petugas. Nilai dasar ini juga diekspos ke template sebagai global Jinja2 `severity_dasar`.

## 6. Modul Laporan Kinerja Infrastruktur (UC-L — `app/controllers/kontrol_laporan_kinerja.py`)
Revisi asisten dosen: konsep SLA dihapus (perbaikan jalan melewati birokrasi, target 24 jam s.d. 7x24 jam tidak realistis). Laporan ini mengukur durasi nyata tiap tahap, bukan kepatuhan pada target.
1. **Rekap (`rekap()`):** Memfilter tiket berdasarkan tanggal diterima (WIB, inklusif) dan wilayah, lalu menghasilkan KPI total, rekap per wilayah (wilayah tanpa tiket tetap tampil dengan nilai nol), rekap per prioritas (`Urgent`, `Tinggi`, `Borderline`, `Rendah`), daftar tiket aktif terurut umur, dan detail tiket terurut Risk Score tertinggi.
2. **Waktu Mulai & Penyelesaian:** Tiket dimulai pada entri pertama `RiwayatStatus` (cadangan: `tanggal_lapor` laporan warga paling awal) dan selesai pada entri `Selesai` pertama (cadangan: `tanggal_selesai`). Semua durasi dalam hari.
3. **Durasi per Tahap (`durasi_tahap()`, konstanta `TAHAP`):** Verifikasi (masuk → `Disetujui`/`Menunggu Inspeksi`), Penugasan (keputusan verifikasi → `Ditugaskan`), Inspeksi Lapangan (`Ditugaskan` → `Terinspeksi`), Penerbitan SPK (`Terinspeksi` → `Dalam Proses`), Perbaikan (`Dalam Proses` → `Selesai`), memakai waktu pertama kali tiap status dicapai. Tahap dihitung untuk sebuah tiket hanya bila kedua ujungnya tercapai dan urutannya benar; jalur inspeksi tambahan (`Menunggu Inspeksi` → `Terinspeksi`) tidak menghitung Penugasan dan Inspeksi Lapangan. Rata-rata ditampilkan keseluruhan dan per prioritas beserta jumlah tiket yang melewati tahap.
   **Umur Tiket Aktif:** hari sejak tiket diterima; `tahap_saat_ini` dipetakan dari status (`TAHAP_SAAT_INI`), dan `lama_di_tahap_hari` dihitung sejak entri riwayat terakhir. Rata-rata rating dihitung dari satu rating per warga unik per tiket (data lama ganda: rating pertama).
4. **Validasi & Pesan:** Format tanggal salah atau tanggal mulai setelah tanggal akhir ditolak dengan HTTP 400; periode tanpa tiket menampilkan `"Tidak ada data kinerja pada periode yang dipilih"`.
5. **Ekspor CSV:** `csv_per_wilayah()` (rata-rata durasi per tahap, rata-rata umur aktif, umur tertua) dan `csv_per_tiket()` (tahap saat ini, durasi per tahap, umur tiket aktif), tanpa kolom SLA, dengan nama berkas `laporan_kinerja_{jenis}_{periode}.csv`. Setiap sel teks melewati `aman_untuk_spreadsheet()` (teks berawalan `=`, `+`, `-`, `@`, tab, atau CR diberi awalan `'`) agar input warga tidak dieksekusi sebagai formula. Versi PDF dibuat lewat fitur cetak browser.
6. **Pengujian:** `tests/test_laporan_kinerja.py` (33 uji cepat: hak akses, durasi per tahap termasuk jalur inspeksi tambahan dan tahap yang belum dilalui, umur tiket aktif, filter, ekspor CSV, proteksi formula), `tests/test_tanpa_sla.py` (25 uji regresi penghapusan SLA), dan `uc_l_laporan_kinerja.feature` (2 skenario BDD).