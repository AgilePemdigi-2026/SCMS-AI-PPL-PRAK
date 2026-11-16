# Product Requirements Document (prd.md)
# SCMS-AI: Smart Complaint Management System — Dinas PUPR Kota Surabaya

**Versi Dokumen:** 2.0 (Full Product Scope — Sprint 1 & Sprint 2 Implemented)  
**Organisasi / Tim:** Kelompok 7 (Kelas I3) — Rizaldi Rizki Saputra (187241005) & Alfarrel Yuri Ramadhani (187241109)  
**Target Instansi:** Dinas Sumber Daya Air dan Bina Marga (DSDABM / PUPR) Pemerintah Kota Surabaya  

## 1. Ringkasan Produk
SCMS-AI adalah platform web terintegrasi berbasis Artificial Intelligence (Computer Vision & NLP) dan Sistem Informasi Geografis (GIS) yang mengotomatiskan siklus hidup pengaduan kerusakan jalan di Kota Surabaya mulai dari pelaporan warga, deduplikasi spasial-semantik, prioritisasi berbasis risiko, verifikasi admin, penugasan penilik jalan, survei inspeksi lapangan, penerbitan SPK & perbaikan fisik, notifikasi warga, hingga evaluasi rating kepuasan publik.

## 2. Profil Pengguna & Hak Akses (RBAC)
| Aktor | Identifier Login | Hak Akses & Tanggung Jawab Utama | Halaman Tujuan |
| :--- | :--- | :--- | :--- |
| **Warga** | No. HP, Email, atau NIK | Membuat laporan 4 langkah (`/lapor`), melacak progres (`/lacak`), membuka notifikasi (`/notifikasi`), dan memberi rating 1-5 bintang (`/lacak/{id}/rating`). | `/Beranda` |
| **Admin (PPK)** | Email Instansi | Mengakses `/Dashboard`, memverifikasi laporan (`/verifikasi`), mengelola data master (`/master-data`), menugaskan penilik & menerbitkan SPK (`/work-orders`), serta melihat & mengunduh laporan kinerja (`/laporan-kinerja`, `/laporan-kinerja/unduh`). | `/Dashboard` |
| **Penilik Jalan** | Email atau NIP 18 Digit | Mengakses tugas lapangan (`/TugasLapangan`) yang **ditugaskan kepadanya** di wilayah rayonnya, menyimpan survei inspeksi (`Terinspeksi`), dan memperbarui progres SPK hingga `Selesai`. Melihat `/Dashboard` dan `/work-orders` wilayahnya sendiri dalam mode baca. | `/TugasLapangan` |
| **Kepala Bidang** | Email Instansi | Memantau `/Dashboard`, `/verifikasi`, `/work-orders`, `/master-data`, dan `/laporan-kinerja` (termasuk unduh CSV) dalam mode baca (read-only). | `/Dashboard` |

## 3. Aturan Bisnis Inti (Core Business Rules)
* **BR-1 (Validasi Foto & Deskripsi):** Foto wajib berupa berkas gambar asli `JPEG/PNG` (diperiksa dari bytes header via Pillow) dengan ukuran <= 10.0 MB dan terdeteksi sebagai objek jalan rusak. Deskripsi minimal 10 karakter.
* **BR-2 (Formula Risk Score & SLA — `app/services/risk_scoring.py`):**
  `Risk Score = clip(0.50*S + 0.45*ln(E+1) + 0.15*V + 0.25*C, 0.0, 10.0)`
  - `>= 8.0`: Prioritas `Urgent` (SLA `24 jam`)
  - `6.0 - 7.9`: Prioritas `Tinggi` (SLA `3 x 24 jam`)
  - `4.0 <= skor < 6.0`: Prioritas `Borderline` (SLA `5 x 24 jam`, `Butuh Verifikasi Lapangan`)
  - `< 4.0`: Prioritas `Rendah` (SLA `7 x 24 jam`)
  - **Skor ambigu** (UC-B) = tepat rentang Borderline, `4.0 <= skor < 6.0` (`skor_ambigu()` di `risk_scoring.py`). Skor **6.0** adalah skor jelas (`Tinggi`).
  - **Nilai S (severity) saat warga mengganti kategori AI** (`severity_laporan()` di `app/controllers/kontrol_pelaporan.py`):
    jika `kategori_pilihan` warga **sama** dengan rekomendasi AI, `S` = severity dari AI (kategori + luas area kerusakan).
    Jika **berbeda**, `S` = nilai dasar kategori pilihan (`VisiYolo.BASE_SEVERITY`: Jalan Berlubang `7.0`, Jalan Amblas `7.5`, Retak Permukaan `4.5`),
    bukan severity AI, dan halaman lapor menampilkan "Kategori diubah dari rekomendasi AI (...). Severity memakai nilai dasar kategori dan akan ditinjau petugas."
