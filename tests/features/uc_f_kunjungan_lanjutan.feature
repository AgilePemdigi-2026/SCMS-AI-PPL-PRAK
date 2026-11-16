# Sprint 3 — carry-over Sprint 2: perbaikan sementara & kunjungan lanjutan (PRD bagian 5.4),
# memakai kolom perbaikan.jadwal_lanjutan yang sudah ada tetapi belum dipakai.
# BELUM dihubungkan ke step definition (tidak ada scenarios()); ditulis sebelum kode.
#
# Data seed yang dipakai (sudah ada):
#   - LAP-2026-0001 -> REP-2026-00341, pelapor USR-01. Seperti UC-F, step definition menyiapkan tiket
#     "Dalam Proses" dengan penilik Budi Santoso (PNL-01) langsung di database.
# Data seed baru: tidak ada. Tanggal ditulis relatif terhadap hari tes dijalankan agar tidak kedaluwarsa.
# Kolom baru yang nanti dibutuhkan: perbaikan.perbaikan_sementara (bool), perbaikan.kunjungan_lanjutan_dicatat (bool)
#   atau penanda setara; jadwal_lanjutan disimpan sebagai tanggal ISO (YYYY-MM-DD).

@sprint3
Feature: UC-F Temporary Repair and Follow-up Visit
  As a PUPR Road Inspector supervising a repair
  I want to mark a repair as temporary and schedule a follow-up visit
  So that the ticket is only completed after the permanent repair is checked

  Scenario: Inspector records a temporary repair with a follow-up schedule (Happy Path)
    Given report "LAP-2026-0001" is in "Dalam Proses" status assigned to road inspector "Budi Santoso"
    When the officer checks "Perbaikan sementara"
    And the officer fills the follow-up visit date with the date 7 days from today
    And the officer inputs progress notes "Ditambal sementara dengan cold mix, menunggu hotmix"
    And the officer clicks the "Perbarui Status Penanganan" button
    Then the ticket "REP-2026-00341" keeps the status "Dalam Proses"
    And the follow-up visit date is shown on the "Tugas Lapangan" page
    And the citizen timeline of "LAP-2026-0001" shows "Kunjungan lanjutan dijadwalkan"

  Scenario: Ticket cannot be completed before the follow-up visit is recorded (Negative Path)
    Given report "LAP-2026-0001" is "Dalam Proses" with a pending follow-up visit 7 days from today
    When the officer selects progress status "Selesai" and uploads repair proof photo "selesai_0001.jpg"
    And the officer clicks the "Perbarui Status Penanganan" button
    Then the system rejects the WorkOrder status update
    And the system displays an error message "Catat kunjungan lanjutan terlebih dahulu sebelum menyelesaikan tiket"

  Scenario: Follow-up visit date in the past is rejected (Negative Path)
    Given report "LAP-2026-0001" is in "Dalam Proses" status assigned to road inspector "Budi Santoso"
    When the officer checks "Perbaikan sementara"
    And the officer fills the follow-up visit date with yesterday's date
    And the officer clicks the "Perbarui Status Penanganan" button
    Then the system displays a warning message "Jadwal kunjungan lanjutan harus tanggal setelah hari ini"
    And no follow-up visit is saved for "REP-2026-00341"

  # Keputusan tim 5.9 no. 7: kunjungan lanjutan boleh dicatat sebelum tanggal jadwalnya.
  Scenario: Ticket is completed after the follow-up visit is recorded early (Happy Path)
    Given report "LAP-2026-0001" is "Dalam Proses" with a pending follow-up visit 7 days from today
    When the officer records the follow-up visit today with notes "Hotmix permanen sudah dipasang"
    Then the follow-up visit is saved even though its scheduled date has not arrived
    When the officer selects progress status "Selesai" and uploads repair proof photo "selesai_0001.jpg"
    And the officer clicks the "Perbarui Status Penanganan" button
    Then the system updates the WorkOrder status and report status of "LAP-2026-0001" to "Selesai"

  # Keputusan tim 5.9 no. 7: boleh dijadwalkan ulang berkali-kali secara berurutan, hanya satu jadwal aktif.
  Scenario: Rescheduling replaces the single active follow-up visit (Boundary Path)
    Given report "LAP-2026-0001" is "Dalam Proses" with a pending follow-up visit 7 days from today
    When the officer reschedules the follow-up visit to the date 14 days from today
    Then "REP-2026-00341" has exactly one active follow-up visit, dated 14 days from today
    And the earlier schedule is kept in the status history as "Kunjungan lanjutan dijadwalkan ulang"
    And the "Tugas Lapangan" page shows only the date 14 days from today
