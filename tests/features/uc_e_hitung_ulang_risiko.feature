# Sprint 3 — carry-over Sprint 2: hitung ulang Risk Score setelah inspeksi (PRD BR-2, bagian 5.4).
# BELUM dihubungkan ke step definition (tidak ada scenarios()); ditulis sebelum kode.
#
# Data seed yang dipakai (sudah ada):
#   - REP-2026-00298 / LAP-2026-0002: Ditugaskan ke Budi Santoso (PNL-01), pelapor Ibu Sari Rahayu (USR-03),
#     Jalan Berlubang, Arteri Primer, S AI 8.0, E 1, V 8.0 -> Risk Score 8.0 (Urgent).
#   - Nilai harapan dihitung dengan formula BR-2 yang sama (risk_scoring.nilai_risiko):
#       Ringan (S=3) -> 5.5 Borderline; Sedang (5) -> 6.5 Tinggi; Berat (7) -> 7.5 Tinggi; Sangat Berat (9) -> 8.5 Urgent.
# Data seed baru: tidak ada. Kolom baru yang nanti dibutuhkan: inspeksi.kategori_terkonfirmasi,
#   inspeksi.tingkat_kerusakan, inspeksi.severity_lapangan, work_order.severity_ai (severity AI asli untuk perbandingan).

@sprint3
Feature: UC-E Recalculate Risk Score from Field Inspection
  As a PUPR Road Inspector assigned to a ticket
  I want to confirm the damage category and choose the field damage level during inspection
  So that the ticket priority reflects the real condition on site instead of only the AI estimate

  Scenario: Field damage level lowers the Risk Score and priority (Happy Path)
    Given the road inspector opens report details for "LAP-2026-0002" with status "Ditugaskan"
    And the ticket "REP-2026-00298" has Risk Score "8.0" with priority "Urgent"
    When the road inspector confirms the category "Jalan Berlubang"
    And the road inspector selects damage level "Ringan"
    And the road inspector fills in the remaining inspection fields and uploads survey photo "survei_0298.jpg"
    And the road inspector clicks the "Simpan Hasil Inspeksi" button
    Then the system updates the report status of "LAP-2026-0002" to "Terinspeksi"
    And the ticket "REP-2026-00298" has Risk Score "5.5" with priority "Borderline"
    And the ticket keeps the AI severity "8.0" for comparison next to the field severity "3"
    And the status history of "REP-2026-00298" contains "Risk Score diperbarui 8.0 → 5.5 berdasarkan inspeksi"

  Scenario: Field damage level raises the priority and the map colour follows (Happy Path)
    Given the road inspector opens report details for "LAP-2026-0002" with status "Ditugaskan"
    When the road inspector confirms the category "Jalan Berlubang"
    And the road inspector selects damage level "Sangat Berat"
    And the road inspector fills in the remaining inspection fields and uploads survey photo "survei_0298.jpg"
    And the road inspector clicks the "Simpan Hasil Inspeksi" button
    Then the ticket "REP-2026-00298" has Risk Score "8.5" with priority "Urgent"
    And the priority badge of "REP-2026-00298" on the Dashboard uses the colour of priority "Urgent"

  Scenario: Inspection without a damage level is rejected (Negative Path)
    Given the road inspector opens report details for "LAP-2026-0002" with status "Ditugaskan"
    When the road inspector confirms the category "Jalan Berlubang"
    And the road inspector leaves the damage level empty
    And the road inspector fills in the remaining inspection fields and uploads survey photo "survei_0298.jpg"
    And the road inspector clicks the "Simpan Hasil Inspeksi" button
    Then the system aborts saving the inspection data
    And the system displays a warning message "Pilih tingkat kerusakan hasil inspeksi lapangan"
    And the ticket "REP-2026-00298" still has Risk Score "8.0" with priority "Urgent"

  # Keputusan tim 5.9 no. 6: tingkat kerusakan tidak wajib HANYA untuk rekomendasi tutup
  # dengan alasan "Tidak ditemukan kerusakan"; tanpa tingkat kerusakan, Risk Score tidak dihitung ulang.
  Scenario Outline: Damage level is optional only when no damage is found (Boundary Path)
    Given the road inspector opens report details for "LAP-2026-0002" with status "Ditugaskan"
    When the road inspector selects recommendation "Rekomendasikan Tutup" with reason "<alasan>"
    And the road inspector leaves the damage level empty
    And the road inspector uploads survey photo "survei_0298.jpg" and clicks the "Simpan Hasil Inspeksi" button
    Then the inspection result is "<hasil>"
    And the ticket "REP-2026-00298" still has Risk Score "8.0" with priority "Urgent"

    Examples:
      | alasan                      | hasil                                                    |
      | Tidak ditemukan kerusakan   | Terinspeksi                                              |
      | Sudah diperbaiki pihak lain | Pilih tingkat kerusakan hasil inspeksi lapangan          |
