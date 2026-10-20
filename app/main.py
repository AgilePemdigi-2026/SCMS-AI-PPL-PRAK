from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models.entities import WorkOrder, Wilayah
from app.controllers.kontrol_autentikasi import KontrolAutentikasi
from app.controllers.kontrol_pelaporan import KontrolPelaporan
from app.controllers.kontrol_verifikasi import KontrolVerifikasi
from app.controllers.kontrol_penugasan import KontrolPenugasan
from app.controllers.kontrol_dashboard import KontrolDashboard

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SCMS-AI Dinas PUPR Kota Surabaya - Sprint 1 Integrated",
    description="Sistem Triage dan Prioritisasi Laporan Kerusakan Jalan Berbasis AI",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/views/templates")

@app.get("/")
def root():
    return RedirectResponse(url="/Login")

# ================= 1. UC-K: LOGIN / AUTENTIKASI =================
@app.get("/Login", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def halaman_login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error_message": None, "entered_identifier": ""}
    )

@app.post("/Login", response_class=HTMLResponse)
@app.post("/login", response_class=HTMLResponse)
def proses_login(
    request: Request,
    identifier: str = Form(default=""),
    password: str = Form(default=""),
    db: Session = Depends(get_db)
):
    hasil = KontrolAutentikasi(db).autentikasi(identifier, password)
    if hasil["success"]:
        return RedirectResponse(url=hasil["redirect_url"], status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error_message": hasil["message"], "entered_identifier": identifier}
    )

# ================= 2. UC-A: BUAT LAPORAN WARGA (4 LANGKAH) =================
@app.get("/Beranda", response_class=HTMLResponse)
@app.get("/beranda", response_class=HTMLResponse)
@app.get("/lapor", response_class=HTMLResponse)
def halaman_buat_laporan(request: Request, db: Session = Depends(get_db)):
    daftar_wilayah = db.query(Wilayah).all()
    return templates.TemplateResponse(
        request=request,
        name="buat_laporan.html",
        context={
            "daftar_wilayah": daftar_wilayah,
            "hasil": None,
            "form_data": {
                "filename": "",
                "file_size_mb": 0.0,
                "lokasi_jalan": "Jl. Panglima Sudirman No. 45, Embong Kaliasin, Genteng, Surabaya",
                "latitude": -7.26550,
                "longitude": 112.74700,
                "deskripsi": "",
                "kategori_pilihan": "Jalan Berlubang",
                "id_wilayah": "WIL-01"
            }
        }
    )

@app.post("/lapor", response_class=HTMLResponse)
def proses_kirim_laporan(
    request: Request,
    filename: str = Form(default=""),
    file_size_mb: float = Form(default=0.0),
    lokasi_jalan: str = Form(default=""),
    latitude: float = Form(default=-7.26550),
    longitude: float = Form(default=112.74700),
    deskripsi: str = Form(default=""),
    kategori_pilihan: str = Form(default="Jalan Berlubang"),
    id_wilayah: str = Form(default="WIL-01"),
    db: Session = Depends(get_db)
):
    hasil = KontrolPelaporan(db).kirim_laporan(
        filename=filename,
        file_size_mb=file_size_mb,
        lokasi_jalan=lokasi_jalan,
        latitude=latitude,
        longitude=longitude,
        deskripsi=deskripsi,
        kategori_pilihan=kategori_pilihan,
        id_wilayah=id_wilayah
    )
    daftar_wilayah = db.query(Wilayah).all()
    return templates.TemplateResponse(
        request=request,
        name="buat_laporan.html",
        context={
            "daftar_wilayah": daftar_wilayah,
            "hasil": hasil,
            "form_data": {
                "filename": filename,
                "file_size_mb": file_size_mb,
                "lokasi_jalan": lokasi_jalan,
                "latitude": latitude,
                "longitude": longitude,
                "deskripsi": deskripsi,
                "kategori_pilihan": kategori_pilihan,
                "id_wilayah": id_wilayah
            }
        }
    )

