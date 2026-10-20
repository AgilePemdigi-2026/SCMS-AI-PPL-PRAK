from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
from app.controllers.kontrol_autentikasi import KontrolAutentikasi

Base.metadata.create_all(bind=engine)
app = FastAPI(title="SCMS-AI Dinas PUPR Kota Surabaya")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def root():
    return RedirectResponse(url="/Login")

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

@app.get("/Beranda")
def beranda_warga():
    return {"halaman": "Beranda Warga (Citizen Home)"}

@app.get("/Dashboard")
def dashboard_petugas():
    return {"halaman": "Dashboard Petugas Dinas"}