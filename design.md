# UI/UX & System Design Specification (`design.md`)
# SCMS-AI: Smart Complaint Management System — Dinas PUPR Kota Surabaya

**Versi Dokumen:** 1.0  
**CSS Framework:** Tailwind CSS (CDN / Utility-First)  
**Font Family:** `Inter`, sans-serif (Google Fonts)  
**Peta Geospasial:** Leaflet.js `1.9.4` + OpenStreetMap + Nominatim Geocoding API  

---

## 1. Filosofi Desain & Identitas Visual (Design Philosophy)

Antarmuka **SCMS-AI** dirancang mengikuti standar **Government Enterprise Dashboard** untuk Dinas Sumber Daya Air dan Bina Marga (DSDABM / PUPR) Kota Surabaya dengan tiga prinsip utama:
1. **Clarity Over Decoration:** Mengutamakan keterbacaan data tabel prioritas, kejelasan metrik skor AI (*Severity* & *Risk Score*), dan kemudahan navigasi dibanding ornamen visual yang berlebihan.
2. **Color-Coded Urgency:** Warna mencolok (Merah, Oranye, Kuning, Hijau) **hanya** digunakan untuk merepresentasikan tingkat keparahan kerusakan jalan (*Severity/Risk*), status tiket *Work Order*, atau umpan balik validasi sistem.
3. **Progressive Disclosure (Wizard Pattern):** Untuk pengguna publik (Warga), proses pelaporan yang kompleks dipecah menjadi 4 langkah bertahap (*Stepper Wizard*) agar mudah digunakan di layar *mobile* maupun *desktop*.

---

## 2. Sistem Desain: Warna, Tipografi & Komponen (Design Tokens)

### 2.1 Palet Warna Utama (Brand & Surface Colors)

| Peran Warna | Kode Hex / Kelas Tailwind | Penggunaan Utama |
| :--- | :--- | :--- |
| **Primary Brand Blue** | `#0B5ED7` (`bg-[#0B5ED7]`, `text-[#0B5ED7]`) | Tombol aksi utama (*Primary CTA*), indikator tab/step aktif, tautan nomor tiket (`REP-2026-...`), dan aksen fokus input. |
| **Executive Dark Navy** | `#0F2942` (`bg-[#0F2942]`) | Avatar profil pejabat/admin, aksen header sekunder, dan lencana identitas instansi. |
| **App Background** | `#F8FAFC` (`bg-[#F8FAFC]`) | Latar belakang utama halaman (`<body>`) agar kartu putih di atasnya memiliki kontras yang nyaman di mata. |
| **Card & Surface** | `#FFFFFF` (`bg-white`) + `border-slate-200` | Seluruh kartu KPI, pembungkus tabel, panel formulir, dan bilah navigasi atas (*Header*). |
| **Text Hierarchy** | `text-slate-900` / `text-slate-700` / `text-slate-500` | Judul utama (`font-extrabold text-slate-900`), isi tabel (`text-slate-700`), dan teks bantuan/label sekunder (`text-slate-500`). |

### 2.2 Warna Semantik Tingkat Risiko & Marker Peta GIS (BR-2)

Setiap tingkat risiko (*Risk Score*) wajib menggunakan skema warna yang konsisten baik pada *badge* tabel maupun titik lingkaran pada peta Leaflet.js:

| Kategori Prioritas | Rentang *Risk Score* | Warna Marker GIS (Hex) | Kelas Badge Tailwind | Rekomendasi SLA |
| :--- | :--- | :--- | :--- | :--- |
| **Urgent / Darurat** | $\ge 8.0$ | `#DC2626` (Merah) | `bg-red-100 text-red-700 border-red-200` | `24 jam` |
| **Tinggi** | $6.0 - 7.9$ | `#EA580C` (Oranye) | `bg-orange-100 text-orange-800 border-orange-200` | `3 x 24 jam` |
| **Borderline / Ambigu** | $4.0 - 5.9$ | `#D97706` (Amber/Kuning) | `bg-amber-100 text-amber-900 border-amber-300` | `Butuh Verifikasi Lapangan` |
| **Rendah / Selesai** | $< 4.0$ atau `Selesai` | `#16A34A` (Hijau) | `bg-emerald-100 text-emerald-800 border-emerald-200` | `7 x 24 jam` / Tuntas |

