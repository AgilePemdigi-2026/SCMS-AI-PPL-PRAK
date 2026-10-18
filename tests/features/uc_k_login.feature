Feature: User Authentication
  In order to mengakses sistem sesuai dengan peran saya
  As a user (warga/petugas)
  I want to melakukan login

  Scenario: Successful Login as Warga
    Given I am on the "/Login" page
    And I have a registered account with phone number "0812xxxxxxx"
    When I enter my phone number and password and press the "Masuk" button
    Then I am directed to the "/Beranda" page

  Scenario: Successful Login as Petugas Dinas
    Given I am on the "/Login" page
    And I have a valid staff account "admin@dpupr.surabaya.go.id"
    When I enter my email and password and press the "Masuk" button
    Then I am directed to the "/Dashboard" page according to my role

  Scenario: Failed Login (wrong password)
    Given I am on the "/Login" page
    When I enter a registered email or phone number with an incorrect password
    Then I see the message "Email/nomor HP atau password salah"
    And I remain on the "/Login" page

  Scenario: Failed Login (account not registered)
    Given I am on the "/Login" page
    When I enter an email or phone number that is not registered
    Then I see the message "Akun tidak ditemukan"

  Scenario: Failed Login (account inactive)
    Given I am on the "/Login" page
    And my account is registered but marked as inactive
    When I enter the correct email/phone number and password
    Then I see the message "Akun Anda tidak aktif, silakan hubungi administrator"
    And I remain on the "/Login" page