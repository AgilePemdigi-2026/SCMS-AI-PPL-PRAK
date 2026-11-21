"""
Session-based login and role checks.

After a successful login the session cookie (signed by Starlette's SessionMiddleware) holds
only the account id, role and session version (C-01): no name or email. The cookie is signed but
readable by its holder and stays valid until max_age, so every request re-reads the account from
the database: an inactive account, a changed role or a raised `versi_sesi` (logout, password
change) ends the session even for an old copy of the cookie. The name and email the templates
need are taken from that same database row. Routes declare who may use them with
`Depends(wajib_peran(...))`.
"""
from typing import Optional
from urllib.parse import quote

from fastapi import Request

PERAN_WARGA = "Warga"
PERAN_ADMIN = "Admin"
PERAN_KABID = "Kepala Bidang"
PERAN_PENILIK = "Penilik Jalan"
PERAN_STAF = (PERAN_ADMIN, PERAN_KABID, PERAN_PENILIK)

HALAMAN_AWAL = {
    PERAN_WARGA: "/Beranda",
    PERAN_ADMIN: "/Dashboard",
    PERAN_KABID: "/Dashboard",
    PERAN_PENILIK: "/TugasLapangan",
}


class LoginDiperlukan(Exception):
    def __init__(self, tujuan: str):
        self.tujuan = tujuan


class AksesDitolak(Exception):
    def __init__(self, pengguna: dict):
        self.pengguna = pengguna


def _model_peran(peran: Optional[str]):
    from app.models.entities import Admin, PenilikJalan, Warga

    return {PERAN_WARGA: Warga, PERAN_ADMIN: Admin, PERAN_KABID: Admin, PERAN_PENILIK: PenilikJalan}.get(peran)


def _nama_email(akun) -> tuple:
    from app.models.entities import Admin, PenilikJalan

    if isinstance(akun, Admin):
        return akun.nama_admin, akun.email_admin
    if isinstance(akun, PenilikJalan):
        return akun.nama_penilik, akun.email_penilik
    return akun.nama_warga, akun.email


def muat_akun(sesi: Optional[dict]) -> Optional[dict]:
    """The logged-in user for a session entry, checked against the database, or None.

    Rejected: unknown role or account, inactive account, a Kepala Bidang flag that changed since
    login, and a session version different from the account's `versi_sesi` (also a cookie from
    before C-01, which has no version). Returns a NEW dict (id, peran, versi, nama, email): the
    session entry itself is never changed, so the name and email never go into the cookie."""
    if not isinstance(sesi, dict):
        return None
    model = _model_peran(sesi.get("peran"))
    versi = sesi.get("versi")
    if model is None or not isinstance(versi, int) or isinstance(versi, bool):
        return None
    from app.database import SessionLocal
    from app.models.entities import Admin

    db = SessionLocal()
    try:
        akun = db.get(model, sesi.get("id"))
        if akun is None or not akun.is_active:
            return None
        if model is Admin and (sesi["peran"] == PERAN_KABID) != bool(akun.is_kepala_bidang):
            return None  # role changed since login
        if (akun.versi_sesi or 0) != versi:
            return None  # logged out (or password changed) since this cookie was issued
        nama, email = _nama_email(akun)
        return {"id": sesi["id"], "peran": sesi["peran"], "versi": versi, "nama": nama, "email": email}
    finally:
        db.close()


def akun_masih_aktif(pengguna: dict) -> bool:
    """Re-check the account, so deactivating it or logging out ends existing sessions."""
    return muat_akun(pengguna) is not None


def pengguna_saat_ini(request: Request) -> Optional[dict]:
    """The checked user of this request (see muat_akun), or None. Read once per request: the
    result is kept in request.state for as long as the session entry is the same object."""
    sesi = request.session.get("pengguna")
    cache = getattr(request.state, "scms_pengguna", None)
    if cache is not None and cache[0] is sesi:
        return cache[1]
    hasil = muat_akun(sesi) if sesi else None
    request.state.scms_pengguna = (sesi, hasil)
    return hasil


def simpan_login(request: Request, hasil_autentikasi: dict) -> None:
    request.session.clear()
    request.session["pengguna"] = {
        "id": hasil_autentikasi["id"],
        "peran": hasil_autentikasi["role"],
        "versi": int(hasil_autentikasi.get("versi_sesi") or 0),
    }


def akhiri_semua_sesi(db, akun) -> None:
    """Raise the account's session version (atomic UPDATE): every cookie issued before, on any
    device, is rejected from the next request on. The caller commits."""
    model = type(akun)
    kunci = model.__mapper__.primary_key[0]
    db.query(model).filter(kunci == getattr(akun, kunci.key)).update(
        {model.versi_sesi: model.versi_sesi + 1}, synchronize_session=False)


def keluar(request: Request, akhiri_sesi: bool = False) -> None:
    """Clear the session. With akhiri_sesi=True (POST /Logout) the account's versi_sesi is raised
    too, so a copy of the old cookie no longer works."""
    sesi = request.session.get("pengguna")
    if akhiri_sesi and isinstance(sesi, dict):
        model = _model_peran(sesi.get("peran"))
        if model is not None:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                akun = db.get(model, sesi.get("id"))
                if akun is not None:
                    akhiri_semua_sesi(db, akun)
                    db.commit()
            finally:
                db.close()
    request.session.clear()


def tujuan_aman(tujuan: Optional[str]) -> Optional[str]:
    """Allow only same-site relative paths as post-login redirect targets."""
    if tujuan and tujuan.startswith("/") and not tujuan.startswith("//") and "\\" not in tujuan:
        return tujuan
    return None


def wajib_peran(*peran_diizinkan: str):
    """FastAPI dependency: require a logged-in user with one of the given roles."""

    def _cek(request: Request) -> dict:
        pengguna = pengguna_saat_ini(request)
        if pengguna is None and request.session.get("pengguna"):
            keluar(request)  # rejected session (inactive, role changed, logged out): drop the cookie
        if not pengguna:
            # Come back to the same page after login (GET only: a POST action can't be replayed as GET).
            tujuan = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            raise LoginDiperlukan(quote(tujuan, safe="") if request.method == "GET" else "")
        if peran_diizinkan and pengguna["peran"] not in peran_diizinkan:
            raise AksesDitolak(pengguna)
        return pengguna

    return _cek
