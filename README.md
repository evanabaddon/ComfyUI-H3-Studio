# ComfyUI-H3-Studio
**Interactive Video + Audio Timeline Extender, Multi-Character Reference Hub (On/Off), Fast Attention + Unlimited Dynamic LoRA Stack, & AI Prompt Composer (`https://ollama.smixapp.com/` + `<d>` Dialogue Rules) untuk MiniMax-H3**

Ekstensi custom node **ComfyUI** yang dirancang khusus untuk mempermudah pembuatan dan perpanjangan (*extend*) video + stereo audio pada model **MiniMax-H3** (`FL2VA` maupun `Ref2VA`).

---

## Fitur Utama

### 1. `H3 Interactive Video & Audio Extender (Timeline)`
Editor timeline interaktif yang berjalan langsung di dalam node canvas ComfyUI:
- **In-Node Frame Scrubber & Player**: Geser *playhead* (`-1f`, `+1f`, `Play/Pause`, `End`) untuk melihat setiap frame hasil generasi.
- **Trim & Lock First-Frame Reference (`<Picture 1>`)**: Cari frame terbaik tepat sebelum gerakan/wajah di akhir klip rusak, lalu klik **`Lock Playhead as First-Frame Ref & Trim Out`**. Frame tersebut otomatis dikunci ke output `reference_frame` untuk diumpankan ke `first_frame` (`MiniMaxH3ImageToVideo`) atau `ref_image_0` (`MiniMaxH3ReferenceToVideo`) pada generasi berikutnya.
- **Audio + Video Sync Trimming & Seamless Stitching**: Karena MiniMax-H3 menghasilkan **Video (`24 FPS`) dan Stereo Audio (`32 kHz`)** secara bersamaan, saat Anda memotong frame video, track audio juga otomatis dipotong pada milidetik yang sama dan disambung (*stitched*) dengan *audio crossfade* halus (tanpa bunyi *pop/click*).
- **Auto-Skip First Frame**: Otomatis membuang frame ke-0 pada segmen ke-2 dst. agar tidak terjadi *duplicate frame* (*stutter*) di titik sambungan.
- **1-Click Complete Workflow Loader**: Tombol **`Auto-Wire H3 I2VA Workflow`** dan **`Auto-Wire H3 Ref2VA Studio`** langsung di dalam node untuk merakit seluruh pipeline MiniMax-H3 di canvas ComfyUI.

### 2. `H3 Model Speed & Unlimited LoRA Hub`
Mengakselerasi model **MiniMax-H3 33B** dan mengelola LoRA tanpa batas:
- **Fast Attention Backend**: Mendukung `sage_attention` (SageAttention), `flash_attention_2` (FlashAttention-2), `xformers`, dan `pytorch_sdpa`, lengkap dengan *Fast TF32/FP16/BF16 Matrix Multiplication*, *AdaLN Modulation Caching*, dan opsi `torch.compile`.
- **Unlimited Dynamic LoRA Stack (`+ Add LoRA`)**:
  - Tambahkan berapa pun LoRA (misal: *H3 Turbo 4-step/8-step LoRA* + *Character LoRA* + *Style LoRA*) langsung dari tombol **`+ Add LoRA`** di dalam node.
  - Setiap baris LoRA memiliki switch **On/Off** sendiri serta pengatur `Model Str` & `CLIP Str`.
  - Otomatis mendeteksi LoRA Turbo (`4step` / `8step`) dan mengeluarkan output `recommended_steps` (`4`, `8`, atau `20`) ke `BasicScheduler`.

### 3. `H3 Character & Multi-Reference Hub (On/Off)`
Mengelola referensi wajah/karakter (`<Subject N>`), environment (`<Picture N>`), dan timbre suara (`<Audio N>`):
- **Master Switch & Per-Character On/Off Toggle**: Aktifkan atau matikan referensi karakter kapan saja langsung dari UI node tanpa perlu mencabut kabel (*wire*) di ComfyUI.
- **Auto Re-Indexing (`<Subject N>`, `<Picture N>`, `<Audio N>`)**: Hanya karakter yang berstatus **ON** yang diurutkan menjadi `<Subject 1>`, `<Subject 2>`, dst., sehingga label di prompt selalu sinkron 100% dengan urutan `ref_image_0..4` dan `ref_audio_0..2` pada node `MiniMaxH3ReferenceToVideo`.
- **Hybrid Video Extend + Character Reference**: Jika input `first_frame_from_extender` dihubungkan, frame terakhir video otomatis menjadi `<Picture 1>` (First Frame of `[Shot 1]`) dan foto wajah karakter otomatis bergeser menjadi `<Picture 2>`, `<Picture 3>`, dst.

