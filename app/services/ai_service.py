"""
AI service for SCMS-AI: photo validation, damage detection (Computer Vision)
and description similarity (NLP), behind one interface.

Backends are chosen with environment variables (see README "Mode AI"):

    SCMS_CV_BACKEND   = simulasi (default) | yolov8
    SCMS_YOLO_WEIGHTS = path to road-damage YOLOv8 weights (.pt), required for yolov8
    SCMS_YOLO_CONFIG  = path to model_config.json (default: next to the weights)
    SCMS_NLP_BACKEND  = leksikal (default) | sentence-transformers
    SCMS_ST_MODEL     = sentence-transformers model name
                        (default: paraphrase-multilingual-MiniLM-L12-v2)

The default backends contain NO machine-learning model:
  * "simulasi" CV decides from the photo's FILE NAME (used for demos and the
    BDD scenarios). The UI labels it as a simulation and shows no confidence.
  * "leksikal" NLP compares descriptions by shared words.
If an ML backend is requested but its library or weights are missing, the
service logs a warning and falls back to the default, and `mode_cv` /
`mode_nlp` report what is actually running.
"""
from __future__ import annotations

import io
import logging
import math
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional, Protocol

logger = logging.getLogger("scms.ai")

KATEGORI_BERLUBANG = "Jalan Berlubang"
KATEGORI_RETAK = "Retak Permukaan"
KATEGORI_AMBLAS = "Jalan Amblas"
KATEGORI_VALID = (KATEGORI_BERLUBANG, KATEGORI_AMBLAS, KATEGORI_RETAK)

UKURAN_MAKS_MB = 10.0
EKSTENSI_VALID = ("jpg", "jpeg", "png")
FORMAT_GAMBAR_VALID = ("JPEG", "PNG")

PESAN_FORMAT_SALAH = "Format harus JPG/PNG dan ukuran maksimal 10MB"
PESAN_BUKAN_JALAN = "Objek jalan rusak tidak terdeteksi, silakan ambil ulang foto"


# --------------------------------------------------------------------------- #
# Photo validation (REQ-RPT-1)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HasilValidasiFoto:
    valid: bool
    message: str
    ukuran_mb: float = 0.0
    ekstensi: str = ""
    format_gambar: str = ""  # "JPEG" / "PNG" detected from the bytes, "" when not checked


def validasi_foto(nama_berkas: str, ukuran_mb: float, data: Optional[bytes] = None) -> HasilValidasiFoto:
    """
    Check extension and size; when the real bytes are given, also check that the
    file really is a JPEG/PNG image (a renamed PDF or text file is rejected) and
    measure the size from the bytes instead of trusting the client.
    """
    nama = (nama_berkas or "").strip()
    if not nama:
        return HasilValidasiFoto(False, PESAN_FORMAT_SALAH)
    ekstensi = nama.lower().rsplit(".", 1)[-1] if "." in nama else ""
    if data is not None:
        ukuran_mb = len(data) / (1024 * 1024)
    if ekstensi not in EKSTENSI_VALID or float(ukuran_mb or 0) > UKURAN_MAKS_MB:
        return HasilValidasiFoto(False, PESAN_FORMAT_SALAH, float(ukuran_mb or 0), ekstensi)

    format_gambar = ""
    if data is not None:
        if not data:
            return HasilValidasiFoto(False, PESAN_FORMAT_SALAH, 0.0, ekstensi)
        try:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as img:
                img.verify()
                format_gambar = img.format or ""
        except Exception:
            return HasilValidasiFoto(False, PESAN_FORMAT_SALAH, ukuran_mb, ekstensi)
        if format_gambar not in FORMAT_GAMBAR_VALID:
            return HasilValidasiFoto(False, PESAN_FORMAT_SALAH, ukuran_mb, ekstensi)

    return HasilValidasiFoto(True, "Foto valid", round(float(ukuran_mb or 0), 2), ekstensi, format_gambar)


