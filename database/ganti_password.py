"""
Change account passwords on a server (never run automatically).

    python -m database.ganti_password --identifier <email / no_hp / NIK / NIP>
    python -m database.ganti_password --semua-staf

The new password is read with getpass (hidden, typed twice) and never from a command-line argument
(those end up in shell history and process lists). Rules: at least 10 characters and not the demo
password "password123". It is hashed with bcrypt (the same CryptContext as login) and the account's
versi_sesi is raised, so every session that was open with the old password ends (C-01).

--semua-staf asks for a new password for every Admin, Kepala Bidang and Penilik Jalan account in
turn (one each; press Enter on an empty prompt to skip an account).
"""
import argparse
import getpass
import sys
from typing import Callable, Optional

from app.auth import akhiri_semua_sesi
from app.controllers.kontrol_autentikasi import KontrolAutentikasi, pwd_context
from app.database import Base, SessionLocal, engine, pastikan_kolom_terbaru
from app.models.entities import Admin, PenilikJalan

PANJANG_MINIMAL = 10
PASSWORD_DILARANG = {"password123"}


class PasswordDitolak(ValueError):
    pass


def validasi_password(password: str) -> None:
    """Raise PasswordDitolak with a readable reason when the password is not allowed."""
    if password is None or len(password) < PANJANG_MINIMAL:
        raise PasswordDitolak(f"Password minimal {PANJANG_MINIMAL} karakter.")
    if password.strip().lower() in PASSWORD_DILARANG:
        raise PasswordDitolak("Password demo 'password123' tidak boleh dipakai.")


def label_akun(akun) -> str:
    if isinstance(akun, Admin):
        return f"{akun.id_admin} {akun.nama_admin} <{akun.email_admin}>"
    if isinstance(akun, PenilikJalan):
        return f"{akun.id_penilik} {akun.nama_penilik} <{akun.email_penilik or akun.nip}>"
    return f"{akun.id_warga} {akun.nama_warga} <{akun.no_hp}>"


def setel_password(db, akun, password: str) -> None:
    """Validate, hash and store the password and end the account's open sessions (one commit)."""
    validasi_password(password)
    akun.password_hash = pwd_context.hash(password)
    akhiri_semua_sesi(db, akun)
    db.commit()


def tanya_password(label: str, baca: Callable[[str], str] = getpass.getpass,
                   boleh_lewati: bool = False) -> Optional[str]:
    """Ask twice until the password is valid and both entries match. None = skipped (empty)."""
    while True:
        pertama = baca(f"Password baru untuk {label}: ")
        if not pertama and boleh_lewati:
            return None
        try:
            validasi_password(pertama)
        except PasswordDitolak as e:
            print(f"  Ditolak: {e}")
            continue
        if baca("Ulangi password baru: ") != pertama:
            print("  Ditolak: kedua password tidak sama.")
            continue
        return pertama


def akun_staf(db) -> list:
    return db.query(Admin).order_by(Admin.id_admin).all() + db.query(PenilikJalan).order_by(PenilikJalan.id_penilik).all()


def main(argv=None, baca: Callable[[str], str] = getpass.getpass) -> int:
    parser = argparse.ArgumentParser(prog="python -m database.ganti_password",
                                     description="Ganti password akun SCMS-AI (password dibaca dengan getpass).")
    grup = parser.add_mutually_exclusive_group(required=True)
    grup.add_argument("--identifier", help="email, nomor HP, NIK, atau NIP akun")
    grup.add_argument("--semua-staf", action="store_true", help="semua akun Admin, Kepala Bidang, dan Penilik Jalan")
    args = parser.parse_args(argv)

    Base.metadata.create_all(bind=engine)
    pastikan_kolom_terbaru()  # versi_sesi must exist even if the app has not started since the update
    db = SessionLocal()
    try:
        if args.identifier:
            akun, peran = KontrolAutentikasi(db).cari_akun(args.identifier)
            if akun is None:
                print(f"Akun dengan identifier '{args.identifier}' tidak ditemukan.")
                return 1
            label = f"{peran} {label_akun(akun)}"
            setel_password(db, akun, tanya_password(label, baca))
            print(f"Password {label} diganti; semua sesi lama akun ini berakhir.")
            return 0

        daftar = akun_staf(db)
        diganti = 0
        for akun in daftar:
            label = label_akun(akun)
            password = tanya_password(f"{label} (Enter kosong = lewati)", baca, boleh_lewati=True)
            if password is None:
                print(f"  Dilewati: {label}")
                continue
            setel_password(db, akun, password)
            diganti += 1
            print(f"  Diganti: {label}")
        print(f"{diganti} dari {len(daftar)} akun staf diganti passwordnya.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