### 4. `H3 AI Prompt Composer (Ollama smixapp.com + <d>)`
Mengubah ide cerita singkat (bahasa Indonesia/Inggris) menjadi struktur prompt **MiniMax-H3** yang 100% patuh pada dokumentasi resmi (`SKILL.md`, `base-en.txt`, dan `ref-en.txt`):
- **Terintegrasi dengan `https://ollama.smixapp.com/`**:
  - Otomatis mengambil daftar model aktif dari `/api/tags` (mendukung model Vision & Thinking seperti `minimax-m3:cloud`, `qwen3.6:27b`, `huihui_ai/Qwen3.8-abliterated:latest`, `gemma3`, dll.).
  - Jika `send_vision_images` aktif, node otomatis mengirim *thumbnail* `first_frame` dan foto karakter ke LLM agar pakaian, komposisi, dan pencahayaan dideskripsikan secara akurat.
- **Interactive Dialogue (`<d>`) Builder**:
  - Klik **`+ Add <d> Line`** di dalam node untuk menambahkan baris dialog dengan Speaker ID `(S1)`, `(S2)`, pilihan bahasa (`[Indonesian]`, `[English]`, `[Japanese]`, dll.), nada bicara, serta toggle **VO (Off-Screen Voiceover)**.
  - Otomatis memformat dialog ke dalam tag wajib `<d>[Language] ...</d>`, menjaga teks asli *verbatim* tanpa diterjemahkan, menstandarkan tanda baca, dan menambahkan instruksi penutupan bibir (*lip closure*) sesuai aturan H3.
- **Kalkulator Frame Resmi H3 (`17k + 5` @ 24fps)**:
  - Otomatis menghitung jumlah frame valid H3 (`frame_length_17k5`) dan durasi efektif (`S.SS` detik) untuk dicolokkan langsung ke input `length` pada `MiniMaxH3ImageToVideo` / `MiniMaxH3ReferenceToVideo`.

---

## Cara Instalasi & Integrasi ke ComfyUI

### Langkah 1: Pasang Ekstensi ke Folder `custom_nodes` ComfyUI
Anda bisa menyalin atau membuat *symlink* folder `/Users/user/Downloads/h3` ini ke dalam direktori `ComfyUI/custom_nodes/ComfyUI-H3-Studio`:

#### Opsi A — Menggunakan Symlink (Direkomendasikan saat development agar perubahan kode langsung aktif)
```bash
ln -s /Users/user/Downloads/h3 /path/ke/ComfyUI/custom_nodes/ComfyUI-H3-Studio
```

#### Opsi B — Copy / Clone langsung ke `custom_nodes`
```bash
cp -r /Users/user/Downloads/h3 /path/ke/ComfyUI/custom_nodes/ComfyUI-H3-Studio
```

### Langkah 2: Install Dependensi Opsional (Fast Attention)
Ekstensi ini hanya membutuhkan `numpy` dan `Pillow` (yang sudah terpasang bawaan di ComfyUI). Jika Anda ingin mengaktifkan **SageAttention** untuk mempercepat generasi model 33B H3:
```bash
# Masuk ke python environment ComfyUI Anda, lalu jalankan:
pip install sageattention
```

