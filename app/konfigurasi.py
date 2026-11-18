"""Runtime settings read from the environment each time they are used (not at import),
so a test can change them with monkeypatch.setenv and the next request follows."""
import os

NILAI_AKTIF = {"1", "true", "yes", "ya"}


def mode_produksi() -> bool:
    """SCMS_PRODUKSI=1 (server mode): demo and test helpers (test credentials on the login page,
    sample-file and sample-text buttons on /lapor, the empty-filter demo on the Dashboard) are not
    rendered. Default "0": everything is shown for local development, demos and the test suite."""
    return os.getenv("SCMS_PRODUKSI", "0").strip().lower() in NILAI_AKTIF
