# System Architecture Document (`architecture.md`)
# SCMS-AI: Smart Complaint Management System — Dinas PUPR Kota Surabaya

**Versi Dokumen:** 1.0  
**Pola Arsitektur:** Layered MVC (Model-View-Controller) + Service-Oriented AI Pipeline  
**Framework Utama:** FastAPI (Python 3.10+), SQLAlchemy ORM, Jinja2 Templates, Pytest-BDD  

---

## 1. Gambaran Umum Arsitektur (Architectural Overview)

**SCMS-AI** dibangun menggunakan arsitektur **Layered Model-View-Controller (MVC)** di atas *framework* **FastAPI**. Pemisahan tanggung jawab (*Separation of Concerns*) diterapkan secara ketat agar logika bisnis pada setiap *Controller* dapat diuji secara langsung oleh *test runner* **Pytest-BDD** maupun dipanggil melalui *HTTP Routing* untuk merender antarmuka pengguna (*Server-Side Rendering* dengan Jinja2 & klien geospasial Leaflet.js).

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER (VIEW)                           │
│  • Jinja2 HTML Templates (app/views/templates/*.html)                      │
│  • Tailwind CSS (Responsive Government UI)                                 │
│  • Leaflet.js + OpenStreetMap + Nominatim Geocoding API (Client-Side GIS)  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ HTTP GET / POST (Form Data & Query)
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      ROUTING & ENTRYPOINT LAYER                            │
│  • FastAPI Application Router (app/main.py)                                │
│  • Dependency Injection: Database Session (Depends(get_db))                │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ Method Invocation
                                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                   BUSINESS LOGIC LAYER (CONTROLLERS)                       │
│  • KontrolAutentikasi (UC-K)   • KontrolVerifikasi (UC-B)                  │
│  • KontrolPelaporan   (UC-A)   • KontrolPenugasan  (UC-G)                  │
│  • KontrolDashboard   (UC-H)   • (Sprint 2: Inspeksi, Progres, Notif, dll) │
└──────────────────┬──────────────────────────────────┬──────────────────────┘
                   │                                  │
                   ▼                                  ▼
┌──────────────────────────────────────┐   ┌─────────────────────────────────┐
│     AI & GEOSPATIAL PIPELINE         │   │    DATA ACCESS LAYER (MODEL)    │
│  • Computer Vision (YOLOv8-Infra)    │   │  • SQLAlchemy ORM Entities      │
│  • Semantic NLP (Sentence-Transf.)   │   │    (app/models/entities.py)     │
│  • Multi-Factor Risk Scoring Engine  │   │  • SQLite / PostgreSQL Engine   │
└──────────────────────────────────────┘   └──────────────────┬──────────────┘
                                                              │
                                                              ▼
                                           ┌─────────────────────────────────┐
                                           │  RELATIONAL DATABASE (10 PDM)   │
                                           │  scms_pupr.db + database/seed.py│
                                           └─────────────────────────────────┘
```

---

## 2. Tumpukan Teknologi (Technology Stack)

| Lapisan (Layer) | Teknologi / Pustaka | Peran & Justifikasi Teknis |
| :--- | :--- | :--- |
| **Web Framework** | **FastAPI** (`>=0.110.0`) & **Uvicorn** | Menangani *HTTP routing*, *form parsing* (`python-multipart`), *dependency injection* sesi basis data, dan eksekusi asinkron berkinerja tinggi. |
| **Template Engine & UI** | **Jinja2** & **Tailwind CSS** | Merender antarmuka HTML dinamis dari sisi server (*Server-Side Rendering*) dengan desain konsisten sesuai standar instansi pemerintah. |
| **Geospatial & Mapping** | **Leaflet.js 1.9.4**, **OpenStreetMap**, **Nominatim API** | Visualisasi sebaran titik kerusakan jalan, lingkaran *heatmap severity*, pencarian alamat jalan (*Forward Geocoding*), dan konversi titik koordinat ke alamat (*Reverse Geocoding*) tanpa biaya lisensi API berbayar. |
| **ORM & Database** | **SQLAlchemy 2.0** & **SQLite** | Memetakan 10 tabel *Physical Data Model* (PDM) ke objek Python. Menggunakan SQLite (`scms_pupr.db`) untuk portabilitas pengujian lokal dan siap dihubungkan ke PostgreSQL/MySQL untuk produksi. |
| **AI Pipeline (CV & NLP)** | **YOLOv8-Infra** & **Sentence-Transformers** *(Simulated/Service Layer)* | Ekstraksi fitur objek kerusakan jalan dari foto warga (*bounding box*, kategori, *severity score*) serta deteksi kemiripan semantik deskripsi laporan untuk deduplikasi tiket aktif. |
| **BDD Automated Testing** | **Pytest** (`>=8.0`) & **Pytest-BDD** (`>=7.0`) | Menjalankan skenario penerimaan fungsional berformat Gherkin (`.feature`) secara terotomatisasi terhadap lapisan *Controller* dan *Database*. |

---

## 3. Arsitektur Lapisan Aplikasi & Kontrak Komponen

### 3.1 Lapisan Konfigurasi Basis Data (`app/database.py`)
* Mengelola pembuatan `engine` SQLAlchemy (`sqlite:///./scms_pupr.db` dengan `check_same_thread=False`).
* Menyediakan pabrik sesi `SessionLocal` dan kelas dasar deklaratif `Base`.
* Menyediakan generator *dependency injection* `get_db()` yang menjamin setiap *request* HTTP mendapatkan sesi transaksi terisolasi dan ditutup secara otomatis (`db.close()`) setelah selesai.

### 3.2 Lapisan Model & Entitas (`app/models/entities.py`)
Merepresentasikan **10 tabel Physical Data Model (PDM)** beserta relasi *Foreign Key* dan `relationship()` dua arah:

```text
                  ┌──────────────┐
                  │   Wilayah    │ (WIL-01: Gubeng, WIL-02: Benowo, WIL-03: Wonokromo)
                  └──────┬───────┘
                         │ 1:N
         ┌───────────────┼───────────────────┐
         ▼               ▼                   ▼
┌─────────────────┐ ┌──────────────┐ ┌────────────────┐
│  PenilikJalan   │ │  WorkOrder   │ │    Laporan     │
└────────┬────────┘ └──────┬───────┘ └───────┬────────┘
         │                 │                 │
         │ 1:N             │ 1:N             │ N:1
         ▼                 ▼                 ▼
┌─────────────────┐ ┌──────────────┐ ┌────────────────┐
│    Inspeksi     │ │    Admin     │ │     Warga      │
└─────────────────┘ └──────────────┘ └───────┬────────┘
                                             │ 1:N
                                     ┌───────┴────────┐
                                     ▼                ▼
                              ┌──────────────┐ ┌──────────────┐
                              │  Notifikasi  │ │    Rating    │
                              └──────────────┘ └──────────────┘
                              (Serta entitas mandiri: KepalaBidang)
```

### 3.3 Lapisan Logika Bisnis / Controllers (`app/controllers/`)
Setiap Use Case memiliki kelas *Controller* mandiri yang menerima `db: Session` pada konstruktornya (`__init__`). *Controller* **tidak boleh** bergantung langsung pada objek `Request` HTTP agar dapat dipanggil langsung baik oleh `app/main.py` maupun oleh `tests/step_definitions/`.

1. **`KontrolAutentikasi` (`app/controllers/kontrol_autentikasi.py` — UC-K):**
   * `autentikasi(identifier: str, password: str) -> dict`: Memvalidasi input kosong, mencari kecocokan akun secara berurutan pada tabel `Warga` (via `no_hp`), `Admin` (via `email`), `PenilikJalan` (via `email`), dan `KepalaBidang` (via `email`), serta mengembalikan status keberhasilan, peran (*role*), URL pengalihan (`redirect_url`), dan pesan respons.
2. **`KontrolPelaporan` (`app/controllers/kontrol_pelaporan.py` — UC-A):**
   * `validasi_foto(filename: str, file_size_mb: float) -> dict`: Memeriksa ekstensi (`jpg/jpeg/png`) dan ukuran berkas ($\le 10.0\text{ MB}$).
   * `analisis_ai_cv(filename: str) -> dict`: Menjalankan deteksi objek jalan rusak, menolak objek non-jalan, serta mengembalikan rekomendasi kategori dan *severity score* awal.
   * `cek_duplikasi_otomatis(lokasi_jalan: str, kategori: str, deskripsi: str) -> WorkOrder | None`: Memeriksa keberadaan *Work Order* aktif di lokasi serupa yang memiliki kemiripan semantik.
   * `kirim_laporan(...) -> dict`: Mengorkestrasi alur 4 langkah pelaporan, menggabungkan laporan jika terdeteksi duplikat (`exposure_count += 1`), atau menerbitkan *Work Order* baru (`status_work_order = "Dilaporkan"`).
3. **`KontrolVerifikasi` (`app/controllers/kontrol_verifikasi.py` — UC-B):**
   * `muat_daftar_tiket() -> list[WorkOrder]`: Mengambil daftar tiket terurut dari `risk_score` tertinggi.
   * `lihat_detail_tiket(id_work_order: str) -> dict`: Mengevaluasi apakah skor risiko tiket berada di rentang ambigu ($4.0 \le \text{risk\_score} \le 6.0$ atau `prioritas == "Borderline"`), menentukan label opsi verifikasi (`"Butuh Verifikasi Lapangan"` vs `"Siap Disetujui"`), dan mengambil daftar Penilik Jalan di wilayah terkait.
   * `setujui_tiket(id_work_order: str) -> WorkOrder`: Mengubah status menjadi `"Disetujui"`.
   * `tugaskan_inspeksi_tambahan(id_work_order: str, nama_penilik: str) -> WorkOrder`: Mengubah status menjadi `"Menunggu Inspeksi"` dan mencatat entitas `Inspeksi`.
   * `lanjutkan_tanpa_inspeksi(id_work_order: str, email_admin: str) -> WorkOrder`: Mengubah status menjadi `"Disetujui"` dan mencatat audit trail pada `log_keputusan`.
4. **`KontrolPenugasan` (`app/controllers/kontrol_penugasan.py` — UC-G):**
   * `get_semua_work_order(wilayah: str, status: str) -> list[dict]`: Memuat daftar SPK dengan dukungan filter wilayah dan status.
   * `cek_sla_dan_ketersediaan_penilik(id_work_order: str) -> dict`: Mengambil rekomendasi SLA tiket dan menyaring `PenilikJalan` yang memiliki `id_wilayah` sesuai tiket serta `ketersediaan == True`.
   * `tugaskan_penilik(id_work_order: str, nama_penilik: str) -> WorkOrder`: Menetapkan Penilik Jalan dan mengubah status menjadi `"Ditugaskan"`, atau mengubahnya menjadi `"Menunggu Penugasan"` apabila tidak ada petugas yang tersedia.
5. **`KontrolDashboard` (`app/controllers/kontrol_dashboard.py` — UC-H):**
   * `muat_dashboard() -> dict`: Mengambil seluruh *Work Order* terurut dari `risk_score` tertinggi, memetakan titik koordinat geospasial Surabaya, dan menetapkan kode warna *marker* berdasarkan tingkat keparahan (`#DC2626` untuk $\ge 8.0$, `#EA580C` untuk $6.0 - 7.9$, `#D97706` untuk $< 6.0$).
   * `filter_dashboard(wilayah: str, status: str, kategori: str) -> dict`: Menyaring data peta dan tabel antrean prioritas, serta mengembalikan pesan `"Tidak ada laporan sesuai filter"` jika hasil penyaringan kosong.

---

## 4. Peta Routing & Endpoint HTTP (`app/main.py`)

| Method | URL Endpoint | Controller yang Dipanggil | Template View (`app/views/templates/`) | Use Case |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/` | Redirect ke `/Login` | - | Root |
| `GET` | `/Login`, `/login` | - | `login.html` | `UC-K` |
| `POST` | `/Login`, `/login` | `KontrolAutentikasi.autentikasi()` | Redirect sesuai Role / `login.html` | `UC-K` |
| `GET` | `/Beranda`, `/lapor` | - | `buat_laporan.html` | `UC-A` |
| `POST` | `/lapor` | `KontrolPelaporan.kirim_laporan()` | `buat_laporan.html` | `UC-A` |
| `GET` | `/Dashboard`, `/dashboard` | `KontrolDashboard.muat_dashboard()` / `filter_dashboard()` | `dashboard_prioritas.html` | `UC-H` |
| `POST` | `/Dashboard/{ticket_id}/quick-approve` | Update Status `WorkOrder` | `dashboard_prioritas.html` | `UC-H` |
| `GET` | `/verifikasi` | `KontrolVerifikasi.lihat_detail_tiket()` | `verifikasi_detail.html` | `UC-B` |
| `POST` | `/verifikasi/{ticket_id}/approve` | `KontrolVerifikasi.setujui_tiket()` | `verifikasi_detail.html` | `UC-B` |
| `POST` | `/verifikasi/{ticket_id}/inspect` | `KontrolVerifikasi.tugaskan_inspeksi_tambahan()` | `verifikasi_detail.html` | `UC-B` |
| `POST` | `/verifikasi/{ticket_id}/skip-inspection` | `KontrolVerifikasi.lanjutkan_tanpa_inspeksi()` | `verifikasi_detail.html` | `UC-B` |
| `GET` | `/work-orders` | `KontrolPenugasan.get_semua_work_order()` | `work_order_list.html` | `UC-G` |
| `POST` | `/work-orders/{ticket_id}/assign` | `KontrolPenugasan.tugaskan_penilik()` | `work_order_list.html` | `UC-G` |

---

## 5. Arsitektur Pengujian Otomatis (BDD Testing Architecture)

Pengujian sistem dirancang dengan pendekatan **Behavior-Driven Development (BDD)** menggunakan `pytest-bdd`:
1. **Isolasi Data Uji Deterministik (`database/seed.py`):**
   * Setiap *fixture* pengujian di dalam `tests/step_definitions/test_uc_*.py` memanggil fungsi `seed_data()` sebelum skenario dijalankan (`@pytest.fixture`).
   * Fungsi `seed_data()` melakukan `Base.metadata.drop_all(bind=engine)` diikuti `Base.metadata.create_all(bind=engine)`, lalu mengisi ulang data *master* (Wilayah Gubeng, Benowo, Wonokromo; akun Warga, Admin, Penilik Jalan, Kepala Bidang; serta tiket uji `REP-2026-00341`, `REP-2026-00298`, `REP-2026-00360`, dan `REP-2026-00355`).
   * Mekanisme ini menjamin tidak ada efek samping (*side-effect*) antar-skenario pengujian sehingga seluruh **17 skenario BDD** selalu menghasilkan hasil yang konsisten (`17 passed`).
2. **Pemetaan File Gherkin ke Step Definitions:**
   * `tests/features/uc_k_login.feature` $\leftrightarrow$ `tests/step_definitions/test_uc_k.py` (5 Skenario)
   * `tests/features/uc_a_buat_laporan.feature` $\leftrightarrow$ `tests/step_definitions/test_uc_a.py` (4 Skenario)
   * `tests/features/uc_b_verifikasi.feature` $\leftrightarrow$ `tests/step_definitions/test_uc_b.py` (4 Skenario)
   * `tests/features/uc_g_penugasan.feature` $\leftrightarrow$ `tests/step_definitions/test_uc_g.py` (2 Skenario)
   * `tests/features/uc_h_dashboard.feature` $\leftrightarrow$ `tests/step_definitions/test_uc_h.py` (2 Skenario)

---

## 6. Panduan Ekstensi untuk Pengembangan Selanjutnya (Sprint 2 Guidelines)

Saat menambahkan fitur baru pada Sprint 2 (seperti `UC-C`, `UC-E`, `UC-F`, `UC-I`, `UC-J`, `UC-L`), ikuti konvensi arsitektur berikut:
1. **Jangan mengubah nama kolom yang sudah ada pada `app/models/entities.py`** agar kompatibilitas dengan ke-17 tes BDD Sprint 1 tetap terjaga.
2. Buat kontroler baru di dalam `app/controllers/kontrol_<nama_fitur>.py` dengan pola konstruktor `def __init__(self, db: Session):`.
3. Buat template HTML baru di dalam `app/views/templates/` menggunakan struktur *header* dan navigasi yang seragam.
4. Daftarkan *route* baru pada `app/main.py` dan tambahkan skenario pengujian Gherkin baru di `tests/features/` serta `tests/step_definitions/`.