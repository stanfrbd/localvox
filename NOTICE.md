# Attribution and third-party components

LocalVox's own code and original geometric icons are MIT licensed (see LICENSE).
The model weights are separate works and are **not** covered by that MIT license.

- **NVIDIA Parakeet TDT 0.6B v3**, by NVIDIA:
  https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- **Parakeet Ultra**, post-trained by Moondream from NVIDIA's model:
  https://huggingface.co/moondream/parakeet-ultra
- **Parakeet Ultra GGUF**, converted and quantized by Handy/transcribe.cpp:
  https://huggingface.co/handy-computer/parakeet-ultra-gguf
  The selected Q8_0 file is pinned in `localvox/catalog.json`.

All three model cards identify CC BY 4.0:
https://creativecommons.org/licenses/by/4.0/
Legal text: https://creativecommons.org/licenses/by/4.0/legalcode.en

Credit the creators and supplied attribution parties, retain supplied notices,
link to the source and license, and identify modifications when redistributing
or adapting weights. Do not imply endorsement or impose additional restrictions
on the licensed material. Preserve upstream LICENSE and NOTICE files when
redistributing the GGUF. LocalVox downloads the existing Handy Q8_0 conversion;
it does not modify or redistribute weights in its source tree or Docker image.

The model-management design takes inspiration from Handy's catalog, pinned
revisions, and integrity checks. No Handy application source was copied:
https://github.com/cjpais/Handy
https://github.com/cjpais/Handy/blob/main/src-tauri/src/managers/model.rs

Runtime dependencies retain their own licenses. In particular:

- transcribe.cpp / transcribe-cpp: MIT; native package includes third-party notices.
  https://github.com/handy-computer/transcribe.cpp
- imageio-ffmpeg: BSD-2-Clause wrapper; its bundled FFmpeg executable has separate
  licensing determined by its build, which can include GPL components.
  https://github.com/imageio/imageio-ffmpeg
  https://ffmpeg.org/legal.html
  Keep the installed package's license files and comply with the actual binary's
  license when distributing an image. LocalVox prefers system FFmpeg if present.

The optional real inference smoke test used upstream `samples/jfk.wav`, an
excerpt of President John F. Kennedy's 1961 inaugural address (US federal
public-domain speech). It is kept only in the ignored local cache, not committed.
Automated tests generate their own synthetic silence and compressed silence.
