from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app.models.entities import Warga, Admin, PenilikJalan

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

class KontrolAutentikasi:
    def __init__(self, db: Session):
        self.db = db

    def autentikasi(self, identifier: str, password: str):
        if not identifier:
            return {'success': False, 'message': 'Akun tidak ditemukan', 'redirect_url': '/Login'}
        identifier = identifier.strip()
        akun, peran, nama = None, None, None
        warga = self.db.query(Warga).filter((Warga.email == identifier) | (Warga.no_hp == identifier)).first()
        if warga:
            akun, peran, nama = warga, 'Warga', warga.nama_warga
        if not akun:
            admin = self.db.query(Admin).filter(Admin.email_admin == identifier).first()
            if admin:
                akun, peran, nama = admin, ('Kepala Bidang' if admin.is_kepala_bidang else 'Admin'), admin.nama_admin
        if not akun:
            penilik = self.db.query(PenilikJalan).filter(PenilikJalan.email_penilik == identifier).first()
            if penilik:
                akun, peran, nama = penilik, 'Penilik Jalan', penilik.nama_penilik
        if not akun:
            return {'success': False, 'message': 'Akun tidak ditemukan', 'redirect_url': '/Login'}
        if not akun.is_active:
            return {'success': False, 'message': 'Akun Anda tidak aktif, silakan hubungi administrator', 'redirect_url': '/Login'}
        if not pwd_context.verify(password, akun.password_hash):
            return {'success': False, 'message': 'Email/nomor HP atau password salah', 'redirect_url': '/Login'}
        redirect_url = '/Beranda' if peran == 'Warga' else '/Dashboard'
        return {'success': True, 'role': peran, 'nama': nama, 'identifier': identifier, 'redirect_url': redirect_url, 'message': 'Login berhasil'}