### 2.3 Tipografi & Skala Ukuran

* **Judul Halaman (`<h2>`):** `text-2xl font-extrabold text-slate-900 tracking-tight`
* **Judul Panel / Kartu (`<h3>`):** `text-sm` atau `text-base font-bold text-slate-900`
* **Header Tabel (`<th>`):** `text-[11px] font-bold text-slate-500 uppercase tracking-wider bg-slate-50`
* **Isi Tabel & Form (`<td>`, `<input>`, `<select>`):** `text-xs font-semibold text-slate-800`
* **Teks Koordinat & Log Audit:** `font-mono text-xs`

---

## 3. Tata Letak Standar & Struktur Navigasi (Global Layout)

### 3.1 Portal Internal Dinas (`UC-H`, `UC-B`, `UC-G`)
Menggunakan lebar kontainer maksimum `max-w-[1360px] mx-auto px-6` dengan struktur:
1. **Sticky Top Header:** Menampilkan logo SCMS PUPR Kota Surabaya, indikator sistem aktif, serta profil pejabat yang sedang login di sisi kanan.
2. **Sub-Navbar Horizontal:** Berisi tautan navigasi cepat antar-modul:
   * `Dashboard Prioritas (UC-H)` $\rightarrow$ `/Dashboard`
   * `Verifikasi Laporan (UC-B)` $\rightarrow$ `/verifikasi`
   * `Penugasan Penilik (UC-G)` $\rightarrow$ `/work-orders`
   * `Buat Laporan (UC-A)` $\rightarrow$ `/lapor`
   *(Menu yang sedang aktif ditandai dengan `text-[#0B5ED7] border-b-2 border-[#0B5ED7]`).*
3. **Breadcrumb & Page Title:** Menunjukkan posisi halaman saat ini (`SCMS / Nama Modul`).

### 3.2 Portal Publik Warga (`UC-A`)
Menggunakan lebar kontainer lebih terfokus `max-w-5xl mx-auto px-6` agar proses pengisian formulir 4 langkah nyaman diakses baik melalui ponsel maupun laptop.

---

## 4. Spesifikasi Desain Antarmuka per Use Case (UI Screen Specifications)

### 4.1 Halaman Login Multi-Aktor (`login.html` — UC-K)
* **Tata Letak:** Kartu terpusat (*Centered Card Layout*) di atas latar belakang bersih dengan identitas resmi Dinas PUPR Kota Surabaya.
* **Komponen Utama:**
  * Input tunggal `identifier` (mendukung Nomor HP untuk Warga atau Email Instansi untuk Admin/Penilik/Kabid).
  * Input `password` dengan validasi wajib isi.
  * Kotak peringatan merah (`bg-red-50 border-red-200 text-red-700`) yang muncul secara dinamis ketika kredensial tidak valid atau kolom kosong.
  * Panel bantuan pengujian cepat (*Quick Demo Credentials*) untuk mempermudah pengujian 4 aktor saat demonstrasi.

### 4.2 Halaman Buat Laporan 4 Langkah (`buat_laporan.html` — UC-A)
Menggunakan pola **4-Step Interactive Wizard** (`Capture` $\rightarrow$ `Location` $\rightarrow$ `Detail` $\rightarrow$ `Review`):
1. **Step 1 — Capture (`#panel-step-1`):**
   * *Dropzone uploader* (`<input type="file" accept=".jpg,.jpeg,.png">`) dengan pratinjau gambar langsung (*FileReader API*).
   * Validasi sisi klien & server yang mengunci tombol `"Lanjut ke Langkah 2"` apabila format bukan `JPG/PNG`, ukuran $> 10\text{ MB}$, atau objek foto terdeteksi bukan jalan rusak (`kucing.jpg`).
2. **Step 2 — Location (`#panel-step-2`):**
   * Bilah pencarian alamat jalan di Surabaya yang terhubung ke **OpenStreetMap Nominatim Search API** (*Forward Geocoding*) lengkap dengan daftar saran lokasi (*Autocomplete Dropdown*) dan tombol `"Gunakan GPS Saya"`.
   * Peta interaktif `#mapPicker` dengan *draggable marker*: saat pin digeser atau peta diklik, sistem memanggil *Nominatim Reverse Geocoding API* untuk mengisi otomatis nama ruas jalan, koordinat `(latitude, longitude)`, serta memilih wilayah rayon (`Gubeng`, `Benowo`, atau `Wonokromo`).
