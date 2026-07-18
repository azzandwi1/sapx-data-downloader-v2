# CORESYS Batch Downloader

Dokumentasi statis: https://azzandwi1.github.io/sapx-data-downloader-v2/

> GitHub Pages hanya menampilkan dokumentasi. Backend Flask tetap diperlukan untuk login CORESYS, antrean, dan download.

Aplikasi lokal untuk membagi dan mengantrekan export dari portal CORESYS:

- Pickup > Monitoring Pickup
- Pickup Manual > Monitoring Pickup
- Laporan POD > Export Laporan POD V2
- Laporan POD > Laporan POD by AWB

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

## Catatan operasional

- Antrean lokal memakai satu worker agar permintaan tidak membanjiri portal.
- Jika portal mengakhiri sesi, login ulang lalu buat pekerjaan baru.
- POD V2 tetap tunduk pada batas antrean dan ukuran file milik server CORESYS.
- Jangan menjalankan aplikasi ini pada host publik tanpa menambahkan autentikasi lokal dan HTTPS.
