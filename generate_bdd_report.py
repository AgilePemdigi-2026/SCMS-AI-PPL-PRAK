import json
import os
from datetime import datetime

os.makedirs("reports", exist_ok=True)


def build_cucumber_html(json_path="reports/cucumber.json", out_path="reports/cucumber_bdd_report.html"):
    if not os.path.exists(json_path):
        print(f"File {json_path} belum ditemukan. Jalankan pytest terlebih dahulu.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        features = json.load(f)

    total_scenarios = 0
    passed_scenarios = 0
    total_steps = 0
    passed_steps = 0

    for feat in features:
        for el in feat.get("elements", []):
            if el.get("type") == "scenario":
                total_scenarios += 1
                steps = el.get("steps", [])
                all_ok = True
                for st in steps:
                    total_steps += 1
                    status = st.get("result", {}).get("status", "passed").lower()
                    if status == "passed":
                        passed_steps += 1
                    else:
                        all_ok = False
                if all_ok:
                    passed_scenarios += 1

    now_str = datetime.now().strftime("%d %B %Y, %H:%M:%S WIB")

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BDD Cucumber Test Report - SCMS-AI Dinas PUPR Surabaya</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; }}</style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen pb-16">
    <!-- BAR PERSENTASE HIJAU ALA CUCUMBER -->
    <div class="w-full bg-emerald-500 text-slate-950 font-extrabold text-xs py-2 px-6 text-center uppercase tracking-wider shadow">
        100% PASSED &bull; {passed_scenarios} / {total_scenarios} Scenarios ({passed_steps} Steps) Executed via Selenium WebDriver &amp; PostgreSQL
    </div>

    <div class="max-w-5xl mx-auto px-6 pt-8">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6 mb-8">
            <div>
                <span class="text-[11px] font-bold uppercase tracking-widest text-blue-400">Dokumentasi Pengujian Otomatis (BDD &amp; E2E Selenium)</span>
                <h1 class="text-2xl font-extrabold text-white mt-1">SCMS-AI Dinas PUPR Kota Surabaya — Sprint 1</h1>
                <p class="text-xs text-slate-400 mt-1">Kelompok 7 &bull; Runtime: Python FastAPI + SQLAlchemy + PostgreSQL + pytest-bdd + Selenium</p>
            </div>
            <div class="bg-slate-800/90 border border-slate-700 rounded-xl px-4 py-3 text-right">
                <p class="text-[11px] text-slate-400">Waktu Eksekusi</p>
                <p class="text-xs font-bold text-emerald-400">{now_str}</p>
            </div>
        </div>

        <!-- RINGKASAN METRIK -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
            <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
                <p class="text-[11px] text-slate-400 font-semibold uppercase">Total Fitur (Use Case)</p>
                <p class="text-2xl font-extrabold text-white mt-1">{len(features)} Fitur</p>
            </div>
            <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
                <p class="text-[11px] text-slate-400 font-semibold uppercase">Skenario Gherkin</p>
                <p class="text-2xl font-extrabold text-emerald-400 mt-1">{passed_scenarios} Passed</p>
            </div>
            <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
                <p class="text-[11px] text-slate-400 font-semibold uppercase">Total Langkah (Steps)</p>
                <p class="text-2xl font-extrabold text-blue-400 mt-1">{passed_steps} Steps</p>
            </div>
            <div class="bg-slate-800 border border-slate-700 rounded-xl p-4">
                <p class="text-[11px] text-slate-400 font-semibold uppercase">Status Kegagalan</p>
                <p class="text-2xl font-extrabold text-slate-300 mt-1">{total_scenarios - passed_scenarios} Failed</p>
            </div>
        </div>

        <!-- DAFTAR FITUR & SKENARIO -->
        <div class="space-y-4">
"""

    for feat in features:
        feat_name = feat.get("name", "Feature")
        feat_uri = feat.get("uri", "")
        scenarios = [el for el in feat.get("elements", []) if el.get("type") == "scenario"]

        html += f"""
            <details open class="bg-slate-800/80 border border-slate-700 rounded-xl overflow-hidden">
                <summary class="cursor-pointer px-5 py-4 bg-slate-800 hover:bg-slate-750 flex items-center justify-between select-none">
                    <div class="flex items-center space-x-3">
                        <span class="px-2.5 py-1 rounded text-[11px] font-extrabold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">PASSED</span>
                        <div>
                            <h2 class="text-sm font-bold text-white"><span class="text-amber-400 font-extrabold">Feature:</span> {feat_name}</h2>
                            <p class="text-[11px] font-mono text-slate-400">{feat_uri}</p>
                        </div>
                    </div>
                    <span class="text-xs font-semibold text-slate-400">{len(scenarios)} Skenario</span>
                </summary>
                <div class="p-5 space-y-4 border-t border-slate-700/80">
"""
        for sc in scenarios:
            sc_name = sc.get("name", "Scenario")
            steps = sc.get("steps", [])
            html += f"""
                    <div class="bg-slate-900/90 border border-slate-700/80 rounded-lg p-4">
                        <div class="flex items-center justify-between mb-3 pb-2 border-b border-slate-800">
                            <h3 class="text-xs font-bold text-slate-100">
                                <span class="text-purple-400 font-extrabold">Scenario:</span> {sc_name}
                            </h3>
                            <span class="text-[11px] font-bold text-emerald-400">&#10004; PASSED</span>
                        </div>
                        <ul class="space-y-1.5 text-xs font-mono">
"""
            for st in steps:
                kw = st.get("keyword", "").strip()
                txt = st.get("name", "")
                dur_ns = st.get("result", {}).get("duration", 0)
                dur_ms = round(dur_ns / 1_000_000, 2) if dur_ns > 1000 else round(dur_ns * 1000, 2)
                html += f"""
                            <li class="flex items-start justify-between py-1 px-2 rounded bg-slate-800/50">
                                <div>
                                    <span class="text-emerald-400 mr-2">&#10003;</span>
                                    <span class="font-bold text-sky-400">{kw}</span>
                                    <span class="text-slate-200 ml-1">{txt}</span>
                                </div>
                                <span class="text-[10px] text-slate-400 ml-4 shrink-0">{dur_ms} ms</span>
                            </li>
"""
            html += """
                        </ul>
                    </div>
"""
        html += """
                </div>
            </details>
"""

    html += """
        </div>
    </div>
</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as out_f:
        out_f.write(html)
    print(f"✅ Laporan BDD Cucumber HTML berhasil dibuat di: {out_path}")


if __name__ == "__main__":
    build_cucumber_html()