* **BR-3 (Deduplikasi Spasial-Semantik Dua Tingkat — `app/services/deduplikasi.py`):** Kandidat hanya WorkOrder aktif (belum `Selesai`) dengan kategori kerusakan yang sama. Laporan baru digabungkan ke tiket kandidat bila:
  * **Tingkat 1 — jarak <= 15 m (`RADIUS_PASTI_SAMA_M`):** langsung dianggap duplikat **tanpa** syarat kemiripan deskripsi (dasar: `"jarak <= 15 m"`).
  * **Tingkat 2 — jarak > 15 m s.d. <= 50 m (`RADIUS_DUPLIKAT_M`), atau tanpa koordinat tetapi nama jalan + nomor sama:** wajib kemiripan deskripsi >= ambang backend NLP (leksikal 0,35; sentence-transformers 0,60) (dasar: `"jarak + kemiripan deskripsi"`).
  * **Lebih dari 50 m:** bukan duplikat.
  * Bila ada beberapa kandidat, kandidat Tingkat 1 terdekat diutamakan; bila tidak ada, dipilih kandidat Tingkat 2 dengan kemiripan tertinggi.
  * *Alasan:* akurasi GPS ponsel hanya sekitar ±5–10 m, sehingga dua laporan berkategori sama dalam 15 m hampir pasti merujuk kerusakan yang sama; deskripsi warga sering tidak informatif (mis. tiket REP-2026-00361/00362/00363 terpaut 4–11 m tetapi kemiripan deskripsinya 0); dan setiap tiket tetap diverifikasi Admin serta Penilik Jalan, sehingga penggabungan keliru masih dapat dikoreksi. `exposure_count` bertambah +1 hanya jika pelapor adalah warga yang berbeda.
  * **Status laporan yang digabung mengikuti status tiket** (mis. `Dilaporkan`, lalu ikut berubah bersama tiket) agar linimasa warga konsisten; tidak ada nilai status khusus untuk laporan hasil penggabungan. Penggabungan ditandai lewat notifikasi "Laporan digabungkan" kepada pelapor dan entri `riwayat_status` tiket.
* **BR-4 (Alur Status Atomik — `app/services/alur_status.py`):**
  Urutan status: `Dilaporkan -> Disetujui / Menunggu Inspeksi / Menunggu Penugasan / Ditugaskan -> Terinspeksi -> Dalam Proses -> Selesai`.
  Transisi sah (`TRANSISI_SAH`): `Dilaporkan -> Disetujui | Menunggu Inspeksi`; `Disetujui -> Ditugaskan | Menunggu Penugasan`; `Menunggu Penugasan -> Ditugaskan`; `Menunggu Inspeksi -> Ditugaskan | Terinspeksi`; `Ditugaskan -> Terinspeksi`; `Terinspeksi -> Dalam Proses`; `Dalam Proses -> Selesai`.
  Setiap perubahan status wajib menggunakan pemeriksaan Compare-and-Set atomik, tidak boleh memundurkan status, wajib mencatat log ke tabel `riwayat_status`, dan wajib mengirim `notifikasi` ke seluruh warga pelapor pada tiket tersebut — **satu notifikasi per warga unik** per perubahan status (warga yang dua laporannya digabung ke tiket yang sama tidak menerima notifikasi ganda).
* **BR-5 (Keputusan Verifikasi — UC-B, `kontrol_verifikasi.py`):** Keputusan verifikasi hanya untuk tiket berstatus `Dilaporkan` dan backend hanya menerima aksi yang ditampilkan halaman:
  * Skor jelas -> `Setujui Tiket` (juga Aksi Cepat Dashboard) -> `Disetujui`.
  * Skor ambigu -> `Tugaskan Inspeksi Tambahan` (hanya ke Penilik Jalan wilayah tiket yang berstatus `Tersedia`) -> `Menunggu Inspeksi`, atau `Lanjutkan Tanpa Inspeksi` (dicatat di `log_keputusan`) -> `Disetujui`. Tiket ambigu tidak dapat disetujui lewat `Setujui Tiket` maupun Aksi Cepat Dashboard.
  * Setelah diputuskan, keputusan tidak dapat diubah dari halaman Verifikasi; penggantian Penilik Jalan (termasuk pada `Menunggu Inspeksi`) dilakukan di halaman Work Order (UC-G) dan tercatat di riwayat serta notifikasi.
