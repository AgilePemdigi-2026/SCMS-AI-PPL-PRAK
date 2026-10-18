class AIService:
    def analisis_severity(self, nama_foto: str):
        return {
            "issue_category": "Jalan Berlubang",
            "severity_score": 8.4,
            "severity_level": "Urgent",
            "generated_description": "Lubang besar di jalur kiri, dalam +-15cm"
        }

    def cek_duplikat_nlp(self, deskripsi: str, lokasi: str):
        return {"is_duplicate": False, "existing_ticket": None}
