import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from app.database import SessionLocal
from database.seed import seed_data
from app.controllers.kontrol_autentikasi import KontrolAutentikasi

scenarios("../features/uc_k_login.feature")

@pytest.fixture
def auth_context():
    seed_data()
    db = SessionLocal()
    yield {
        "db": db,
        "controller": KontrolAutentikasi(db),
        "current_page": None,
        "identifier": None,
        "result": None
    }
    db.close()

@given(parsers.parse('I am on the "{page}" page'))
def on_login_page(auth_context, page):
    auth_context["current_page"] = page

@given(parsers.parse('I have a registered account with phone number "{phone}"'))
def registered_warga_account(auth_context, phone):
    auth_context["identifier"] = phone

@given(parsers.parse('I have a valid staff account "{email}"'))
def valid_staff_account(auth_context, email):
    auth_context["identifier"] = email

@given("my account is registered but marked as inactive")
def inactive_account(auth_context):
    # Di database/seed.py, akun USR-02 (0899xxxxxxx / nonaktif@gmail.com) diset is_active=False
    auth_context["identifier"] = "0899xxxxxxx"

@when('I enter my phone number and password and press the "Masuk" button')
def login_with_phone(auth_context):
    auth_context["result"] = auth_context["controller"].autentikasi(
        auth_context["identifier"], "password123"
    )

@when('I enter my email and password and press the "Masuk" button')
def login_with_email(auth_context):
    auth_context["result"] = auth_context["controller"].autentikasi(
        auth_context["identifier"], "password123"
    )

@when("I enter a registered email or phone number with an incorrect password")
def login_wrong_password(auth_context):
    auth_context["result"] = auth_context["controller"].autentikasi(
        "admin@dpupr.surabaya.go.id", "password_salah_123"
    )

@when("I enter an email or phone number that is not registered")
def login_unregistered_account(auth_context):
    auth_context["result"] = auth_context["controller"].autentikasi(
        "belum.terdaftar@surabaya.go.id", "password123"
    )

@when("I enter the correct email/phone number and password")
def login_correct_credentials_for_inactive(auth_context):
    auth_context["result"] = auth_context["controller"].autentikasi(
        auth_context["identifier"], "password123"
    )

@then(parsers.parse('I am directed to the "{target_page}" page'))
def verify_redirect_warga(auth_context, target_page):
    assert auth_context["result"]["success"] is True
    assert auth_context["result"]["redirect_url"] == target_page

@then(parsers.parse('I am directed to the "{target_page}" page according to my role'))
def verify_redirect_staff(auth_context, target_page):
    assert auth_context["result"]["success"] is True
    assert auth_context["result"]["redirect_url"] == target_page

@then(parsers.parse('I see the message "{expected_message}"'))
def verify_error_message(auth_context, expected_message):
    assert auth_context["result"]["message"] == expected_message

@then(parsers.parse('I remain on the "{page}" page'))
def verify_remain_on_login(auth_context, page):
    assert auth_context["result"]["redirect_url"] == page