# --------------------------------------------------------------------------- #
# Computer Vision
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HasilVisi:
    detected: bool
    message: str
    rekomendasi_kategori: Optional[str]
    severity_score: float
    confidence: Optional[float]  # 0-100, None when the backend cannot measure it
    sumber: str                  # "simulasi" | "yolov8"
    # Detection boxes for the preview (YOLO only): kategori, confidence (%),
    # x1, y1, x2, y2 normalised 0-1 to the upright (EXIF-transposed) photo.
    kotak: list[dict] = field(default_factory=list)


class BackendVisi(Protocol):
    nama: str

    def analisis(self, nama_berkas: str, data: Optional[bytes] = None) -> HasilVisi: ...


class VisiSimulasi:
    """
    Demo backend. Looks only at the file name, never at the pixels.
    Kept so the 4-step wizard and BDD scenarios work without model weights.
    """

    nama = "simulasi"
    KATA_BUKAN_JALAN = ("kucing", "selfie", "makanan", "hewan", "bunga", "mobil", "dokumen")

    def analisis(self, nama_berkas: str, data: Optional[bytes] = None) -> HasilVisi:
        nama = (nama_berkas or "").lower()
        if any(k in nama for k in self.KATA_BUKAN_JALAN):
            return HasilVisi(False, PESAN_BUKAN_JALAN, None, 0.0, None, self.nama)
        if "amblas" in nama:
            kategori, severity = KATEGORI_AMBLAS, 8.8
        elif "retak" in nama:
            kategori, severity = KATEGORI_RETAK, 5.4
        else:
            kategori, severity = KATEGORI_BERLUBANG, 8.5
        return HasilVisi(
            True,
            "Objek jalan rusak diterima (mode simulasi berdasarkan nama berkas)",
            kategori,
            severity,
            None,
            self.nama,
        )


def baca_konfigurasi_model(path: Optional[str]) -> dict:
    """
    Read the model_config.json exported by the training notebook (v4):
    conf_per_class, infer_imgsz, nms_iou, agnostic_nms, versi.
    Returns {} when the path is empty or the file does not exist.
    """
    if not path or not os.path.isfile(path):
        return {}
    import json

    with open(path, encoding="utf-8") as f:
        return json.load(f)