### Langkah 3: Pastikan File Model MiniMax-H3 Sudah Ada di Folder `ComfyUI/models/`
Sesuai arsitektur resmi MiniMax-H3 di ComfyUI ([HuggingFace Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)), pastikan model disimpan di struktur berikut:
```text
ComfyUI/models/
├── diffusion_models/
│   ├── minimax_h3_fl2va_pruned_int8_convrot.safetensors      # Untuk mode T2VA / I2VA / FL2VA
│   └── minimax_h3_ref2va_pruned_int8_convrot.safetensors     # Untuk mode Ref2VA (Multi-Karakter)
├── text_encoders/
│   └── qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors          # Text/Vision Encoder H3 (wajib type: minimax)
├── vae/
│   ├── minimax_h3_video_vae_int8_convrot.safetensors         # Video VAE
│   └── minimax_h3_audio_vae_fp32.safetensors                 # Stereo Audio VAE (32kHz)
├── loras/
│   ├── minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors
│   ├── minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors
│   └── minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors
└── embeddings/ (Opsional)
    └── minimaxh3_*.safetensors
```

### Langkah 4: Restart ComfyUI & Muat Workflow
1. Jalankan ulang server **ComfyUI** dan refresh browser Anda (`Cmd+R` / `Ctrl+F5`).
2. Anda dapat memuat workflow lengkap dengan **2 cara mudah**:
   - **Cara 1 (Drag & Drop JSON)**: Tarik file dari folder [`example_workflows/`](./example_workflows/) langsung ke kanvas ComfyUI:
     - [`example_workflows/H3_I2VA_Interactive_Extender.json`](./example_workflows/H3_I2VA_Interactive_Extender.json) — Workflow I2VA + Interactive Video & Audio Extender.
     - [`example_workflows/H3_Ref2VA_MultiCharacter_Studio.json`](./example_workflows/H3_Ref2VA_MultiCharacter_Studio.json) — Workflow Ref2VA Multi-Karakter On/Off + Interactive Extender.
   - **Cara 2 (1-Click Button di dalam Node)**:
     - Klik kanan di kanvas ComfyUI -> **Add Node** -> **MiniMax-H3 Studio** -> **Timeline & Extender** -> **`H3 Interactive Video & Audio Extender (Timeline)`**.
     - Di bagian bawah node tersebut, klik tombol **`Auto-Wire H3 I2VA Workflow`** atau **`Auto-Wire H3 Ref2VA Studio`**. Seluruh node akan otomatis dirakit!

---

## Panduan Alur Kerja Extend Video (Step-by-Step)

1. **Generate Segmen Pertama (Segmen 1)**:
   - Ketik ide cerita di **`H3 AI Prompt Composer`**, tambahkan baris dialog `<d>` jika ada karakter yang berbicara.
   - Klik **`Generate H3 Prompt Now (via ollama.smixapp.com)`** untuk melihat hasil prompt H3 (atau biarkan otomatis saat menekan **Queue Prompt**).
   - Klik **Queue Prompt**. Setelah selesai, Segmen 1 (Video + Audio) akan masuk ke **`H3 Interactive Video & Audio Extender`**.
2. **Pilih Frame Terbaik untuk Extend (Scrub & Lock)**:
   - Di dalam node **`H3 Interactive Video & Audio Extender`**, geser *scrubber* (atau gunakan tombol `-1f` / `+1f`) ke bagian akhir video tempat gerakan dan wajah masih bagus (misal: Frame 115 dari 124).
   - Klik tombol oranye **`Lock Playhead as First-Frame Ref & Trim Out`**.
   - Sisa frame setelah Frame 115 (beserta audionya) otomatis dipotong, dan Frame 115 dikunci sebagai `reference_frame` (`<Picture 1>`).
3. **Generate Segmen Kedua (Extend Segmen 2)**:
   - Ubah cerita/dialog di **`H3 AI Prompt Composer`** untuk adegan lanjutan.
   - Klik **Queue Prompt**. Segmen 2 otomatis dibuat mulai dari Frame 115 tadi, lalu otomatis ditambahkan (*append*) ke timeline tanpa duplikasi frame sambungan!
4. **Re-Roll atau Simpan Video Utuh**:
   - Jika hasil Segmen 2 kurang bagus, cukup klik **`Undo Seg`** di dalam node Extender lalu **Queue Prompt** lagi.
   - Output `stitched_images` dan `stitched_audio` dari node Extender selalu berisi gabungan utuh dari seluruh segmen (Segmen 1 + Segmen 2 + ... + Segmen N) yang langsung disimpan menjadi MP4 oleh node `CreateVideo` -> `SaveVideo`.
