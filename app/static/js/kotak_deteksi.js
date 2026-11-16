/*
 * Detection boxes shared by the report wizard (buat_laporan.html) and the ticket
 * detail pages (_macro_tiket.html foto_laporan).
 * Boxes are {kategori, confidence (%), x1, y1, x2, y2} normalised 0-1 to the photo.
 */
(function () {
    var GAYA_KOTAK = {
        "Jalan Berlubang": { warna: "#DC2626", label: "Lubang", jamak: "lubang" },
        "Retak Permukaan": { warna: "#F97316", label: "Retak", jamak: "retak" },
        "Jalan Amblas": { warna: "#7C3AED", label: "Amblas", jamak: "amblas" }
    };

    // Draw boxes on a 2D context, for a photo drawn at (ox, oy) with size dw x dh.
    function gambarKotak(g, kotak, ox, oy, dw, dh, lebarArea) {
        var ukuranHuruf = lebarArea < 260 ? 10 : 12;
        g.font = "bold " + ukuranHuruf + "px Inter, sans-serif";
        g.textBaseline = "top";
        // lowest confidence first, so the highest label ends up on top
        (kotak || []).slice().reverse().forEach(function (k) {
            var gaya = GAYA_KOTAK[k.kategori] || { warna: "#0B5ED7", label: k.kategori };
            var x1 = ox + k.x1 * dw, y1 = oy + k.y1 * dh;
            var bw = (k.x2 - k.x1) * dw, bh = (k.y2 - k.y1) * dh;
            g.lineWidth = 2;
            g.strokeStyle = gaya.warna;
            g.strokeRect(x1, y1, bw, bh);
            var teks = gaya.label + " " + Math.round(k.confidence) + "%";
            var tw = g.measureText(teks).width + 6, th = ukuranHuruf + 4;
            var ty = y1 - th >= oy ? y1 - th : y1;  // label above the box, or inside when there is no room
            var tx = Math.min(x1, ox + dw - tw);
            g.fillStyle = gaya.warna;
            g.fillRect(tx, ty, tw, th);
            g.fillStyle = "#FFFFFF";
            g.fillText(teks, tx + 3, ty + 2);
        });
    }

    // Detail pages: the <img> is shown with object-contain and the canvas only holds the boxes.
    function gambarDiAtasFoto(img, kanvas) {
        var w = kanvas.clientWidth, h = kanvas.clientHeight;
        if (!w || !h || !img.naturalWidth) return;
        var dpr = window.devicePixelRatio || 1;
        kanvas.width = Math.round(w * dpr);
        kanvas.height = Math.round(h * dpr);
        var g = kanvas.getContext("2d");
        g.setTransform(dpr, 0, 0, dpr, 0, 0);
        g.clearRect(0, 0, w, h);
        var skala = Math.min(w / img.naturalWidth, h / img.naturalHeight);
        var dw = img.naturalWidth * skala, dh = img.naturalHeight * skala;
        var kotak = [];
        try { kotak = JSON.parse(img.getAttribute("data-kotak") || "[]"); } catch (e) { kotak = []; }
        gambarKotak(g, kotak, (w - dw) / 2, (h - dh) / 2, dw, dh, w);
    }

    function pasangSemua() {
        document.querySelectorAll("figure.foto-laporan").forEach(function (fig) {
            var img = fig.querySelector("img"), kanvas = fig.querySelector("canvas.kanvas-kotak");
            if (!img) return;
            if (!kanvas) return;
            var gambar = function () { if (!fig.classList.contains("foto-gagal")) gambarDiAtasFoto(img, kanvas); };
            if (img.complete && img.naturalWidth) gambar(); else img.addEventListener("load", gambar);
            window.addEventListener("resize", gambar);
        });
    }

    window.SCMS_KOTAK = { GAYA_KOTAK: GAYA_KOTAK, gambarKotak: gambarKotak, gambarDiAtasFoto: gambarDiAtasFoto };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", pasangSemua);
    else pasangSemua();
})();
