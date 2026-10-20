from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models.entities import Wilayah
from app.controllers.kontrol_pelaporan import KontrolPelaporan

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SCMS-AI Dinas PUPR Kota Surabaya - Modul Pelaporan Warga (UC-A)")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/views/templates")

@app.get("/")
def root():
    return RedirectResponse(url="/lapor")

@app.get("/lapor", response_class=HTMLResponse)
@app.get("/Beranda", response_class=HTMLResponse)
def halaman_buat_laporan(
    request: Request,
    db: Session = Depends(get_db)
):
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
    controller = KontrolPelaporan(db)
    hasil = controller.kirim_laporan(
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