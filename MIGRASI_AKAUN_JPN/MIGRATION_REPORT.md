# Laporan Migrasi Apps Script PRESTIJ

Tarikh: 27 Julai 2026

## Akaun operasi

- Akaun sumber: `aimiizdihar1987@gmail.com`
- Akaun baharu: `jpn-perlis-cm16@moe-dl.edu.my`
- Identiti pelaksana yang disahkan: `jpn-perlis-cm16@moe-dl.edu.my`
- Zon masa runtime: UTC+8 (`Asia/Singapore`, setara Malaysia)

## Projek dalam akaun JPN

| Projek | Script ID |
|---|---|
| PRESTIJ Project - All at once | `1MqzWr2TjtoXqbk9SUoIqeSXeV8A-yekE1YPzT85NRVndt46O0uy4Xfci` |
| PRESTIJ Project - Lesson Plan Distribution | `1YeDIVM1ImRbTngFD0ZaRe0_0Sfo68kDs2Wr5dZeTDHzSDwLaI7F5hDvd` |
| PRESTIJ Project - Worksheet Distribution | `1kfuTttltgksu8S2SDS6lUscuIGE3bjyGfihhGeIFVIJPpxFy10q97EC6` |

## Deployment produksi

- Projek: PRESTIJ Project - All at once
- Versi: 4
- Deployment ID: `AKfycbykWGCaM96izS_KWo-lkl1YeBt7Cf_7LK35OtGKryzZHt5n3OvuRPqmWPCbofFOrqhQ`
- URL: `https://script.google.com/macros/s/AKfycbykWGCaM96izS_KWo-lkl1YeBt7Cf_7LK35OtGKryzZHt5n3OvuRPqmWPCbofFOrqhQ/exec`
- Mod pelaksana: akaun yang membuat deployment (akaun JPN)

## Pengesahan

- Runtime berjaya mengenal pasti akaun JPN.
- Tiga Classroom aktif dapat dikesan ketika ujian editor.
- Tiada installable trigger lama ditemui (`triggers: []`).
- Endpoint anonim boleh dicapai dan dilindungi dengan kunci baharu.
- Kunci salah/lama ditolak.
- Ujian baca-sahaja Classroom untuk tugasan lampau berjaya.
- Penapisan kelas diperbetulkan supaya hanya kelas yang diajar oleh akaun JPN diproses.
- Tiada e-mel peribadi, URL deployment lama, kunci lalai, atau zon masa India tertinggal dalam konfigurasi operasi.
- Deployment produksi Gmail lama (versi 5) telah dinyahaktifkan selepas endpoint JPN disahkan; kod dan versi sumber masih disimpan.

## Fail sistem yang dikemas kini

- `C:\Users\HP\Desktop\PRESTIJ KAK AIMI\reminder.py`
- `C:\Users\HP\Desktop\PRESTIJ KAK AIMI\reminder_config.txt`
- `C:\Users\HP\Desktop\PRESTIJ KAK AIMI\niat_hub.gs`
- `C:\Users\HP\Desktop\PRESTIJ FUTRE PLAN\reminder_config.txt`
- `C:\Users\HP\Desktop\PRESTIJ FUTRE PLAN\niat_hub.gs`
- `C:\Users\HP\Desktop\PRESTIJ FUTRE PLAN\niat_mail_webhook.gs`

Salinan asal sebelum perubahan disimpan di `apps-script-migration/desktop-backup/`.

## Trigger dan jadual

- Apps Script installable trigger: tiada.
- Windows Scheduled Task `Niat Agent 6`: aktif dan berstatus `Ready`.
- Jadual: setiap hari 3:30 petang waktu komputer India, bersamaan 6:00 petang Malaysia.
- Pelaksanaan pertama: 28 Julai 2026, 6:00 petang Malaysia.
- Program: `C:\Users\HP\anaconda3\python.exe`
- Skrip: `C:\Users\HP\Desktop\PRESTIJ KAK AIMI\remind_cron.py`
- Scheduled task memanggil web app JPN; e-mel peringatan dihantar oleh akaun JPN.

Kunci produksi disimpan hanya dalam kod deployment dan fail konfigurasi operasi; ia tidak direkodkan dalam laporan ini.
