# Sprint 3 — status akhir baru "Ditutup" dengan alasan wajib (PRD BR-4, bagian 5.3).
# BELUM dihubungkan ke step definition (tidak ada scenarios()); ditulis sebelum kode.
#
# Data seed yang dipakai (sudah ada):
#   - LAP-2026-0001 -> REP-2026-00341, pelapor Bpk. Tri Wahyudi (USR-01). Seperti UC-F/UC-J, step definition
#     menyiapkan status tiket langsung di database ("Dilaporkan" untuk pintu (a)).
#   - LAP-2026-0002 -> REP-2026-00298, Ditugaskan ke Budi Santoso, pelapor Ibu Sari Rahayu (USR-03) untuk pintu (b).
#   - Akun admin@dpupr.surabaya.go.id, budi.santoso@dpupr.surabaya.go.id, 0812xxxxxxx, 0813xxxxxxx.
# Data seed baru (opsional, agar step tidak perlu mengubah status langsung):
#   - REP-2026-00370 / LAP-2026-0004: tiket "Dilaporkan" skor jelas milik USR-01 di Wilayah Gubeng.
# Kolom baru yang nanti dibutuhkan: work_order.alasan_ditutup, inspeksi.rekomendasi_tutup (+ alasan).

@sprint3
Feature: UC-B Close a Ticket with a Mandatory Reason
  As a PUPR Admin
  I want to close tickets that do not need repair, always stating the reason
  So that invalid or out-of-scope reports leave the queue and the citizen knows why

  Scenario: Admin rejects a report during verification (Happy Path)
    Given the admin opens ticket "REP-2026-00341" of report "LAP-2026-0001" with status "Dilaporkan"
    When the admin presses the "Tolak" button
    And the admin selects the closing reason "Laporan tidak valid"
    And the admin confirms with the "Tutup Tiket" button
    Then I see the ticket status change to "Ditutup"
    And the status history of "REP-2026-00341" contains "Ditutup: Laporan tidak valid"
    And the citizen "0812xxxxxxx" receives a notification containing "Laporan tidak valid"
    And the citizen cannot submit a rating for report "LAP-2026-0001"

  Scenario: Closing a ticket without a reason is rejected (Negative Path)
    Given the admin opens ticket "REP-2026-00341" of report "LAP-2026-0001" with status "Dilaporkan"
    When the admin presses the "Tolak" button
    And the admin confirms with the "Tutup Tiket" button without selecting a closing reason
    Then the system displays a warning message "Pilih alasan penutupan tiket"
    And the ticket "REP-2026-00341" keeps the status "Dilaporkan"

  Scenario: Inspector recommends closing and the admin confirms (Happy Path)
    Given the road inspector opens report details for "LAP-2026-0002" with status "Ditugaskan"
    When the road inspector selects recommendation "Rekomendasikan Tutup" with reason "Sudah diperbaiki pihak lain"
    And the road inspector selects damage level "Ringan"
    And the road inspector uploads survey photo "survei_0298.jpg" and clicks the "Simpan Hasil Inspeksi" button
    Then the system updates the report status of "LAP-2026-0002" to "Terinspeksi"
    When the admin opens the Work Order "REP-2026-00298"
    Then the admin sees the inspector recommendation "Rekomendasi penilik: tutup tiket (Sudah diperbaiki pihak lain)"
    And the "Terbitkan SPK" button is not available while the recommendation is pending
    When the admin presses the "Konfirmasi Tutup Tiket" button
    Then the ticket "REP-2026-00298" has status "Ditutup"
    And the citizen "0813xxxxxxx" receives a notification containing "Sudah diperbaiki pihak lain"

  Scenario: Admin rejects the closing recommendation and continues to the SPK (Alternative Path)
    Given ticket "REP-2026-00298" is "Terinspeksi" with an inspector recommendation to close for reason "Tidak ditemukan kerusakan"
    When the admin opens the Work Order "REP-2026-00298"
    And the admin presses the "Tolak Rekomendasi" button
    Then the ticket "REP-2026-00298" keeps the status "Terinspeksi"
    And the status history of "REP-2026-00298" contains "Rekomendasi tutup ditolak Admin"
    And the SPK form with button "Terbitkan SPK" is available for "REP-2026-00298"
