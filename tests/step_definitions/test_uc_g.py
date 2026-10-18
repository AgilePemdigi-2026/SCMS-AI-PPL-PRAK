import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from app.database import SessionLocal
from database.seed import seed_data
from app.controllers.kontrol_penugasan import KontrolPenugasan

scenarios("../features/uc_g_penugasan.feature")

@pytest.fixture
def context():
    seed_data()
    db = SessionLocal()
    yield {"db": db, "controller": KontrolPenugasan(db), "info_tiket": None, "wo": None}
    db.close()

@given(parsers.parse('I have verified ticket "{ticket_id}"'))
def verified_ticket(context, ticket_id):
    context["ticket_id"] = ticket_id

@when("I select the ticket")
def select_ticket(context):
    context["info_tiket"] = context["controller"].cek_sla_dan_ketersediaan_penilik(context["ticket_id"])

@then(parsers.parse('I see an SLA recommendation of "{sla}" along with a list of available Penilik Jalan in "{wilayah}"'))
def check_sla_and_penilik(context, sla, wilayah):
    info = context["info_tiket"]
    assert info["sla_rekomendasi"] == sla
    assert info["nama_wilayah"] == wilayah
    assert len(info["daftar_penilik"]) > 0

@when(parsers.parse('I select "{nama_penilik}" as the Penilik Jalan'))
def assign_penilik(context, nama_penilik):
    context["wo"] = context["controller"].tugaskan_penilik(context["ticket_id"], nama_penilik)

@then(parsers.parse('I see the ticket status change to "{expected_status}"'))
def verify_status_changed(context, expected_status):
    assert context["wo"].status_work_order == expected_status

@given(parsers.parse('I see ticket "{ticket_id}" located in "{wilayah}"'))
def ticket_in_region(context, ticket_id, wilayah):
    context["ticket_id"] = ticket_id
    info = context["controller"].cek_sla_dan_ketersediaan_penilik(ticket_id)
    assert info["nama_wilayah"] == wilayah

@when("I attempt to make an assignment and find no available Penilik Jalan in that region")
def attempt_assignment_no_penilik(context):
    context["wo"] = context["controller"].tugaskan_penilik(context["ticket_id"])

@then(parsers.parse('I see the ticket marked as "{expected_status}"'))
def verify_waiting_status(context, expected_status):
    assert context["wo"].status_work_order == expected_status
