SCMS-AI Dinas PUPR Kota Surabaya
================================
Sistem Triage dan Prioritisasi Laporan Kerusakan Jalan Berbasis AI - Kelompok 7 (Kelas I3).

Cara Menjalankan Proyek:
1. Buat venv: python -m venv venv
2. Aktifkan venv: venv\Scripts\activate (Windows) atau source venv/bin/activate (Mac/Linux)
3. Install library: pip install -r requirements.txt
4. Isi data awal (Seeder): python -m database.seed
5. Jalankan BDD Testing: pytest -v
6. Jalankan Server Web: uvicorn app.main:app --reload