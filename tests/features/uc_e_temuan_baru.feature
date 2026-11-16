# Sprint 3 — carry-over Sprint 2: temuan baru saat inspeksi (PRD bagian 5.4).
# BELUM dihubungkan ke step definition (tidak ada scenarios()); ditulis sebelum kode.
#
# Data seed yang dipakai (sudah ada):
#   - REP-2026-00298 / LAP-2026-0002 Ditugaskan ke Budi Santoso, Jalan Berlubang, titik (-7.26550, 112.74700).
#   - REP-2026-00341 aktif, Jalan Berlubang, Jl. Raya Kertajaya No. 50 (-7.27970, 112.76180) untuk uji BR-3.
# Data/kolom baru yang nanti dibutuhkan:
#   - Keputusan tim 5.9 no. 3: laporan.id_warga menjadi nullable, kolom baru laporan.sumber
#     ("Warga" | "Temuan Penilik") dan laporan.id_penilik_pencatat.
#   - Notifikasi hanya untuk warga pelapor: tiket temuan murni tidak mengirim notifikasi warga; bila
#     kemudian laporan warga digabung (BR-3) ke tiket temuan, warga itu menerima notifikasi.
#   - Titik temuan > 50 m dari tiket aktif lain berkategori sama: (-7.26700, 112.74950) "Jl. Sudirman No. 80".

@sprint3
Feature: UC-E Record a New Finding During Inspection
  As a PUPR Road Inspector on site
  I want to record other damage I find around the inspected location
  So that it becomes a new ticket without waiting for a citizen to report it

  Scenario: Inspector records a new finding that becomes a new ticket (Happy Path)
    Given the road inspector opens report details for "LAP-2026-0002" with status "Ditugaskan"
    When the road inspector opens the "Catat Temuan Baru" form
    And the road inspector uploads finding photo "temuan_sudirman_80.jpg"
    And the road inspector selects finding category "Retak Permukaan"
    And the road inspector enters finding description "Retak memanjang di bahu jalan sekitar 3 meter"
    And the road inspector marks the finding point "-7.26700, 112.74950" on the map
    And the road inspector clicks the "Simpan Temuan" button
    Then the system creates a new ticket with source "Temuan Penilik" and status "Dilaporkan"
    And the new report has no reporting citizen and is recorded by road inspector "Budi Santoso"
    And the new ticket appears in the Verifikasi queue
    And the ticket "REP-2026-00298" keeps the status "Ditugaskan"
    And no citizen notification is created for the new ticket

  Scenario: Citizen report merged into a finding ticket gets notifications (Alternative Path)
    Given a finding ticket with source "Temuan Penilik" and category "Retak Permukaan" exists at "-7.26700, 112.74950" with status "Dilaporkan"
    When the citizen "0812xxxxxxx" submits a "Retak Permukaan" report at the same point with a similar description
    Then the citizen report is merged into the finding ticket
    And the citizen "0812xxxxxxx" receives the notification "Laporan digabungkan"
    When the admin approves the finding ticket
    Then the citizen "0812xxxxxxx" receives a status notification for the finding ticket

  Scenario: Finding close to an active ticket is merged by BR-3 deduplication (Alternative Path)
    Given the road inspector opens report details for "LAP-2026-0002" with status "Ditugaskan"
    When the road inspector records a finding with category "Jalan Berlubang" at point "-7.27975, 112.76185" with photo "temuan_kertajaya.jpg"
    And the road inspector clicks the "Simpan Temuan" button
    Then no new ticket is created
    And the finding is merged into ticket "REP-2026-00341"
    And the system displays the message "Temuan digabungkan dengan tiket aktif REP-2026-00341"

  Scenario: Finding without a photo is rejected (Negative Path)
    Given the road inspector opens report details for "LAP-2026-0002" with status "Ditugaskan"
    When the road inspector fills in the finding category, description and map point without uploading a photo
    And the road inspector clicks the "Simpan Temuan" button
    Then the system displays a warning message "Foto temuan wajib diunggah"
    And no new ticket is created
