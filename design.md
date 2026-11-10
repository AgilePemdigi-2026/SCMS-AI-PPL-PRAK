# UI/UX & System Design Specification (design.md)
# SCMS-AI: Smart Complaint Management System — Dinas PUPR Kota Surabaya

**Versi Dokumen:** 2.0 (Sprint 1 & Sprint 2 Integrated)  
**CSS Framework:** Tailwind CSS (Utility-First)  
**Font Family:** `Inter`, sans-serif (Google Fonts)  
**Peta Geospasial:** Leaflet.js `1.9.4` + OpenStreetMap + Nominatim Geocoding API  

## 1. Filosofi Desain & Identitas Visual
1. **Clarity Over Decoration:** Mengutamakan keterbacaan data tabel prioritas, kejelasan metrik skor AI (*Severity* & *Risk Score*), dan kemudahan navigasi.
2. **Color-Coded Urgency:** Warna mencolok (Merah `#DC2626` untuk >= 8.0 Urgent, Oranye `#EA580C` untuk 6.0-7.9 Tinggi, Amber `#D97706` untuk 4.0-5.9 Borderline, Hijau `#16A34A` untuk < 4.0 / Selesai) hanya digunakan untuk tingkat risiko, status tiket, atau pesan sistem (`#pesanSistem`).
3. **Progressive Disclosure & Transparency:** Pelaporan warga menggunakan *4-Step Wizard*, sedangkan pelacakan laporan menampilkan *Vertical 5-Stage Timeline* beserta perbandingan foto bukti lapangan (*Before – Survey – After*).

## 2. Struktur Navigasi (`_layout.html`)
* **Admin & Kepala Bidang:** `Dashboard Prioritas` (`/Dashboard`), `Verifikasi Laporan` (`/verifikasi`), `Work Order & SPK` (`/work-orders`), `Data Master` (`/master-data`), dan `Laporan Kinerja` (`/laporan-kinerja`).
* **Penilik Jalan:** `Tugas Lapangan` (`/TugasLapangan`), `Dashboard Prioritas` (`/Dashboard`), dan `Daftar Work Order` (`/work-orders`).
* **Warga:** `Beranda` (`/Beranda`), `Buat Laporan` (`/lapor`), `Riwayat & Lacak Laporan` (`/lacak`), serta `Notifikasi` (`/notifikasi` dengan lencana `#badgeNotif`).

## 3. Spesifikasi Antarmuka per Use Case
### 3.1 Modul Sprint 1 (`UC-K`, `UC-A`, `UC-B`, `UC-G`, `UC-H`)
* **`login.html` & `register.html` (UC-K):** Autentikasi satu pintu (Nomor HP/Email/NIK untuk Warga, Email/NIP 18 digit untuk Staf) dan registrasi warga baru.
* **`buat_laporan.html` (UC-A):** 4-Step Wizard (Step 1 Capture + `/api/analisis-foto` -> Step 2 Location Leaflet & Nominatim -> Step 3 Detail -> Step 4 Review & Submit).
  - **Kotak Deteksi YOLOv8 v4:** Kotak hasil deteksi (`kotak` dari `/api/analisis-foto`, koordinat ternormalisasi 0-1) digambar di atas pratinjau foto pada `#kanvasCapture` (Step 1) dan thumbnail `#kanvasDetail` (Step 3), dengan warna per kategori (Jalan Berlubang Merah `#DC2626`, Retak Permukaan Oranye `#F97316`, Jalan Amblas Ungu `#7C3AED`) beserta label dan persentase confidence. Pada mode simulasi tidak ada kotak dan angka confidence.
  - **Kategori Diganti Warga (PRD BR-2):** Jika warga memilih kategori yang berbeda dari rekomendasi AI, ditampilkan catatan "Kategori diubah dari rekomendasi AI (...). Severity memakai nilai dasar kategori dan akan ditinjau petugas." dan severity memakai nilai dasar kategori (`severity_dasar`).