class VisiYolo:
    """
    YOLOv8 backend for a road-damage model (e.g. trained on RDD2022 with
    classes D00/D10/D20 cracks and D40 potholes, or custom pothole/crack/
    subsidence classes). Class names are mapped to the three SCMS categories.

    Inference settings come from the model_config.json exported next to the
    weights (or SCMS_YOLO_CONFIG): a confidence threshold per category, the
    inference image size and the NMS settings chosen on the validation set.
    Without a config file the single `conf_minimum` threshold is used.

    Severity is a heuristic to calibrate with field data: a base value per
    category plus up to +2.5 for how much of the photo the damage covers,
    weighted by detection confidence.
    """

    nama = "yolov8"
    BASE_SEVERITY = {KATEGORI_BERLUBANG: 7.0, KATEGORI_AMBLAS: 7.5, KATEGORI_RETAK: 4.5}
    MAKS_KOTAK = 20

    def __init__(
        self,
        weights: Optional[str] = None,
        model=None,
        conf_minimum: float = 0.35,
        config: Optional[dict] = None,
        config_path: Optional[str] = None,
    ):
        if model is None:
            from ultralytics import YOLO  # optional dependency, see requirements-ai.txt

            if not weights or not os.path.exists(weights):
                raise FileNotFoundError(f"YOLO weights not found: {weights!r}")
            model = YOLO(weights)
            if config is None and config_path is None:
                # default: model_config.json in the same folder as the weights
                config_path = os.path.join(os.path.dirname(os.path.abspath(weights)), "model_config.json")
        if config is None:
            config = baca_konfigurasi_model(config_path)
        self.model = model
        self.versi = config.get("versi")

        # Per-category thresholds, keyed by SCMS category (the config uses model class names)
        self.conf_per_kategori: dict[str, float] = {}
        for nama_kelas, nilai in (config.get("conf_per_class") or {}).items():
            kategori = self.petakan_kelas(nama_kelas)
            if kategori is not None:
                self.conf_per_kategori[kategori] = float(nilai)
        self.conf_minimum = min(self.conf_per_kategori.values()) if self.conf_per_kategori else conf_minimum

        # Extra predict() arguments, only those set in the config
        self.opsi_prediksi: dict = {}
        if config.get("infer_imgsz"):
            self.opsi_prediksi["imgsz"] = int(config["infer_imgsz"])
        if config.get("nms_iou") is not None:
            self.opsi_prediksi["iou"] = float(config["nms_iou"])
        if config.get("agnostic_nms") is not None:
            self.opsi_prediksi["agnostic_nms"] = bool(config["agnostic_nms"])
        if config:
            logger.info("YOLOv8 %s: conf=%s, opsi=%s", self.versi or "", self.conf_per_kategori, self.opsi_prediksi)

    def ambang(self, kategori: str) -> float:
        return self.conf_per_kategori.get(kategori, self.conf_minimum)

    @staticmethod
    def petakan_kelas(nama_kelas: str) -> Optional[str]:
        n = (nama_kelas or "").strip().lower()
        if n in ("d40",) or "pothole" in n or "lubang" in n:
            return KATEGORI_BERLUBANG
        if n in ("d00", "d10", "d20") or "crack" in n or "retak" in n:
            return KATEGORI_RETAK
        if "subsid" in n or "sink" in n or "depress" in n or "amblas" in n:
            return KATEGORI_AMBLAS
        return None

    def analisis(self, nama_berkas: str, data: Optional[bytes] = None) -> HasilVisi:
        if not data:
            return HasilVisi(False, "Foto wajib diunggah untuk dianalisis", None, 0.0, None, self.nama)
        from PIL import Image, ImageOps

        # Phone photos are often stored sideways with an EXIF orientation tag;
        # rotate them upright first, as the training images were.
        gambar = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        hasil = self.model.predict(gambar, conf=self.conf_minimum, verbose=False, **self.opsi_prediksi)[0]
        nama_kelas = hasil.names

        terbaik = None  # (skor, kategori, conf)
        luas_per_kategori: dict[str, float] = {}
        kotak: list[dict] = []
        for cls_id, conf, xywhn in zip(hasil.boxes.cls.tolist(), hasil.boxes.conf.tolist(), hasil.boxes.xywhn.tolist()):
            kategori = self.petakan_kelas(nama_kelas[int(cls_id)])
            if kategori is None or conf < self.ambang(kategori):
                continue
            kotak.append(self._kotak(kategori, float(conf), xywhn))
            luas = float(xywhn[2]) * float(xywhn[3])
            luas_per_kategori[kategori] = luas_per_kategori.get(kategori, 0.0) + luas
            skor = conf * (0.5 + luas)
            if terbaik is None or skor > terbaik[0]:
                terbaik = (skor, kategori, float(conf))

        if terbaik is None:
            return HasilVisi(False, PESAN_BUKAN_JALAN, None, 0.0, None, self.nama)

        _, kategori, conf = terbaik
        cakupan = min(1.0, luas_per_kategori[kategori] * 5)
        severity = round(min(10.0, self.BASE_SEVERITY[kategori] + 2.5 * cakupan * conf), 1)
        return HasilVisi(
            True,
            f"Objek jalan rusak terdeteksi oleh YOLOv8 ({conf * 100:.1f}%)",
            kategori,
            severity,
            round(conf * 100, 1),
            self.nama,
            sorted(kotak, key=lambda k: k["confidence"], reverse=True)[: self.MAKS_KOTAK],
        )

    @staticmethod
    def _kotak(kategori: str, conf: float, xywhn) -> dict:
        """One box for the preview; xywhn is normalised to the image passed to predict()."""
        cx, cy, w, h = (float(v) for v in xywhn)

        def klip(v: float) -> float:
            return round(min(1.0, max(0.0, v)), 4)

        return {
            "kategori": kategori,
            "confidence": round(conf * 100, 1),
            "x1": klip(cx - w / 2),
            "y1": klip(cy - h / 2),
            "x2": klip(cx + w / 2),
            "y2": klip(cy + h / 2),
        }


# --------------------------------------------------------------------------- #
# NLP similarity
# --------------------------------------------------------------------------- #
class BackendKemiripan(Protocol):
    nama: str
    ambang_duplikat: float

    def kemiripan(self, teks1: str, teks2: str) -> float: ...


