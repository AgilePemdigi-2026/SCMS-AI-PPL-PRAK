"""Runtime settings read from the environment each time they are used (not at import),
so a test can change them with monkeypatch.setenv and the next request follows."""
import os

NILAI_AKTIF = {"1", "true", "yes", "ya"}


def mode_produksi() -> bool:
    """SCMS_PRODUKSI=1 (server mode): demo and test helpers (test credentials on the login page,
    sample-file and sample-text buttons on /lapor, the empty-filter demo on the Dashboard) are not
    rendered. Default "0": everything is shown for local development, demos and the test suite."""
    return os.getenv("SCMS_PRODUKSI", "0").strip().lower() in NILAI_AKTIF


def opsi_dokumentasi() -> dict:
    """C-02: FastAPI's /docs, /redoc and /openapi.json list every route and form field. Read once
    when the app is created: on the production server (SCMS_PRODUKSI=1) all three are switched
    off (404); locally they stay available."""
    if mode_produksi():
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