* **`dashboard_prioritas.html` (UC-H):** 4 Kartu KPI, filter Wilayah/Status/Kategori, peta interaktif `#mapSurabaya`, ringkasan zona risiko, dan tabel antrean prioritas dengan tombol aksi cepat.
* **`verifikasi_detail.html` (UC-B):** Panel keputusan kondisional untuk skor jelas (`Setujui Tiket`) vs skor ambigu 4.0-6.0 (`Tugaskan Inspeksi Tambahan` atau `Lanjutkan Tanpa Inspeksi`).
* **`work_order_list.html` (UC-G & UC-F):** Tabel Work Order di kiri dan panel kontekstual di kanan (Form Penugasan Penilik untuk status `Disetujui`/`Menunggu Penugasan`, Form Penerbitan SPK untuk status `Terinspeksi`, dan Form Progres/Penutupan untuk status `Dalam Proses`).

### 3.2 Modul Sprint 2 (`UC-C`, `UC-D`, `UC-E`, `UC-F`, `UC-I`, `UC-J`, `UC-L`)
* **`lacak_laporan.html` (UC-C & UC-J):** Input pencarian `#inputIdLaporan` + `#tombolCariLaporan`, panel `#detailLaporan`, linimasa 5 tahap (`#linimasaProgres`), riwayat status berformat WIB (`#riwayatStatus`), galeri 3 foto bukti (Laporan, Survei, Selesai), dan `#formRating` (bintang 1-5 + `#komentar` + `#tombolKirimUlasan` khusus status `Selesai`).
* **`master_data.html` (UC-D):** Form tambah Wilayah Rayon dan form tambah Penilik Jalan (`#nip` 18 digit, `#nama_penilik`, `#id_wilayah`, `#email_penilik`), kotak kata sandi sementara sekali tampil (`select-all`), serta pengubah status ketersediaan petugas (`Tersedia`, `Bertugas`, `Cuti`).
* **`tugas_lapangan.html` & `tugas_lapangan_detail.html` (UC-E & UC-F):** Daftar tiket khusus wilayah rayon Penilik Jalan yang login, form hasil inspeksi lapangan (`#dimensi_kerusakan`, `#rekomendasi`, `#catatan_teknis`, `#foto_survei`, `#simpanInspeksi`), dan form update progres perbaikan (`#status_baru`, `#catatan_progres`, `#foto_selesai`, `#perbaruiStatus`).
* **`notifikasi.html` (UC-I):** Daftar kartu notifikasi (`#notif-{id_notifikasi}`), kelas `.notif-belum-dibaca`, tombol tandai semua dibaca, dan redirect otomatis ke `/lacak?id={id_laporan}`.
* **`laporan_kinerja.html` (UC-L):** Form filter `#formFilterKinerja` (`#tanggal_mulai`, `#tanggal_akhir`, `#filter_wilayah`, `#tampilkanLaporan`), 5 kartu KPI `#kpiKinerja` (`#kpiTotal`, `#kpiPenyelesaian`, `#kpiKepatuhan`, `#kpiDurasi`, `#kpiLewatSla`), tabel rekap `#tabelWilayah` dan `#tabelPrioritas` (termasuk rata-rata Risk Score dan rating warga), tabel detail `#tabelTiket` dengan lencana status SLA (`Tepat Waktu` Hijau, `Dalam SLA` Biru, `Terlambat` / `Melewati SLA` Merah), tombol `#unduhWilayah` / `#unduhTiket` (CSV) dan `#cetakLaporan` (cetak/PDF browser), serta `#pesanKosong` ("Tidak ada data kinerja pada periode yang dipilih") tanpa tombol unduh saat periode kosong.

## 4. Pemetaan Diagram Desain UML (`docs/`)
Seluruh Activity Diagram (`docs/activity_diagrams/*.puml`) dan Sequence Diagram (`docs/sequence_diagrams/*.puml`) tersedia untuk ke-12 Use Case: `uc_k_login`, `uc_a_buat_laporan`, `uc_b_verifikasi`, `uc_c_lacak_status`, `uc_d_kelola_master_data`, `uc_e_inspeksi_lapangan`, `uc_f_update_perbaikan`, `uc_g_penugasan`, `uc_h_dashboard`, `uc_i_notifikasi_status`, `uc_j_rating_ulasan`, dan `uc_l_laporan_kinerja`.