3. **Step 3 — Detail (`#panel-step-3`):**
   * Kotak informasi biru yang menampilkan hasil deteksi AI Computer Vision (`Kategori Terdeteksi` & `Estimasi Severity Awal`).
   * *Dropdown* kategori kerusakan yang otomatis terisi rekomendasi AI namun tetap dapat diubah oleh warga.
   * `<textarea>` deskripsi kondisi jalan dengan penghitung karakter *real-time* (`0 / min. 10 karakter`).
4. **Step 4 — Review & Submit (`#panel-step-4`):**
   * Tabel ringkasan 4 poin data laporan sebelum tombol `"Kirim Laporan"` ditekan.
   * Menampilkan kotak umpan balik hijau di bagian atas halaman setelah dikirim (menampilkan nomor tiket baru `REP-2026-00341` atau informasi penggabungan deduplikasi ke `REP-2026-00298`).

### 4.3 Halaman Dashboard Prioritas & Peta GIS (`dashboard_prioritas.html` — UC-H)
* **Baris 1 — 4 Kartu KPI Dinamis:** Menampilkan *Total Pengaduan*, *Prioritas Darurat ($\ge 8.0$)*, *Kasus Dalam Penanganan*, dan *Tingkat Penyelesaian (%)* yang dihitung langsung dari basis data.
* **Baris 2 — Filter Operasional Multi-Parameter:** Form `GET /Dashboard` dengan *dropdown* `Wilayah`, `Status`, dan `Kategori`, ditambah tombol `Terapkan Filter` dan `Reset`.
* **Baris 3 — Peta Geospasial (8 Kolom) & Ringkasan Zona Risiko (4 Kolom):**
  * Peta `#mapSurabaya` merender `L.circle` (radius dampak) dan `L.circleMarker` (titik laporan) dengan warna sesuai *severity*.
  * Panel kanan menampilkan agregasi jumlah tiket dan *Max Risk Score* untuk setiap wilayah rayon serta kotak rumus prioritisasi.
* **Baris 4 — Tabel Antrean Prioritas (*Priority Queue*):**
  * Menampilkan daftar tiket terurut dari *Risk Score* tertinggi (`REP-2026-00341 (8.4)`).
  * Mengklik baris tabel memicu fungsi `fokusKeTitik(lat, lng, idTiket)` yang menggerakkan kamera peta (`map.flyTo`) dan membuka *popup* titik tersebut.
  * Kolom paling kanan memuat 3 tombol **Aksi Cepat (`REQ-DSH-5`)**: `Lihat Detail` (ke `/verifikasi`), `Setujui` (`POST` langsung mengubah status), dan `Tugaskan` (ke `/work-orders`).

### 4.4 Halaman Verifikasi Laporan & Evaluasi AI (`verifikasi_detail.html` — UC-B)
* **Bagian Atas — Tabel Antrean Verifikasi Terurut (`REQ-VER-1`):** Memudahkan Admin berpindah antar-tiket yang diurutkan dari *Risk Score* tertinggi ke terendah.
* **Bagian Bawah Kiri (7 Kolom) — Bukti Visual & Metadata:** Menampilkan simulasi *bounding box* deteksi AI di atas foto laporan warga, rekomendasi SLA, deskripsi warga, dan kotak **Log Audit Keputusan Manual** (`log_keputusan`) jika ada.
* **Bagian Bawah Kanan (5 Kolom) — Panel Keputusan Kondisional (`REQ-VER-3` s/d `REQ-VER-6`):**
  * Menggunakan percabangan ketat Jinja2 `{% if detail.is_ambiguous %}`:
  * **Jika Skor Jelas (Contoh: `REP-2026-00341`, Skor `8.4`):** Hanya menampilkan kartu biru otorisasi dengan tombol **`"Setujui Tiket"`**.
  * **Jika Skor Ambigu / Borderline ($4.0 \le \text{Skor} \le 6.0$, Contoh: `REP-2026-00355`, Skor `5.1`):** Menampilkan kartu berbingkai kuning/amber berlabel **`"Butuh Verifikasi Lapangan"`** dengan dua formulir pilihan:
    1. Pilih Penilik Jalan + tombol **`"Tugaskan Inspeksi Tambahan"`**.
    2. Tombol **`"Lanjutkan Tanpa Inspeksi"`** (mencatat log audit otomatis).

