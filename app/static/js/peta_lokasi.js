/*
 * Shared map helpers (OpenStreetMap Nominatim), used by the citizen report wizard
 * (buat_laporan.html) and the inspector's "Catat Temuan Baru" form (tugas_lapangan_detail.html).
 */
(function () {
    // Reverse geocoding: coordinates -> address text, or null when unavailable (offline, no result).
    function cariAlamat(lat, lng) {
        var url = "https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=" + lat + "&lon=" + lng;
        return fetch(url, { headers: { 'Accept-Language': 'id' } })
            .then(function (res) { return res.json(); })
            .then(function (data) { return data && data.display_name ? data.display_name : null; })
            .catch(function () { return null; });
    }

    window.SCMS_PETA = { cariAlamat: cariAlamat };
})();
