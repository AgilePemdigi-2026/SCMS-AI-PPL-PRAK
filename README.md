# SCMS-AI Dinas PUPR Kota Surabaya
> **Smart Infrastructure Monitoring & Dispatch System (SCMS-AI)**  
> Sistem Triage, Validasi AI, dan Prioritisasi Laporan Kerusakan Jalan Berbasis Artificial Intelligence — Dinas Sumber Daya Air dan Bina Marga (DSDABM) Kota Surabaya.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-red?logo=sqlite&logoColor=white)
![Pytest](https://img.shields.io/badge/Pytest-31%20BDD%20%2B%203%20E2E%20%2B%20316%20unit-success?logo=pytest&logoColor=white)
![Leaflet GIS](https://img.shields.io/badge/Leaflet.js-OpenStreetMap-199900?logo=openstreetmap&logoColor=white)

---

## 👥 Tim Pengembang (Kelompok 7 — Kelas I3)

| Nama Lengkap | Peran & Tanggung Jawab Modul (Sprint 1) |
| :--- | :--- |
| **Rizaldi Rizki Saputra** | Arsitektur Basis Data (10 Tabel PDM & Seeder), Autentikasi Multi-Aktor (`UC-K`), Pelaporan Kerusakan 4 Langkah & AI Pipeline (`UC-A`), serta Penugasan Penilik Jalan & SPK (`UC-G`). |
| **Alfarrel Yuri Ramadhani** | Verifikasi Laporan & Evaluasi Skor Risiko Ambigu (`UC-B`), serta Dashboard Prioritas Infrastruktur & Peta Geospasial GIS (`UC-H`). |

---

## 📋 Latar Belakang & Deskripsi Proyek
**SCMS-AI** dirancang untuk mentransformasi proses penanganan pengaduan kerusakan jalan dan infrastruktur di Kota Surabaya dari yang semula bersifat manual-reaktif menjadi terotomatisasi dan berbasis tingkat risiko (*Risk-Based Triage*).

Sistem ini mengintegrasikan tiga pilar kecerdasan utama:
1. **Computer Vision (YOLOv8, opsional):** Memvalidasi bukti foto warga (menolak foto non-infrastruktur) serta mengekstraksi rekomendasi kategori kerusakan dan *Severity Score* awal. Secara bawaan berjalan dalam **mode simulasi** (lihat [Mode AI](#-mode-ai)).
2. **Natural Language Processing (Sentence-Transformers, opsional):** Mendeteksi duplikasi laporan secara spasial-semantik dua tingkat (<= 15 m langsung digabung; 15–50 m wajib kemiripan deskripsi), menggabungkan laporan serupa ke tiket *Work Order* aktif, dan menaikkan nilai *Exposure Count* (+1). Bawaan: kemiripan leksikal tanpa model.
3. **Multi-Factor Risk Scoring Engine & GIS (PRD BR-2):** Menghitung skor prioritas penanganan (skala 0–10) di `app/services/risk_scoring.py`:
   $$\text{Risk Score} = \text{clip}\big(0.50\,S + 0.45\ln(E+1) + 0.15\,V + 0.25\,C,\ 0,\ 10\big)$$
   dengan *S* = severity, *E* = jumlah pelapor, *V* = kerentanan lokasi, *C* = kritikalitas kelas jalan. Hasilnya menentukan tingkat prioritas (≥ 8,0 Urgent; 6,0 ≤ skor < 8,0 Tinggi; 4,0 ≤ skor < 6,0 Borderline; < 4,0 Rendah) tanpa target waktu penyelesaian (konsep SLA dihapus atas masukan asisten dosen karena perbaikan jalan melewati birokrasi) dan divisualisasikan pada peta Leaflet.js & OpenStreetMap.

---

## 🚀 Cakupan Fitur Utama (Sprint 1 — 17 Skenario BDD)

1. **UC-K — Login / Autentikasi Pengguna (5 Skenario BDD):**
   * Autentikasi terpadu untuk 4 aktor: **Warga** (via Nomor HP), **Admin**, **Penilik Jalan**, dan **Kepala Bidang** (via Email Instansi).
   * Validasi kredensial salah dan pencegahan pengiriman form kosong.
2. **UC-A — Membuat Laporan Kerusakan 4 Langkah (4 Skenario BDD):**
   * **Step 1 (Capture):** Validasi format berkas (`JPG/PNG`) dan ukuran maksimum ($\le 10\text{ MB}$), serta deteksi objek jalan rusak menggunakan AI Computer Vision.
   * **Step 2 (Location):** Pencarian alamat akurat (*Nominatim Geocoding*), deteksi GPS otomatis, dan penempatan pin peta interaktif.
   * **Step 3 (Detail):** Rekomendasi kategori otomatis dari AI dan validasi deskripsi minimal 10 karakter.
   * **Step 4 (Review & Deduplikasi):** Tinjauan akhir dan penggabungan otomatis (*merge*) jika terdeteksi laporan aktif serupa di titik lokasi yang sama.
3. **UC-B — Memverifikasi Laporan Kerusakan (4 Skenario BDD):**
   * Menampilkan antrean tiket terurut dari *Risk Score* tertinggi ke terendah.
   * Otorisasi persetujuan tiket (`Disetujui`) untuk skor risiko yang jelas.
   * Deteksi otomatis skor risiko *borderline/ambigu* ($4.0 \le \text{Risk Score} < 6.0$; skor 6,0 termasuk skor jelas) dengan opsi **Tugaskan Inspeksi Tambahan** (`Menunggu Inspeksi`, hanya ke Penilik Jalan berstatus *Tersedia*) atau **Lanjutkan Tanpa Inspeksi** disertai pencatatan log audit keputusan manual. Tiket ambigu tidak dapat disetujui lewat tombol *Setujui* maupun Aksi Cepat Dashboard.
   * Keputusan verifikasi hanya untuk tiket `Dilaporkan`; setelah itu tidak dapat diubah dari halaman Verifikasi (penggantian Penilik Jalan dilakukan di halaman Work Order dan tercatat di riwayat).
4. **UC-G — Menugaskan Penilik Jalan (2 Skenario BDD):**
   * Menampilkan lencana **Prioritas Penanganan** (warna sama dengan marker peta, misal merah untuk *Urgent*) dan daftar Penilik Jalan yang tersedia sesuai wilayah rayon.
   * Penanganan otomatis kondisi ketika seluruh Penilik Jalan di wilayah terkait sedang penuh (`Menunggu Penugasan`).
5. **UC-H — Melihat Dashboard Prioritas Infrastruktur (2 Skenario BDD):**
   * Kartu metrik KPI dinamis yang dihitung dari tiket yang sama dengan tabel (ikut filter), ringkasan zona risiko wilayah, dan peta sebaran kerusakan jalan dengan gradasi warna tingkat keparahan (*severity*).
   * Filter multi-parameter berdasarkan Wilayah, Status, dan Kategori dengan penanganan kondisi hasil filter kosong.

---

## 🧭 Cakupan Fitur Sprint 2 (14 Skenario BDD)

Alur status tiket: `Dilaporkan → Disetujui / Menunggu Inspeksi → (Menunggu Penugasan →) Ditugaskan → Terinspeksi → Dalam Proses → Selesai`. Tiket `Disetujui` wajib ditugaskan Admin lebih dulu (`Ditugaskan`, atau `Menunggu Penugasan` bila tidak ada penilik tersedia); Penilik Jalan hanya menginspeksi tiket yang ditugaskan kepadanya (`Ditugaskan`, atau `Menunggu Inspeksi` dengan dirinya sebagai penilik). Setiap perubahan status dicatat di tabel `riwayat_status` (linimasa) dan otomatis membuat **satu notifikasi per warga pelapor** tiket tersebut (`app/services/alur_status.py`). Satu warga memberi satu rating per tiket, meski dua laporannya digabung ke tiket yang sama.

1. **UC-C — Lacak Status Laporan (`/lacak`, 2 skenario):** warga mencari laporannya dengan ID Laporan (`LAP-2026-0001`), melihat skor severity AI, prioritas, linimasa vertikal, riwayat status, serta foto laporan/survei/selesai. Laporan milik warga lain dianggap tidak ditemukan.
2. **UC-D — Data Master (`/master-data`, 2 skenario):** Admin menambah wilayah rayon dan Penilik Jalan (NIP 18 digit, unik) serta mengubah ketersediaan petugas. Penilik baru mendapat kata sandi sementara yang ditampilkan sekali, dan bisa login dengan NIP.
3. **UC-E — Inspeksi Lapangan (`/TugasLapangan`, 2 skenario):** Penilik Jalan hanya melihat tiket di wilayahnya, mengisi dimensi kerusakan, catatan teknis, rekomendasi penanganan, dan foto survei → status `Terinspeksi`.
4. **UC-F — Update Perbaikan (3 skenario):** Admin menerbitkan SPK (nomor unik + tim pelaksana) dari halaman Work Order → `Dalam Proses`; Penilik/Admin memperbarui progres dan menutup tiket → `Selesai` (wajib foto bukti).
5. **UC-I — Notifikasi (`/notifikasi`, 1 skenario):** daftar notifikasi dengan lencana jumlah belum dibaca; klik notifikasi menandainya terbaca dan membuka progres laporan.
6. **UC-J — Rating & Ulasan (2 skenario):** setelah `Selesai`, warga memberi 1–5 bintang dan ulasan (sekali per laporan).
7. **UC-L — Laporan Kinerja Infrastruktur (`/laporan-kinerja`, 2 skenario):** Kepala Bidang/Admin memfilter periode & wilayah, melihat KPI, tingkat dan rata-rata waktu penyelesaian, **rata-rata durasi per tahap** (Verifikasi, Penugasan, Inspeksi Lapangan, Penerbitan SPK, Perbaikan — dalam hari, keseluruhan dan per prioritas, dari `riwayat_status`), **tiket aktif menurut umur** beserta tahap saat ini, statistik risiko per wilayah dan per prioritas, serta rating warga. Rekap dapat diunduh sebagai CSV (rekap wilayah / detail tiket) atau dicetak/disimpan sebagai PDF lewat browser. Ukuran berbasis SLA (kepatuhan SLA, status Tepat Waktu/Terlambat) dihapus atas masukan asisten dosen.

---

## 📂 Struktur Direktori Proyek

```text
scms-ai-pupr/
├── app/
│   ├── controllers/                 # Logika bisnis & orkestrasi per Use Case
│   │   ├── kontrol_autentikasi.py   # Controller UC-K (Login Multi-Aktor)
│   │   ├── kontrol_pelaporan.py     # Controller UC-A (Wizard 4-Step & AI CV/NLP)
│   │   ├── kontrol_verifikasi.py    # Controller UC-B (Verifikasi & Skor Ambigu)
│   │   ├── kontrol_penugasan.py     # Controller UC-G (Penugasan Penilik & Prioritas)
│   │   ├── kontrol_dashboard.py     # Controller UC-H (Dashboard Prioritas & GIS)
│   │   ├── kontrol_lacak.py         # Controller UC-C & UC-J (Lacak Laporan, Rating)
│   │   ├── kontrol_master_data.py   # Controller UC-D (Wilayah & Penilik Jalan)
│   │   ├── kontrol_inspeksi.py      # Controller UC-E (Inspeksi Lapangan)
│   │   ├── kontrol_penanganan.py    # Controller UC-F (SPK & Progres Perbaikan)
│   │   ├── kontrol_notifikasi.py    # Controller UC-I (Notifikasi Warga)
│   │   └── kontrol_laporan_kinerja.py # Controller UC-L (Rekap Kinerja, Durasi per Tahap, Umur Tiket & Ekspor CSV)
│   ├── models/
│   │   └── entities.py              # Definisi 10 Tabel Physical Data Model (SQLAlchemy)
│   ├── services/
│   │   ├── ai_service.py            # Validasi foto, Computer Vision & NLP (simulasi / YOLOv8 / ST)
│   │   ├── deduplikasi.py           # Aturan deduplikasi spasial-semantik (BR-3)
│   │   ├── risk_scoring.py          # Formula Risk Score & tingkat prioritas (BR-2)
│   │   ├── alur_status.py           # Perubahan status + riwayat + notifikasi otomatis
│   │   └── penyimpanan.py           # Simpan foto unggahan & pembuat ID berurutan
│   ├── auth.py                      # Sesi login & pembatasan akses per peran
│   ├── static/
│   │   └── images/                  # Aset visual dan logo instansi
│   ├── views/templates/             # Antarmuka pengguna (Jinja2, TailwindCSS, Leaflet.js)
│   │   ├── login.html
│   │   ├── buat_laporan.html
│   │   ├── verifikasi_detail.html
│   │   ├── work_order_list.html
│   │   └── dashboard_prioritas.html
│   ├── database.py                  # Konfigurasi engine & session SQLite/SQLAlchemy
│   └── main.py                      # Entrypoint aplikasi & routing FastAPI terintegrasi
├── database/
│   └── seed.py                      # Seeder data awal sesuai skenario BDD & Mockup
├── docs/
│   ├── activity_diagrams/           # File PlantUML (.puml) Activity Diagram 12 Use Case
│   └── sequence_diagrams/           # File PlantUML (.puml) Sequence Diagram 12 Use Case
├── tests/
│   ├── features/                    # Spesifikasi skenario Gherkin (.feature)
│   ├── step_definitions/            # Pytest-BDD: 17 skenario Sprint 1 + 14 skenario Sprint 2 + 3 E2E Selenium
│   ├── test_keamanan_dan_logika.py  # Uji cepat Sprint 1: hak akses, unggah foto, deduplikasi, risk score
│   ├── test_sprint2.py              # Uji cepat Sprint 2: hak akses, kepemilikan data, alur status, notifikasi
│   ├── test_laporan_kinerja.py      # Uji cepat UC-L: hak akses, durasi per tahap, umur tiket aktif, filter, ekspor CSV
│   ├── test_audit_sprint2.py        # Uji regresi temuan audit pra-Sprint 3 (A-01…A-10, B-01…B-05, C-05, C-06, D-01…D-05, E-01, E-04)
│   ├── test_tanpa_sla.py            # Uji regresi penghapusan SLA (revisi asisten dosen)
│   └── test_tampilan_tiket.py       # Uji tampilan detail tiket: posisi lencana prioritas, warna, foto & kotak deteksi
├── reports/                         # Laporan pengujian (lihat "Membuat Laporan Pengujian")
│   ├── cucumber.json                # Hasil BDD format Cucumber (pytest-bdd --cucumberjson)
│   ├── cucumber_bdd_report.html     # Laporan BDD per sprint (dibuat generate_bdd_report.py)
│   ├── selenium_e2e_report.html     # pytest-html: 31 skenario BDD + 3 E2E Selenium
│   └── dokumentasi_testing_scms.html # pytest-html: seluruh 350 tes
├── generate_bdd_report.py           # Pembuat cucumber_bdd_report.html dari cucumber.json
├── pytest.ini                       # Konfigurasi pytest runner
├── requirements.txt                 # Daftar dependensi paket Python
├── requirements-ai.txt              # (Opsional) model AI sungguhan: ultralytics, sentence-transformers
└── README.md                        # Dokumentasi utama proyek
```

---

## ⚙️ Cara Menjalankan Proyek (Panduan Instalasi Lokal)

Pastikan perangkat Anda telah terinstal **Python 3.10+**. Ikuti 6 langkah berikut di terminal:

### 1. Buat Virtual Environment (`venv`)
```bash
python -m venv venv
```

### 2. Aktifkan Virtual Environment
* **Windows (PowerShell / CMD):**
  ```powershell
  venv\Scripts\activate
  ```
* **macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```

### 3. Instal Seluruh Dependensi Pustaka
```bash
pip install -r requirements.txt
```

### 4. Salin `.env.example` menjadi `.env` lalu sesuaikan
Isi `DATABASE_URL` (tanpa `.env`, aplikasi memakai SQLite `scms_dev.db`) dan `SCMS_SECRET_KEY` (penanda tangan cookie sesi login).

### 5. Inisialisasi & Isi Data Awal (Database Seeder)
> Database lama dari Sprint 1 tetap bisa dipakai: saat aplikasi dijalankan, kolom baru (koordinat laporan, alamat domisili) ditambahkan otomatis. Jalankan seeder hanya untuk mengisi ulang data contoh.
> ⚠️ Seeder **menghapus seluruh tabel** lalu mengisinya ulang. Untuk database selain SQLite (mis. PostgreSQL) seeder menolak berjalan kecuali diberi `--force`.
```bash
python -m database.seed            # SQLite lokal
python -m database.seed --force    # PostgreSQL: hanya jika memang ingin mereset
```

### 6. Jalankan Pengujian Otomatis
Pengujian **selalu** memakai database terpisah `scms_test.db`, sehingga database di `.env` tidak tersentuh.
```bash
pytest -v                                      # semua 350 tes: 31 BDD + 3 E2E Selenium + 316 uji cepat (butuh Chrome/Edge)
pytest tests/test_keamanan_dan_logika.py tests/test_sprint2.py tests/test_laporan_kinerja.py tests/test_audit_sprint2.py tests/test_tanpa_sla.py tests/test_tampilan_tiket.py -v   # uji cepat saja, tanpa browser
HEADLESS=1 pytest -v                           # browser tanpa jendela
```

### Membuat Laporan Pengujian
Keempat berkas di `reports/` dibuat ulang dengan tiga perintah berikut (butuh `pytest-html`, sudah ada di `requirements.txt`). Jalankan dari folder proyek dengan venv aktif. Perintah 1 harus dijalankan sebelum perintah 3, karena perintah 3 membaca `reports/cucumber.json`.
```bash
# 1. BDD (31 skenario) + 3 E2E Selenium -> reports/cucumber.json + reports/selenium_e2e_report.html
HEADLESS=1 python -m pytest tests/step_definitions --cucumberjson=reports/cucumber.json --html=reports/selenium_e2e_report.html --self-contained-html

# 2. Seluruh 350 tes -> reports/dokumentasi_testing_scms.html
HEADLESS=1 python -m pytest --html=reports/dokumentasi_testing_scms.html --self-contained-html

# 3. reports/cucumber.json -> reports/cucumber_bdd_report.html (dikelompokkan Sprint 1 / Sprint 2)
python generate_bdd_report.py
```
Di PowerShell, ganti awalan `HEADLESS=1 ` dengan `$env:HEADLESS = "1";` sebelum perintah. Hapus `HEADLESS=1` bila ingin melihat jendela browser. Pengelompokan sprint diatur di `SPRINT_UC` pada `generate_bdd_report.py` (Sprint 1: UC-K, A, B, G, H; Sprint 2: UC-C, D, E, F, I, J, L).

### 7. Jalankan Server Aplikasi Web
```bash
uvicorn app.main:app --reload
```
Setelah server aktif, buka browser dan akses tautan berikut:
* **Halaman Login Utama (`UC-K`):** `http://127.0.0.1:8000/Login`
* **Form Pelaporan Warga 4 Langkah (`UC-A`, login Warga):** `http://127.0.0.1:8000/lapor`
* **Dashboard Prioritas & Peta GIS (`UC-H`, login staf):** `http://127.0.0.1:8000/Dashboard`
* **Verifikasi Laporan & Evaluasi AI (`UC-B`, login Admin/Kabid):** `http://127.0.0.1:8000/verifikasi`
* **Penugasan Penilik Jalan & SPK (`UC-G`, login staf):** `http://127.0.0.1:8000/work-orders`

---

## 🤖 Mode AI

Semua fitur AI melewati satu layanan (`app/services/ai_service.py`) dan backend-nya dipilih lewat `.env`:

| Variabel | Bawaan | Pilihan lain |
| :--- | :--- | :--- |
| `SCMS_CV_BACKEND` | `simulasi` — **tidak ada model**; kategori & severity ditentukan dari **nama berkas** (nama berisi `kucing`, `selfie`, `mobil`, dst. ditolak; `retak` → Retak Permukaan; `amblas` → Jalan Amblas) | `yolov8` + `SCMS_YOLO_WEIGHTS=<path .pt>` (model kerusakan jalan, mis. dilatih pada RDD2022: D00/D10/D20 → Retak, D40 → Berlubang) |
| `SCMS_NLP_BACKEND` | `leksikal` — kemiripan kata (tanpa model) | `sentence-transformers` (model `SCMS_ST_MODEL`, bawaan `paraphrase-multilingual-MiniLM-L12-v2`) |

* Foto **benar-benar diunggah** dan diperiksa isinya (harus JPEG/PNG asli, ≤ 10 MB), lalu disimpan di `app/static/uploads/`.
* Dalam mode simulasi, UI menampilkan label **"Mode simulasi AI"** dan tidak menampilkan angka confidence.
* Model sungguhan: `pip install -r requirements-ai.txt`. Jika library/bobot model tidak ditemukan, aplikasi mencatat peringatan dan kembali ke mode simulasi.

### Memakai model YOLOv8 v4

1. Salin dua file hasil `export_v4` (Google Drive `scms_ai_runs/export_v4/`) ke `models/scms_v4/`:
   `yolov8_infra_best.pt` dan `model_config.json`. Folder `models/` tidak ikut di-commit (lihat `.gitignore`).
2. Isi `.env`:
   ```
   SCMS_CV_BACKEND=yolov8
   SCMS_YOLO_WEIGHTS=models/scms_v4/yolov8_infra_best.pt
   ```
3. `pip install -r requirements-ai.txt`, lalu jalankan ulang aplikasi. Header halaman lapor menampilkan `mode: yolov8`.

Setelan inferensi dibaca otomatis dari `model_config.json` (dipilih dari data validasi saat training):
ukuran gambar 800, ambang confidence **Jalan Berlubang 0,26** dan **Retak Permukaan 0,20**, NMS IoU 0,6, *agnostic NMS* mati.
Model v4 hanya mengenali dua kelas (Jalan Berlubang, Retak Permukaan); Jalan Amblas tetap dipilih oleh warga/petugas.

## 🛡️ Hak Akses per Peran

| Halaman / Aksi | Warga | Admin (PPK) | Kepala Bidang | Penilik Jalan |
| :--- | :---: | :---: | :---: | :---: |
| `/Beranda`, `/lapor`, `/lacak`, `/notifikasi` | ✅ | – | – | – |
| `/Dashboard` | – | ✅ | ✅ | 👁️ wilayahnya sendiri |
| `/verifikasi` | – | ✅ | 👁️ lihat saja | – |
| `/work-orders` | – | ✅ | 👁️ lihat saja | 👁️ wilayahnya sendiri |
| `/master-data` | – | ✅ | 👁️ lihat saja | – |
| `/laporan-kinerja`, `/laporan-kinerja/unduh` (CSV) | – | ✅ | ✅ | – |
| `/TugasLapangan` (inspeksi & progres) | – | – | – | ✅ (hanya tiket yang ditugaskan kepadanya) |
| Setujui / tugaskan / terbitkan SPK / ubah data master | – | ✅ | – | – |

Halaman tanpa login dialihkan ke `/Login`; peran yang tidak berhak mendapat `403`. Sesi berakhir otomatis jika akun dinonaktifkan. *Exposure* tiket dihitung dari jumlah **warga berbeda** yang melapor, sehingga satu warga yang mengirim ulang laporan tidak menaikkan prioritas.

---

## 🔐 Akun Kredensial Pengujian (Demo Login)

Seluruh akun pengujian di bawah ini menggunakan kata sandi: **`password123`**

| Peran Aktor | Identifier (No. HP / Email) | Halaman Tujuan Setelah Login |
| :--- | :--- | :--- |
| **Warga** | `0812xxxxxxx` (atau NIK `3578010101900001`) | `/Beranda` (Form Pelaporan Warga) |
| **Warga kedua** | `0813xxxxxxx` (pelapor tiket REP-2026-00298) | `/Beranda` |
| **Admin (PPK)** | `admin@dpupr.surabaya.go.id` | `/Dashboard` (Dashboard Prioritas & Verifikasi) |
| **Penilik Jalan** | `budi.santoso@dpupr.surabaya.go.id` (atau NIP `198501012015021001`) | `/TugasLapangan` (Inspeksi & Update Perbaikan) |
| **Kepala Bidang** | `kabid@dpupr.surabaya.go.id` | `/Dashboard` (Monitoring Eksekutif & Analitik) |

---
*&copy; 2026 Kelompok 7 — Kelas I3. Pengembangan Perangkat Lunak Praktik (Agile Pemdigi).*