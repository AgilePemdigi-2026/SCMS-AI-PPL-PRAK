Feature: UC-J Citizen Rating and Review System for Handling
  As a Reporting Citizen whose report has been successfully repaired
  I want to provide a star rating (1-5) and review comments on the quality of road repairs
  So that the PUPR Department receives feedback evaluating the field repair team's performance

  Scenario: Citizen successfully submits rating and review for a Completed report (Happy Path)
    Given the citizen opens the details of report "LAP-2026-0001" with status "Completed" and no existing rating
    When the citizen selects a "5" star rating score and writes review "Repair was very fast and neat"
    And the citizen clicks the "Submit Review" button
    Then the system saves the evaluation to the Rating table
    And the system displays a confirmation message "Thank you for your review and rating"

  Scenario: Citizen submits review without selecting a star rating (Negative Path)
    Given the citizen opens the details of report "LAP-2026-0001" with status "Completed" and no existing rating
    When the citizen leaves the star rating option blank and clicks the "Submit Review" button
    Then the system rejects the review submission
    And the system displays a warning message "Please select a star rating (1-5) first"