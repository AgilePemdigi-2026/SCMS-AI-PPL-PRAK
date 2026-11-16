# Sprint 3 — carry-over Sprint 2: AI tidak pernah menolak laporan (PRD BR-1, keputusan tim 5.9 no. 4).
# BELUM dihubungkan ke step definition (tidak ada scenarios()); ditulis sebelum kode.
#
# Aturan: berkas yang lolos BR-1 (JPEG/PNG asli, <= 10 MB) SELALU diterima, di backend simulasi maupun yolov8.
# Foto yang tidak terdeteksi kerusakannya ATAU tampak bukan jalan -> label "Perlu tinjauan manual".
# Admin dapat menolaknya saat verifikasi dengan alasan "Laporan tidak valid" (status Ditutup, BR-4).
#
# REVISI skenario Sprint 1: skenario 2 di bawah menggantikan skenario UC-A
# "Photo Does Not Contain a Road Damage Object" (kucing.jpg ditolak). Teks skenario lama di
# uc_a_buat_laporan.feature diganti bersamaan dengan kode UC-A.
#
# Data seed yang dipakai (sudah ada): akun warga 0812xxxxxxx (Bpk. Tri Wahyudi), admin@dpupr.surabaya.go.id.
# Data/konfigurasi baru yang nanti dibutuhkan:
#   - Backend simulasi: nama berkas berisi "tanpa_deteksi" = gambar valid tanpa kotak deteksi; kata kunci
#     bukan-jalan ("kucing", "selfie", ...) tidak lagi menolak, melainkan juga "Perlu tinjauan manual".
#   - Foto uji "tanpa_deteksi_jl_kenjeran.jpg" dan "kucing.jpg" dibuat step definition (JPEG asli, < 10 MB).
#   - Kolom baru: laporan.perlu_tinjauan_manual (bool) atau penanda setara di work_order.

@sprint3
Feature: UC-A Report with a Photo the AI Cannot Classify
  As a Warga
  I want my report to be accepted even when the AI does not recognise the damage in my valid photo
  So that real damage is still handled after an officer reviews it manually

  Scenario: Valid photo without AI detection is accepted for manual review (Happy Path)
    Given I am logged in and on the "Buat Laporan" page
    When I upload a valid road photo "tanpa_deteksi_jl_kenjeran.jpg" in which the AI detects nothing
    Then I see the notice "Perlu tinjauan manual"
    And I can proceed to the next step
    When I select the location "Jl. Kenjeran No. 100, Surabaya" via GPS
    And I choose the category "Jalan Berlubang" myself
    And I enter the description "Aspal mengelupas dan berlubang di depan pasar"
    And I press the "Kirim Laporan" button
    Then I receive a new ticket number with initial status "Dilaporkan"
    And the new ticket is labelled "Perlu tinjauan manual" in the Verifikasi queue

  Scenario: Photo that looks like a non-road object goes to manual review (Revised Sprint 1 Path)
    Given I am logged in and on the "Buat Laporan" page
    When I upload a valid photo that does not show road damage, such as "kucing.jpg"
    Then I do not see the warning "Objek jalan rusak tidak terdeteksi, silakan ambil ulang foto"
    And I see the notice "Perlu tinjauan manual"
    When I complete the location, category and description steps and press the "Kirim Laporan" button
    Then I receive a new ticket number with initial status "Dilaporkan"
    And the new ticket is labelled "Perlu tinjauan manual" in the Verifikasi queue

  Scenario: Manual-review ticket is treated as an ambiguous score and can be rejected (Happy Path)
    Given a ticket labelled "Perlu tinjauan manual" with status "Dilaporkan" reported by citizen "0812xxxxxxx"
    When the admin opens the ticket on the Verifikasi page
    Then I see the options "Tugaskan Inspeksi Tambahan", "Lanjutkan Tanpa Inspeksi" and "Tolak"
    And I do not see the "Setujui Tiket" button
    And the Dashboard quick-approve of that ticket is rejected
    When the admin presses the "Tolak" button and closes the ticket with reason "Laporan tidak valid"
    Then I see the ticket status change to "Ditutup"
    And the citizen "0812xxxxxxx" receives a notification containing "Laporan tidak valid"

  Scenario: Invalid file is still rejected under BR-1 (Negative Path)
    Given I am on the "Buat Laporan" page
    When I upload a file named "tanpa_deteksi.pdf" that is not a real JPEG or PNG image
    Then I see the error message "Format harus JPG/PNG dan ukuran maksimal 10MB"
    And I cannot proceed to the next step