### 4.5 Halaman Penugasan Penilik Jalan & SPK (`work_order_list.html` — UC-G)
* **Bagian Atas:** 4 Kartu ringkasan SPK (*Total Work Order*, *Siap / Menunggu Penugasan*, *Sedang Ditugaskan*, *Selesai*).
* **Bagian Utama (Grid 12 Kolom):**
  * **Tabel Daftar SPK (7 Kolom):** Menampilkan daftar *Work Order* dengan filter Wilayah & Status, serta tombol `"Pilih & Tugaskan"` pada setiap baris.
  * **Panel Konfirmasi Penugasan & Evaluasi SLA (5 Kolom):**
    * Menampilkan rekomendasi SLA tiket terpilih (`24 jam`).
    * Jika wilayah memiliki Penilik Jalan yang `ketersediaan == True` (misal `Wilayah Gubeng`), menampilkan *dropdown* pemilihan petugas dan tombol **`"Konfirmasi Penugasan"`** (mengubah status ke `"Ditugaskan"`).
    * Jika seluruh Penilik Jalan di wilayah tersebut sedang penuh (misal `REP-2026-00360` di `Wilayah Benowo`), menampilkan kotak peringatan kuning **`"Semua Penilik Jalan di wilayah ini sedang dalam penugasan aktif"`** dan tombol **`"Simpan Status: Menunggu Penugasan"`**.

---

## 5. Pemetaan Diagram Desain UML (`docs/`)

Seluruh rancangan alur aktivitas dan interaksi objek disimpan dalam format **PlantUML (`.puml`)** yang selaras 100% dengan nama kelas dan metode pada kode sumber:

| Use Case | Activity Diagram (`docs/activity_diagrams/`) | Sequence Diagram (`docs/sequence_diagrams/`) | Kelas Boundary, Control & Entity yang Terlibat |
| :--- | :--- | :--- | :--- |
| **UC-K (Login)** | `uc_k_login.puml` | `uc_k_login.puml` | `HalamanLogin` $\rightarrow$ `KontrolAutentikasi` $\rightarrow$ `Warga`, `Admin`, `PenilikJalan`, `KepalaBidang` |
| **UC-A (Buat Laporan)** | `uc_a_buat_laporan.puml` | `uc_a_buat_laporan.puml` | `HalamanBuatLaporan` $\rightarrow$ `KontrolPelaporan` $\rightarrow$ `WorkOrder`, `Laporan` |
| **UC-B (Verifikasi)** | `uc_b_verifikasi.puml` | `uc_b_verifikasi.puml` | `HalamanVerifikasi` $\rightarrow$ `KontrolVerifikasi` $\rightarrow$ `WorkOrder`, `PenilikJalan`, `Inspeksi` |
| **UC-G (Penugasan)** | `uc_g_penugasan.puml` | `uc_g_penugasan.puml` | `HalamanWorkOrders` $\rightarrow$ `KontrolPenugasan` $\rightarrow$ `WorkOrder`, `PenilikJalan` |
| **UC-H (Dashboard)** | `uc_h_dashboard.puml` | `uc_h_dashboard.puml` | `HalamanDashboardPrioritas` $\rightarrow$ `KontrolDashboard` $\rightarrow$ `WorkOrder`, `Wilayah` |

---

## 6. Pedoman Desain untuk Modul Sprint 2 (Future UI Guidelines)

Ketika membangun antarmuka untuk fitur Sprint 2 (`UC-C`, `UC-E`, `UC-F`, `UC-I`, `UC-J`, `UC-L`), gunakan komponen standar berikut:
1. **Halaman Pelacakan Progres Warga (`UC-C`) & Rating (`UC-J`):** Gunakan komponen *Vertical Stepper Timeline* untuk menampilkan tahapan status dari `Dilaporkan` hingga `Selesai`, serta komponen bintang interaktif (1–5 bintang) yang hanya aktif ketika `status_work_order == "Selesai"`.
2. **Halaman Tugas Lapangan Penilik Jalan (`UC-E` & `UC-F`):** Gunakan tata letak ramah seluler (*Mobile-First Card List*) dengan tombol aksi berukuran besar untuk mempermudah petugas lapangan mengunggah foto bukti inspeksi maupun foto perbaikan selesai (*before-after*).