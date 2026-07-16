# Niat — Panduan Deploy ke Google Cloud (Cloud Run)

Panduan ini untuk bila anda bersedia meletakkan Niat di cloud supaya boleh
diakses dari mana-mana peranti (bukan hanya PC ini). Servis yang paling sesuai
ialah **Cloud Run** — bayar ikut guna, ada tier percuma, dan cukup untuk
aplikasi sekolah.

> Belum bersedia? Tak mengapa — setup sedia ada (auto-start pada PC ini,
> port 8050) kekal berfungsi seperti biasa. Lihat `HOSTING.md`.

## Fail-fail yang telah disediakan

| Fail | Fungsi |
|------|--------|
| `Dockerfile` | Resipi bekas (container) — Cloud Run bina imej dari sini |
| `requirements.txt` | Senarai pakej Python (server teras: tiada — stdlib sahaja) |
| `.gcloudignore` | Fail yang **TIDAK** dimuat naik semasa deploy (rahsia, PII, `private/`) |
| `.dockerignore` | Sama, untuk build Docker secara lokal |

## Langkah-langkah

### 1. Sediakan akaun & projek
1. Pergi ke [console.cloud.google.com](https://console.cloud.google.com) dan log masuk.
2. Cipta projek baharu (contoh nama: `niat-smkkps`).
3. Aktifkan billing (tier percuma Cloud Run biasanya mencukupi untuk seorang guru).

### 2. Pasang gcloud CLI (sekali sahaja)
Muat turun dari <https://cloud.google.com/sdk/docs/install>, kemudian dalam PowerShell:

```powershell
gcloud init                      # log masuk & pilih projek niat-smkkps
gcloud config set run/region asia-southeast1   # Singapura (paling hampir)
```

> Alternatif tanpa pasang apa-apa: guna **Cloud Shell** (butang terminal di
> penjuru atas Console) dan muat naik folder ini ke situ.

### 3. Simpan API key sebagai rahsia (JANGAN muat naik apikey.txt)
Server membaca `GOOGLE_API_KEY` dari environment variable dahulu sebelum
mencari `apikey.txt`, jadi di cloud kita guna **Secret Manager**:

```powershell
gcloud services enable secretmanager.googleapis.com
gcloud secrets create gemini-api-key --data-file=apikey.txt
```

*(Ini menghantar kandungan fail terus ke Secret Manager — fail itu sendiri
tetap tidak dimuat naik semasa deploy kerana disenaraikan dalam `.gcloudignore`.)*

### 4. Deploy!
Dari folder projek ini:

```powershell
gcloud run deploy niat --source . `
  --allow-unauthenticated `
  --set-secrets GOOGLE_API_KEY=gemini-api-key:latest
```

Selepas 2–3 minit anda akan dapat URL seperti
`https://niat-xxxxx-as.a.run.app` — itu alamat Niat anda, boleh dibuka dari
mana-mana peranti. Deploy semula selepas ubah kod: jalankan arahan yang sama.

## Perkara penting untuk difahami sebelum deploy

1. **SQLite (`bank_soalan.db`) tidak kekal di Cloud Run.** Storan bekas
   adalah sementara — setiap kali servis restart, data dalam fail hilang.
   Bank soalan & perpustakaan RPH perlu berada di **Supabase** dahulu
   (migrasi sudah disediakan — `migrate_to_supabase.py`). Siapkan itu dulu.
2. **Rahsia Supabase** juga perlu masuk sebagai env var/secret, bukan fail
   `supabase_config.txt`. Semak nama pembolehubah yang dibaca oleh
   `supabase_client.py` dan tetapkan dengan `--set-secrets` juga.
3. **Fallback Ollama tidak wujud di cloud** (tiada model tempatan di sana) —
   jika kuota Gemini habis, penjanaan akan gagal dan bukan bertukar ke model
   tempatan seperti di PC ini.
4. **Data sekolah** (`timetable.json`, `classrooms.json`) tidak dimuat naik
   secara lalai. Jika mahu ia ada di cloud, buka `.gcloudignore` dan buang
   tanda `#` pada dua baris `!timetable.json` / `!classrooms.json`.
5. **`--allow-unauthenticated`** bermaksud URL itu terbuka kepada sesiapa yang
   tahu alamatnya — log masuk Niat (Supabase auth) menjadi satu-satunya
   pagar. Pastikan akaun ujian/lemah dipadam sebelum kongsi URL.

## Kos anggaran
Cloud Run mengecaj hanya semasa permintaan diproses. Untuk kegunaan seorang
guru / sebuah sekolah kecil, kebiasaannya **kekal dalam tier percuma**
(2 juta permintaan/bulan). Tetapkan *budget alert* dalam Console → Billing
sebagai langkah berjaga-jaga.
