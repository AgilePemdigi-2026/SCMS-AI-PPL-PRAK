# Sprint 3 — backlog 1: pengiriman & pengiriman ulang notifikasi (PRD BR-8, bagian 5.3).
#
# Data seed yang dipakai (sudah ada):
#   - REP-2026-00341 / LAP-2026-0001 berstatus "Disetujui", pelapor Bpk. Tri Wahyudi (USR-01, 0812xxxxxxx).
#   - Budi Santoso (PNL-01) "Tersedia" di Wilayah Gubeng, admin@dpupr.surabaya.go.id.
#   - Kolom notifikasi.status_kirim sudah ada (default "Terkirim").
# Konfigurasi baru: env SCMS_NOTIF_TINGKAT_GAGAL (0.0–1.0, bawaan 0.0). Tes memakai 1.0 untuk memaksa gagal.
# Kolom baru yang nanti dibutuhkan: notifikasi.jumlah_percobaan, notifikasi.waktu_percobaan_terakhir.

@sprint3
Feature: UC-I Notification Delivery and Resend
  As a PUPR Admin
  I want every status notification to record its delivery status and be resent when it fails
  So that citizens are not left without news about their report

  Scenario: Notification is delivered on the first attempt (Happy Path)
    Given the notification delivery channel failure rate is "0"
    When the admin assigns road inspector "Budi Santoso" to ticket "REP-2026-00341"
    Then the citizen "0812xxxxxxx" receives a notification for report "LAP-2026-0001"
    And the notification delivery status is "Terkirim" after 1 attempt

  Scenario: Failed notification is retried automatically and listed as failed (Negative Path)
    Given the notification delivery channel failure rate is "1"
    When the admin assigns road inspector "Budi Santoso" to ticket "REP-2026-00341"
    Then the ticket "REP-2026-00341" has status "Ditugaskan"
    And the notification for report "LAP-2026-0001" has delivery status "Gagal" after 3 automatic retries
    And the notification delivery attempt count is 4 (1 initial send + 3 retries)
    And the notification appears on the "Notifikasi Gagal" page with the "Kirim Ulang" button

  Scenario: Admin resends a failed notification (Happy Path)
    Given a notification for report "LAP-2026-0001" has delivery status "Gagal"
    And the notification delivery channel failure rate is "0"
    When the admin opens the "Notifikasi Gagal" page
    And the admin clicks the "Kirim Ulang" button for report "LAP-2026-0001"
    Then the system displays the message "Notifikasi berhasil dikirim ulang"
    And the notification delivery status is "Terkirim"
    And the notification no longer appears on the "Notifikasi Gagal" page

  Scenario: Head of Division cannot resend notifications (Negative Path)
    Given a notification for report "LAP-2026-0001" has delivery status "Gagal"
    When the head of division opens the "Notifikasi Gagal" page
    Then the head of division does not see the "Kirim Ulang" button
    And a direct resend request by the head of division is rejected with status 403