_STOPWORDS = {
    "ada", "di", "ke", "dari", "yang", "dan", "atau", "dengan", "untuk", "pada", "ini", "itu",
    "sangat", "cukup", "agak", "sekali", "sudah", "belum", "akan", "juga", "karena", "saat",
    "dekat", "depan", "belakang", "samping", "sebelah", "tengah", "sekitar", "arah",
    "jalan", "jl", "jln", "raya", "no", "nomor", "gang", "gg", "kota", "surabaya",
    "the", "a", "an", "of", "in", "on", "near",
}


def _token(teks: str) -> set[str]:
    kata = re.findall(r"[a-z0-9]+", (teks or "").lower())
    return {k for k in kata if k not in _STOPWORDS and len(k) > 1}


class KemiripanLeksikal:
    """Cosine similarity over word sets, Indonesian stopwords removed. No model."""

    nama = "leksikal"
    ambang_duplikat = 0.35

    def kemiripan(self, teks1: str, teks2: str) -> float:
        a, b = _token(teks1), _token(teks2)
        if not a or not b:
            return 0.0
        return len(a & b) / math.sqrt(len(a) * len(b))


class KemiripanSentenceTransformer:
    """Semantic similarity with a multilingual sentence-transformers model."""

    nama = "sentence-transformers"
    ambang_duplikat = 0.60

    def __init__(self, nama_model: str = "paraphrase-multilingual-MiniLM-L12-v2", encoder=None):
        if encoder is None:
            from sentence_transformers import SentenceTransformer  # optional dependency

            encoder = SentenceTransformer(nama_model)
        self.encoder = encoder

    def kemiripan(self, teks1: str, teks2: str) -> float:
        if not (teks1 or "").strip() or not (teks2 or "").strip():
            return 0.0
        v1, v2 = self.encoder.encode([teks1, teks2])
        v1, v2 = list(map(float, v1)), list(map(float, v2))
        norma = math.sqrt(sum(x * x for x in v1)) * math.sqrt(sum(x * x for x in v2))
        return 0.0 if norma == 0 else sum(x * y for x, y in zip(v1, v2)) / norma


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #
class AIService:
    def __init__(self, visi: Optional[BackendVisi] = None, kemiripan: Optional[BackendKemiripan] = None):
        self.visi = visi or VisiSimulasi()
        self.nlp = kemiripan or KemiripanLeksikal()

    @property
    def mode_cv(self) -> str:
        return self.visi.nama

    @property
    def mode_nlp(self) -> str:
        return self.nlp.nama

    @property
    def is_simulasi(self) -> bool:
        return self.visi.nama == "simulasi"

    def validasi_foto(self, nama_berkas: str, ukuran_mb: float, data: Optional[bytes] = None) -> HasilValidasiFoto:
        return validasi_foto(nama_berkas, ukuran_mb, data)

    def analisis_foto(self, nama_berkas: str, data: Optional[bytes] = None) -> HasilVisi:
        return self.visi.analisis(nama_berkas, data)

    def kemiripan_deskripsi(self, teks1: str, teks2: str) -> float:
        return self.nlp.kemiripan(teks1, teks2)

    @property
    def ambang_duplikat(self) -> float:
        return self.nlp.ambang_duplikat


@lru_cache(maxsize=1)
def get_ai_service() -> AIService:
    visi: BackendVisi = VisiSimulasi()
    if os.getenv("SCMS_CV_BACKEND", "simulasi").strip().lower() == "yolov8":
        try:
            visi = VisiYolo(weights=os.getenv("SCMS_YOLO_WEIGHTS"), config_path=os.getenv("SCMS_YOLO_CONFIG") or None)
        except Exception as e:  # missing library or weights
            logger.warning("YOLOv8 backend unavailable (%s); using simulation backend", e)

    nlp: BackendKemiripan = KemiripanLeksikal()
    if os.getenv("SCMS_NLP_BACKEND", "leksikal").strip().lower() == "sentence-transformers":
        try:
            nlp = KemiripanSentenceTransformer(os.getenv("SCMS_ST_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"))
        except Exception as e:
            logger.warning("sentence-transformers backend unavailable (%s); using lexical backend", e)

    return AIService(visi, nlp)
