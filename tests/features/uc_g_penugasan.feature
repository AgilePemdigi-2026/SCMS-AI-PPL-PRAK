Feature: Assigning a Penilik Jalan
  In order to memastikan tiket yang telah diverifikasi ditangani oleh petugas yang tepat
  As a Admin
  I want to menugaskan Penilik Jalan

  Scenario: Successfully Assigning a Penilik Jalan
    Given I have verified ticket "REP-2026-00341"
    When I select the ticket
    Then I see an SLA recommendation of "24 jam" along with a list of available Penilik Jalan in "Wilayah Gubeng"
    When I select "Budi Santoso" as the Penilik Jalan
    Then I see the ticket status change to "Ditugaskan"

  Scenario: No Penilik Jalan Available
    Given I see ticket "REP-2026-00360" located in "Wilayah Benowo"
    When I attempt to make an assignment and find no available Penilik Jalan in that region
    Then I see the ticket marked as "Menunggu Penugasan"
