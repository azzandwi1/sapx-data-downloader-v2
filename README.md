# CORESYS Batch Downloader

Dokumentasi statis: https://azzandwi1.github.io/sapx-data-downloader-v2/

> GitHub Pages hanya menampilkan dokumentasi. Backend Flask tetap diperlukan untuk login CORESYS, antrean, dan download.

Aplikasi lokal untuk membagi dan mengantrekan export dari portal CORESYS:

- Pickup > Monitoring Pickup
- Pickup Manual > Monitoring Pickup
- Laporan POD > Export Laporan POD V2
- Laporan POD > Laporan POD by AWB
- Trace & Tracking > Export History AWB

Batch dapat diproses paralel dengan batas satu sampai tiga proses. Preset dua proses memakai koneksi HTTP terpisah dengan sesi login yang sama, sehingga batch berikutnya dapat berjalan saat batch lain menunggu server atau sedang mengunduh.

## Menjalankan

```powershell
python -m pip install -r requirements.txt
python app.py
```

Buka `http://127.0.0.1:5177`. Masukkan akun portal pada dialog login. Kredensial tidak ditulis ke file; sesi hanya hidup di memori sampai aplikasi dihentikan atau pengguna logout.

### Instalasi Windows

Pilihan termudah adalah mengunduh `SAPX-Data-Downloader.exe` dari halaman [Releases](https://github.com/azzandwi1/sapx-data-downloader-v2/releases). Aplikasi akan membuka browser lokal secara otomatis. File hasil disimpan di:

```text
%LOCALAPPDATA%\SAPX Data Downloader\downloads
```

Pengguna yang menjalankan source code dapat klik dua kali `start-local.bat`. Skrip membuat virtual environment, memasang dependency, menjalankan backend, dan membuka browser.

File hasil disimpan di `downloads/<job-id>/`. Monitoring Pickup dan Pickup Manual diunduh langsung per batch. POD V2 membuat proses pada server laporan, memantau status, lalu mengambil file saat selesai. POD by AWB menghapus duplikat dan membagi daftar maksimal 10.000 AWB per file.

Export History AWB menyediakan tiga jenis hasil. `Milestone tujuan` menerima kolom `No. AWB` dan `TLC Tujuan`, lalu menghasilkan tanggal verifikasi, Outgoing SMU pertama, Incoming SMU pertama di TLC tujuan, dan POD pertama di TLC tujuan. `ID kurir POD pertama` hanya memerlukan kolom `No. AWB` dan mengambil teks setelah garis miring terakhir pada kolom `Lokasi / Oleh` dari aktivitas POD pertama. Sheet `Ringkasan` dan `Semua History` dapat diaktifkan sebagai output tambahan. History yang sama disimpan dalam cache memori selama lima menit.

`Verifikasi percobaan pickup` hanya memerlukan kolom `No. AWB`. Hasilnya merangkum permintaan pickup, percobaan pertama, kurir, alasan, jumlah percobaan, jumlah status belum ready, pickup berhasil, pemenuhan SLA H+1, dan status verifikasi otomatis.

Trace & Tracking mendukung 1-12 request paralel dengan nilai awal 9. Setiap request yang mengalami gangguan jaringan sementara dicoba ulang sampai tiga kali.

## Catatan operasional

- Scheduler membatasi maksimal tiga batch aktif secara global agar percepatan tetap terkontrol.
- Jika portal mengakhiri sesi, login ulang lalu buat pekerjaan baru.
- POD V2 tetap tunduk pada batas antrean dan ukuran file milik server CORESYS.
- Jangan menjalankan aplikasi ini pada host publik tanpa menambahkan autentikasi lokal dan HTTPS.
