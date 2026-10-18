from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models.entities import WorkOrder, Wilayah
from app.controllers.kontrol_penugasan import KontrolPenugasan

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SCMS-AI Dinas PUPR Kota Surabaya",
    description="Sistem Triage dan Prioritisasi Laporan Kerusakan Jalan Berbasis AI",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/views/templates")

@app.get("/")
def root():
    return {
        "status": "Normal & Beroperasi Penuh",
        "portal": "SCMS PUPR - Sistem Pengelolaan Proyek & Pemeliharaan Infrastruktur Kota Surabaya",
        "halaman_penugasan_rizaldi": "Buka http://127.0.0.1:8000/work-orders di browser"
    }

# --- ROUTE FRONTEND & BACKEND UC-G: MENUGASKAN PENILIK JALAN (RIZALDI) ---
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

    # Hitung ringkasan KPI untuk 4 kartu di atas
    semua_wo = db.query(WorkOrder).all()
    total_spk = len(semua_wo)
    jml_menunggu = sum(1 for w in semua_wo if w.status_work_order in ["Disetujui", "Menunggu Penugasan"])
    jml_ditugaskan = sum(1 for w in semua_wo if w.status_work_order in ["Ditugaskan", "Dalam Proses"])
    jml_selesai = sum(1 for w in semua_wo if w.status_work_order == "Selesai")

    info_tiket = None
    if select_ticket:
        info_tiket = controller.cek_sla_dan_ketersediaan_penilik(select_ticket)

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
            "total_spk": total_spk,
            "jml_menunggu": jml_menunggu,
            "jml_ditugaskan": jml_ditugaskan,
            "jml_selesai": jml_selesai,
        }
    )

@app.post("/work-orders/{ticket_id}/assign", response_class=HTMLResponse)
def proses_penugasan_penilik(
    request: Request,
    ticket_id: str,
    nama_penilik: str = Form(default=None),
    db: Session = Depends(get_db)
):
    controller = KontrolPenugasan(db)
    wo = controller.tugaskan_penilik(ticket_id, nama_penilik)
    
    if wo.status_work_order == "Ditugaskan":
        pesan = f"Tiket {ticket_id} berhasil ditugaskan kepada Penilik Jalan: {nama_penilik} (Status: Ditugaskan)."
    else:
        pesan = f"Tidak ada Penilik Jalan tersedia di wilayah tiket {ticket_id}. Status tiket diubah menjadi: {wo.status_work_order}."

    return halaman_work_orders(request=request, pesan_sukses=pesan, db=db)