* **BR-6 (Penugasan & Inspeksi — UC-G / UC-E):** Penilik Jalan **hanya** dapat menginspeksi tiket yang ditugaskan kepadanya: status `Ditugaskan`, atau `Menunggu Inspeksi` dengan `id_penilik` = dirinya. Tiket `Disetujui` yang belum ditugaskan tidak tampil sebagai tugas inspeksi dan POST inspeksinya ditolak; Admin wajib menugaskannya lebih dulu (UC-G). Identitas pemilik tugas dibandingkan berdasarkan ID akun, bukan nama.
* **BR-7 (Rating — UC-J / UC-L):** Satu rating per (warga, tiket). Bila dua laporan warga yang sama digabung ke satu tiket, rating kedua ditolak dengan pesan "Tiket penanganan ini sudah Anda beri penilaian melalui laporan ...". Rata-rata rating di Laporan Kinerja dihitung dari satu rating per warga unik (data lama ganda: hanya rating pertama yang dihitung).

## 4. Cakupan Skenario BDD (31 Skenario di `tests/features/`)
### Sprint 1 (17 Skenario)
* **UC-K (`uc_k_login.feature` — 5 skenario):** Login Warga, Admin, Penilik Jalan, kredensial salah, dan form kosong.
* **UC-A (`uc_a_buat_laporan.feature` — 4 skenario):** Laporan baru terbit tiket, deduplikasi otomatis, penolakan format/ukuran foto, dan penolakan objek bukan jalan.
* **UC-B (`uc_b_verifikasi.feature` — 4 skenario):** Tabel urut Risk Score, setujui tiket jelas, tugaskan inspeksi tambahan skor ambigu, dan lanjutkan tanpa inspeksi dengan log keputusan.
* **UC-G (`uc_g_penugasan.feature` — 2 skenario):** Tugaskan Penilik Jalan tersedia (`Ditugaskan`) dan penanganan saat semua penilik penuh (`Menunggu Penugasan`).
* **UC-H (`uc_h_dashboard.feature` — 2 skenario):** Peta GIS & KPI prioritas serta filter multi-parameter dengan pesan kosong.

### Sprint 2 (14 Skenario)
* **UC-C (`uc_c_lacak_status.feature` — 2 skenario):** Warga melacak detail & timeline laporan (`LAP-2026-0001`) serta penanganan nomor tiket tidak ditemukan (`LAP-9999-XXXX`).
* **UC-D (`uc_d_kelola_master_data.feature` — 2 skenario):** Admin menambah Penilik Jalan baru dengan NIP 18 digit serta penolakan duplikasi NIP/Kode Wilayah.
* **UC-E (`uc_e_inspeksi_lapangan.feature` — 2 skenario):** Penilik Jalan menyimpan pada tiket yang ditugaskan kepadanya (`Ditugaskan`) dimensi kerusakan, catatan teknis, rekomendasi, dan foto survei (`Terinspeksi`), serta penolakan form inspeksi belum lengkap.
* **UC-F (`uc_f_update_perbaikan.feature` — 3 skenario):** Admin menerbitkan SPK (`Dalam Proses`), petugas menyelesaikan perbaikan dengan unggah foto bukti (`Selesai`), serta penolakan status `Selesai` tanpa foto bukti perbaikan.
* **UC-I (`uc_i_notifikasi_status.feature` — 1 skenario):** Warga mengklik notifikasi belum dibaca, status berubah menjadi dibaca, dan diarahkan ke halaman `/lacak` laporan terkait.
* **UC-J (`uc_j_rating_ulasan.feature` — 2 skenario):** Warga mengirim rating bintang 1-5 dan ulasan pada laporan `Selesai`, serta penolakan jika bintang belum dipilih.
* **UC-L (`uc_l_laporan_kinerja.feature` — 2 skenario):** Kepala Bidang melihat rekap kinerja per wilayah (kepatuhan SLA, status SLA tiap tiket, statistik risiko) dan mengunduh CSV rekap wilayah, serta pesan `"Tidak ada data kinerja pada periode yang dipilih"` tanpa tombol unduh jika periode kosong. Jam SLA dihitung sejak tiket diterima (entri pertama `riwayat_status`) hingga `tanggal_selesai`.
