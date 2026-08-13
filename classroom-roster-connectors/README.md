# Penyambung roster Classroom

Pakej setempat ini menyediakan pemetaan **3 kelas × 3 tahap** serta dua arahan sync:

- Supabase melalui REST upsert ke jadual `classroom_members`.
- Google Cloud Firestore melalui REST commit ke koleksi `classroom_members`.

Alamat akaun murid sengaja **tidak disimpan** dalam fail projek, selaras dengan `AGENTS.md`. Skrip membaca sembilan alamat daripada `.env.local` ketika dijalankan dan memprosesnya terus dalam memori.

## 1. Sediakan nilai peribadi

Dari folder ini, jalankan PowerShell:

```powershell
Copy-Item .env.example .env.local
notepad .env.local
```

Isi sembilan pemboleh ubah e-mel menggunakan senarai peribadi anda. `.env.local` telah disenaraikan dalam `.gitignore`; jangan commit atau sertakannya dalam pakej.

Semak struktur tanpa memaparkan alamat:

```powershell
npm run validate
```

Hasil yang sah ialah 9 rekod: 3 bagi setiap kelas.

## 2. Push ke Supabase

1. Buka SQL Editor Supabase dan jalankan [`supabase/schema.sql`](./supabase/schema.sql).
2. Isi `SUPABASE_URL` dan `SUPABASE_SERVICE_ROLE_KEY` dalam `.env.local`.
3. Jalankan:

```powershell
npm run sync:supabase
```

Skrip membuat upsert berdasarkan `student_email`, jadi arahan boleh dijalankan semula tanpa menghasilkan pendua. Service-role key ialah rahsia pelayan; jangan masukkan ke kod klien atau commit ke Git.

## 3. Push ke Google Cloud Firestore

Pastikan Firestore telah diwujudkan bagi projek Google Cloud dan akaun anda mempunyai kebenaran menulis. Dapatkan token akses menggunakan Google Cloud CLI, kemudian letakkannya pada sesi PowerShell semasa:

```powershell
$env:GOOGLE_OAUTH_ACCESS_TOKEN = gcloud auth application-default print-access-token
```

Isi `GCP_PROJECT_ID` dalam `.env.local`. Jika menggunakan database bernama selain `(default)`, isi `FIRESTORE_DATABASE_ID`. Kemudian jalankan:

```powershell
npm run sync:firestore
```

ID dokumen Firestore dijana daripada hash e-mel; alamat asal tidak digunakan sebagai URL dokumen. Arahan commit bersifat atomik untuk kesemua sembilan rekod.

## Struktur data

Setiap rekod menggunakan medan berikut:

| Medan | Nilai |
|---|---|
| `student_email` | Dibaca daripada environment variable |
| `class_name` | `3 Delima`, `3 Zamrud` atau `3 Berlian` |
| `achievement_level` | `advanced`, `intermediate` atau `lower_achiever` |
| `is_active` | `true` |
| `source` | `classroom_invite_confirmed_by_user` |
| `updated_at` | Masa sync dalam ISO 8601 |

## Nota keselamatan

- Skrip tidak menghantar jemputan Google Classroom dan tidak memanggil Classroom API.
- Nilai e-mel hanya dimuatkan ketika arahan dijalankan.
- Output konsol hanya menunjukkan jumlah rekod mengikut kelas, bukan alamat e-mel.
- Untuk penggunaan produksi, jalankan arahan sync dari mesin dipercayai dan putarkan token akses selepas digunakan.
