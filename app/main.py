from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base

Base.metadata.create_all(bind=engine)
app = FastAPI(title="SCMS-AI PUPR")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def root():
    return {"status": "Base Setup Ready"}