# ================= 3. UC-H: DASHBOARD PRIORITAS & PETA GIS =================
@app.get("/Dashboard", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def halaman_dashboard_prioritas(
    request: Request,
    wilayah: str = "Semua",
    status: str = "Semua",
    kategori: str = "Semua",
    pesan_aksi: str = None,
    db: Session = Depends(get_db)
):
    controller = KontrolDashboard(db)
    if wilayah == "Semua" and status == "Semua" and kategori == "Semua":
        data_dash = controller.muat_dashboard()
    else:
        data_dash = controller.filter_dashboard(wilayah=wilayah, status=status, kategori=kategori)

    semua_wo = db.query(WorkOrder).all()
    daftar_wilayah = db.query(Wilayah).all()

    total_aduan = len(semua_wo)
    kasus_ditangani = sum(1 for w in semua_wo if w.status_work_order != "Selesai")
    kasus_selesai = sum(1 for w in semua_wo if w.status_work_order == "Selesai")
    kasus_darurat = sum(1 for w in semua_wo if w.risk_score >= 8.0)
    persentase_selesai = round((kasus_selesai / total_aduan * 100), 1) if total_aduan > 0 else 0.0

    ringkasan_wilayah = []
    for w in daftar_wilayah:
        wo_wil = [item for item in semua_wo if item.id_wilayah == w.id_wilayah]
        max_score = max([item.risk_score for item in wo_wil], default=0.0)
        ringkasan_wilayah.append({
            "nama_wilayah": w.nama_wilayah,
            "jumlah_tiket": len(wo_wil),
            "max_score": max_score
        })

    return templates.TemplateResponse(
        request=request,
        name="dashboard_prioritas.html",
        context={
            "daftar_tiket": data_dash["daftar_tiket"],
            "pesan_kosong": data_dash["message"],
            "pesan_aksi": pesan_aksi,
            "daftar_wilayah": daftar_wilayah,
            "ringkasan_wilayah": ringkasan_wilayah,
            "filter_wilayah": wilayah,
            "filter_status": status,
            "filter_kategori": kategori,
            "total_aduan": total_aduan,
            "kasus_ditangani": kasus_ditangani,
            "kasus_selesai": kasus_selesai,
            "kasus_darurat": kasus_darurat,
            "persentase_selesai": persentase_selesai
        }
    )

@app.post("/Dashboard/{ticket_id}/quick-approve", response_class=HTMLResponse)
def aksi_cepat_setujui(request: Request, ticket_id: str, db: Session = Depends(get_db)):
    wo = db.query(WorkOrder).filter_by(id_work_order=ticket_id).first()
    if wo:
        wo.status_work_order = "Disetujui"
        db.commit()
    return halaman_dashboard_prioritas(
        request=request,
        pesan_aksi=f"Tiket {ticket_id} berhasil diubah menjadi Disetujui melalui Aksi Cepat Dashboard.",
        db=db
    )

# ================= 4. UC-B: VERIFIKASI LAPORAN =================
@app.get("/verifikasi", response_class=HTMLResponse)
def halaman_verifikasi(
    request: Request,
    ticket_id: str = "REP-2026-00341",
    pesan_sukses: str = None,
    db: Session = Depends(get_db)
):
    controller = KontrolVerifikasi(db)
    semua_tiket = controller.muat_daftar_tiket()
    detail = controller.lihat_detail_tiket(ticket_id)
    if not detail and semua_tiket:
        detail = controller.lihat_detail_tiket(semua_tiket[0].id_work_order)

    return templates.TemplateResponse(
        request=request,
        name="verifikasi_detail.html",
        context={"semua_tiket": semua_tiket, "detail": detail, "pesan_sukses": pesan_sukses}
    )

@app.post("/verifikasi/{ticket_id}/approve", response_class=HTMLResponse)
def proses_setujui_tiket(request: Request, ticket_id: str, db: Session = Depends(get_db)):
    wo = KontrolVerifikasi(db).setujui_tiket(ticket_id)
    return halaman_verifikasi(request=request, ticket_id=ticket_id, pesan_sukses=f"Tiket {ticket_id} disetujui ({wo.status_work_order}).", db=db)

@app.post("/verifikasi/{ticket_id}/inspect", response_class=HTMLResponse)
def proses_tugaskan_inspeksi(request: Request, ticket_id: str, nama_penilik: str = Form(default="Budi Santoso"), db: Session = Depends(get_db)):
    wo = KontrolVerifikasi(db).tugaskan_inspeksi_tambahan(ticket_id, nama_penilik)
    return halaman_verifikasi(request=request, ticket_id=ticket_id, pesan_sukses=f"Inspeksi ditugaskan ke {nama_penilik} ({wo.status_work_order}).", db=db)

@app.post("/verifikasi/{ticket_id}/skip-inspection", response_class=HTMLResponse)
def proses_lanjutkan_tanpa_inspeksi(request: Request, ticket_id: str, db: Session = Depends(get_db)):
    wo = KontrolVerifikasi(db).lanjutkan_tanpa_inspeksi(ticket_id, "admin@dpupr.surabaya.go.id")
    return halaman_verifikasi(request=request, ticket_id=ticket_id, pesan_sukses=f"Tercatat: {wo.log_keputusan}.", db=db)

# ================= 5. UC-G: PENUGASAN PENILIK JALAN =================
@app.get("/work-orders", response_class=HTMLResponse)
def halaman_work_orders(
    request: Request,
    wilayah: str = "Semua",
    status: str = "Semua",
    select_ticket: str = None,
    pesan_sukses: str = None,
    db: Session = Depends(get_db)
):
    controller = KontrolPenugasan(db)
    daftar_wo = controller.get_semua_work_order(wilayah, status)
    daftar_wilayah = db.query(Wilayah).all()
    semua_wo = db.query(WorkOrder).all()

    info_tiket = controller.cek_sla_dan_ketersediaan_penilik(select_ticket) if select_ticket else None

    return templates.TemplateResponse(
        request=request,
        name="work_order_list.html",
        context={
            "daftar_wo": daftar_wo,
            "daftar_wilayah": daftar_wilayah,
            "filter_wilayah": wilayah,
            "filter_status": status,
            "info_tiket": info_tiket,
            "pesan_sukses": pesan_sukses,
            "total_spk": len(semua_wo),
            "jml_menunggu": sum(1 for w in semua_wo if w.status_work_order in ["Disetujui", "Menunggu Penugasan"]),
            "jml_ditugaskan": sum(1 for w in semua_wo if w.status_work_order in ["Ditugaskan", "Dalam Proses"]),
            "jml_selesai": sum(1 for w in semua_wo if w.status_work_order == "Selesai"),
        }
    )

@app.post("/work-orders/{ticket_id}/assign", response_class=HTMLResponse)
def proses_penugasan_penilik(request: Request, ticket_id: str, nama_penilik: str = Form(default=None), db: Session = Depends(get_db)):
    wo = KontrolPenugasan(db).tugaskan_penilik(ticket_id, nama_penilik)
    pesan = f"Tiket {ticket_id} berhasil diperbarui menjadi status: {wo.status_work_order}."
    return halaman_work_orders(request=request, pesan_sukses=pesan, db=db)