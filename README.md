# LocalVox

A small, self-hosted web app for turning audio files into text on your server CPU.
Upload several recordings from a phone, export the results, and delete the audio
after processing. No cloud transcription, accounts, database, or permanent history.

**Default model: Parakeet Ultra Q8_0**, as requested: Moondream's post-trained
NVIDIA Parakeet TDT 0.6B v3, converted to GGUF by Handy. This is a distinct
checkpoint from the original NVIDIA v3. It supports 25 European languages,
including French; language selection is automatic. Accuracy depends on the
recording. Upstream benchmark improvements are not a guarantee for your audio.

The browser transfers files to the server. Inference is local **to the server**,
not to the Android phone. Internet access is needed to install dependencies and
provision weights; inference does not call a cloud API.

## Quick start: Linux, without Docker

Tested here on Linux x86-64 using Python 3.11.15, managed by `uv`.
System `python3` is 3.12.3; bare `python` is unavailable. The project declares
Python 3.11–3.13, but only 3.11 was exercised. Use Python 3.11 for reproduction.
Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.

```bash
uv venv --python 3.11
uv pip install --require-hashes -r requirements.lock
uv pip install --no-deps .
cp .env.example .env
chmod 600 .env
```

Generate a token, then put it in `.env` as `LOCALVOX_TOKEN`:

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

The placeholder is deliberately rejected. Keep `.env` private; it is Git-ignored.
Load your administrator-controlled configuration and provision the model:

```bash
set -a
. ./.env
set +a
.venv/bin/localvox download-model
.venv/bin/localvox serve
```

Open `http://SERVER_LAN_IP:8000`, sign in using the token, select files, and
click **Transcribe files**. The process binds **0.0.0.0**, with configurable port;
`0.0.0.0` is a listening address, not the address to enter on the phone.
Stop with Ctrl+C. There is no reverse proxy or domain requirement for LAN use.

**HTTP sends credentials and audio without encryption.** Use it only on a trusted
LAN with that risk understood. For remote use, use HTTPS through a reverse proxy
or a properly configured VPN. Do not expose plain HTTP directly to the Internet.
The token does not replace TLS. A VPN protects transport but does not by itself
make an HTTP LAN URL a browser secure context for PWA features.

## Model handling and CPU runtime

Model management follows Handy's approach: a small catalog, pinned Hugging Face
revision, expected file size and SHA-256, explicit provisioning, atomic rename,
and persistent reuse. `download-model` serializes downloaders, verifies the
existing cache, and deletes partial files on handled failures. It does not resume
an interrupted download. A hard-killed downloader may leave a `.part` file;
remove it while no downloader is running.

The catalog is in `localvox/catalog.json`. The Q8_0 file is **740,363,168 bytes**.
Default model directory: `.cache/models`; set `LOCALVOX_MODEL_DIR` for another
persistent location. This is a direct file cache, not the Hugging Face SDK cache:
`HF_HOME` is not used. Reserve at least 2 GB disk for weights and download headroom,
plus dependencies and temporary uploads. A dedicated download command is used
instead of downloading during a Docker build or unexpectedly during an upload.

On the first transcription, the server verifies SHA-256 and starts one persistent
worker. `transcribe-cpp==0.4.1` loads the model once with `backend="cpu"` and
reuses a session. Native computation is serialized across all requests because
the upstream engine restricts concurrent computation on a model. CPU threads
(default 2) are configurable; inference concurrency is deliberately fixed at one.
The isolated worker can be terminated on timeout and recreated on a later file.

| Route considered | CPU and dependencies | Assessment for this prototype |
| --- | --- | --- |
| NVIDIA NeMo | Established reference for original v3; PyTorch and a broad speech dependency stack, generally multi-GB environment | Strong reference, optimized mainly for NVIDIA GPUs; not the simplest Ultra deployment |
| ONNX Runtime / onnx-asr | Established community v3 CPU conversion; lighter than NeMo, no PyTorch required | Reasonable for original v3; its published v3 conversion is not automatically Ultra or its VAD behavior |
| Moondream Photon | Ultra model card's reference execution path; published performance uses NVIDIA GPU | Not selected for this CPU-first prototype |
| Handy transcribe.cpp / GGUF | CPU supported; prebuilt native Python wheel installed here without compiling, no PyTorch | Selected: explicitly supports Ultra including its long-audio segmentation, pinned Q8_0 file; young pre-1.0 runtime/API |

Start with **4 GB RAM and 2 CPU cores**, then measure your own recordings. This is
an operational starting point, not a measured minimum. Docker limits default to
4 GB and 2 CPUs; resource-limited deployment and long recordings are unverified.
Do not extrapolate NVIDIA GPU long-audio capacity claims to a small CPU server.
A single short English sample passed here; French accuracy was not evaluated.

Official/upstream sources consulted on 2026-11-09:

- [NVIDIA v3 model card and supported languages](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- [Moondream Ultra model card](https://huggingface.co/moondream/parakeet-ultra)
- [Handy model catalog](https://github.com/cjpais/Handy/blob/main/src-tauri/src/catalog/catalog.json)
- [Handy model-management implementation](https://github.com/cjpais/Handy/blob/main/src-tauri/src/managers/model.rs)
- [transcribe.cpp Ultra documentation](https://github.com/handy-computer/transcribe.cpp/blob/main/docs/models/parakeet-ultra.md)
- [transcribe.cpp Python bindings](https://github.com/handy-computer/transcribe.cpp/blob/main/bindings/python/README.md)
- [onnx-asr and CPU installation](https://github.com/istupakov/onnx-asr)
- [Community original-v3 ONNX conversion](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx)

## Docker Compose

Docker is not installed in the development environment; these files are provided
but the image build and Compose lifecycle remain to be validated on a Docker host.
Linux x86-64 is the intended initial target. Other architectures may require
native compilation and are not validated.

Create `.env` and replace the token as above, then:

```bash
docker compose build
docker compose run --rm --no-deps localvox localvox download-model
docker compose up -d
docker compose logs -f localvox
curl --fail http://127.0.0.1:8000/health
docker compose down
```

The named `models` volume persists weights across container replacement. `down`
retains it; `down -v` deletes it. No model is downloaded during image construction.
The service runs as UID 10001, uses a read-only root filesystem, and writes audio
to a 600 MB `/tmp` tmpfs. Adjust this capacity if you raise upload limits.
Compose maps `${LOCALVOX_PORT:-8000}` on the host to container port 8000. The
container always listens on 0.0.0.0:8000. Binding a host port makes it reachable on
host interfaces subject to firewall rules: restrict it to your LAN/VPN.

The Docker healthcheck only checks HTTP liveness. It does not load or download
the model. `/api/model`, available after sign-in, reports the backend, configured
limits, and presence/size of the downloaded file. Integrity is checked on load.

## Configuration

The CLI reads environment variables. It does not load `.env` itself; source it
as shown above. Compose reads `.env` through `env_file`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `LOCALVOX_TOKEN` | required | Random administrator secret, at least 24 characters |
| `LOCALVOX_BACKEND` | `parakeet` | `parakeet` or explicitly simulated `mock` |
| `LOCALVOX_PORT` | `8000` | Listening port; host port with Compose |
| `LOCALVOX_MODEL_DIR` | `.cache/models` | Persistent model directory; Compose uses `/data/models` |
| `LOCALVOX_TEMP_DIR` | `.cache/tmp` | Dedicated temporary root; Compose uses `/tmp/localvox` |
| `LOCALVOX_CPU_THREADS` | `2` | Threads in the native inference session |
| `LOCALVOX_MAX_FILES` | `8` | Maximum multipart files per API request |
| `LOCALVOX_MAX_FILE_MB` | `25` | Per-file limit in MiB |
| `LOCALVOX_MAX_SECONDS` | `300` | Decoded audio duration limit |
| `LOCALVOX_MAX_PENDING` | `2` | Maximum active + queued transcription requests |
| `LOCALVOX_QUEUE_TIMEOUT` | `30` | Seconds to wait for the processing slot |
| `LOCALVOX_UPLOAD_TIMEOUT` | `120` | Seconds to receive the complete HTTP body |
| `LOCALVOX_TASK_TIMEOUT` | `180` | Separate limits for decoding, model startup, and each inference |
| `LOCALVOX_SECURE_COOKIE` | `false` | Set `true` when served over HTTPS |

All numeric limits must be positive. Whole-request upload bytes are bounded at
`MAX_FILES × MAX_FILE_MB × 1048576 + 65536` even without Content-Length. This limit
includes multipart overhead. Overlarge whole requests are rejected before
transcription. Within an accepted request, individual errors do not discard other
file results. Decoding stops at the duration limit plus one second, then checks
the actual number of decoded 16 kHz mono samples. Input MIME types are ignored;
extensions are allowlisted and FFmpeg must successfully decode an allowed
container format. Playlist demuxers and network protocols are disabled.

Only one server process may use a temporary root (an exclusive filesystem lock
prevents accidental multi-worker deployment). Never launch several Uvicorn workers.
The default two pending requests mean one active batch and one waiting request;
additional requests receive 503. Waiting requests do not yet consume upload spool
space. Authentication happens before the request body is read. HTTP bodies and
multipart spools are bounded, but memory/disk limits are still deployment concerns.

## Web use and batch behavior

Select or drop multiple files; each has a waiting, processing, done, or error
state. The interface submits one file per request sequentially, releasing browser
file references after each finishes. This gives live per-file progress without
WebSockets or a background job database. More files can be added while working.
A failed file does not block later files. Copy each transcript, copy everything,
or download text/JSON. Clipboard writes can require HTTPS; downloads are the
fallback. Results and errors are inserted as text, never interpreted as HTML.

The batch API accepts multiple parts in a single synchronous request and processes
them sequentially. Its response is returned when the batch finishes. There are
no job IDs, polling endpoints, or persistent tasks. Restarting loses pending work.
A disconnected client may leave the active bounded batch running until completion
or timeout; there is no cancellation endpoint. Retry can duplicate computation.

Temporary files use generated names inside a private run directory. Original names
are display metadata only. Audio and decoded PCM are removed per file, including
on handled decoding/inference errors; spools close when the request ends. Shutdown
stops the model worker and cleans the run directory. SIGKILL/power loss cannot run
cleanup: stale run directories are removed at the next exclusive server startup.
Host-side temporary files are not securely erased; filesystem snapshots, backups,
swap, and administrator access are outside this prototype's guarantees.

## API

Public endpoints: `GET /health`, `GET /login`, `POST /login`, manifest, icons, and
service worker. They contain no token, transcripts, or model filesystem paths.
All other routes require `Authorization: Bearer …` or a signed browser session.
`GET /health` always returns `200 {"status":"ok"}` when the HTTP app is alive.

`POST /api/transcribe` takes `multipart/form-data` with **one or more file parts
named `files`**, repeated for a batch. Other field names are rejected.

```bash
# LOCALVOX_TOKEN is already exported from your private .env; never put it in URLs.
curl --fail-with-body http://127.0.0.1:8000/api/transcribe \
  -H "Authorization: Bearer ${LOCALVOX_TOKEN}" \
  -F 'files=@./first.ogg' \
  -F 'files=@./second.wav'
```

A valid request returns HTTP 200 and exactly this envelope and per-file fields,
in request order. Individual failures are represented in the array, even when all
files fail:

```json
{
  "results": [
    {
      "filename": "first.ogg",
      "status": "done",
      "text": "Hello there.",
      "error": null,
      "duration_seconds": 2.5
    },
    {
      "filename": "second.wav",
      "status": "error",
      "text": null,
      "error": "Cannot decode this file as audio. Export a supported audio file.",
      "duration_seconds": null
    }
  ]
}
```

`filename` is a sanitized display name; it may be truncated. `status` is `done` or
`error`. `text` is a string on success; `error` is a string on failure. Duration
is measured from decoded samples; it may be present even if inference fails.
The mock backend labels its output `[MOCK]` and never pretends to recognize speech.
The export JSON uses the same envelope; pending UI rows can additionally have
`waiting` or `processing` states.

Request errors use `{"detail":"..."}`:

| HTTP status | Meaning |
| --- | --- |
| 400 | Missing/wrong multipart fields, malformed multipart, too many files |
| 401 | Missing or invalid token/session |
| 403 | Cookie-authenticated mutation lacks a same-origin Origin header, or origin differs |
| 408 | Upload deadline exceeded |
| 413 | Whole HTTP body exceeds the byte limit |
| 503 | Queue full or queue deadline exceeded |

An individual bad extension, oversized file, excessive duration, decoding error,
model error, or inference timeout yields a per-file `error` in HTTP 200.
`POST /share` has the same authenticated multipart contract as the API when called
directly; an installed service worker intercepts Android share navigation instead.
`GET /api/model` requires authentication. Unknown authenticated routes use normal
404/405 errors; interactive OpenAPI pages are disabled.

## Android / PWA / WhatsApp

The manifest defines a multipart POST Web Share Target at `/share`, with repeated
`files` parts. There are install icons and a minimal service worker. **A network
HTTP URL such as `http://192.168.1.20:8000` does not support this PWA workflow.**
Use a browser-trusted HTTPS URL for Android installation and service workers;
localhost exceptions refer to the device itself. A certificate warning bypass is
not a reliable deployment setup.

Android filters share targets by the sending app's MIME type. In addition to
`audio/*` and audio extensions, the manifest accepts `application/ogg` and
`application/octet-stream` for generically labelled attachments. The latter can
also make LocalVox appear for unrelated binary files; server extension checks and
audio decoding still reject unsupported content. This is a compatibility measure,
not a claim about the MIME type used by every WhatsApp version.

If LocalVox is missing from Android's share sheet, uninstall the existing app,
open the HTTPS site in Chrome, sign in, let the home page finish loading, and
install it again so Android registers the current manifest. Confirm LocalVox
appears in Android Settings → Apps; a browser-badged home-screen shortcut is not
equivalent to an installed WebAPK. First test sharing a saved MP3/OGG from Files,
including the share sheet's full app list, then test WhatsApp. If Files works but
WhatsApp does not, investigate WhatsApp's export action and the attachment type.
If neither works, investigate installation, Android/Chrome versions, and device
support. A Web Share Target manifest change may require reinstalling or waiting
for Chrome's installed-app metadata update; refreshing the page alone is not a
reliable way to update Android's registered share filters.

After installation, the service worker receives shared `File` objects and hands
them to the authenticated home page. Shared files start transcription automatically
and are processed sequentially. Files selected or dropped manually still wait for
the Transcribe button; receiving a share does not start pending manual selections.
New shared files received during processing join the existing sequential queue.
The service worker uses volatile memory only, expires pending files
after two minutes, and does not cache audio or authenticated pages. This is not
an offline application. Browser worker suspension/restart or simultaneous shares
can lose pending files; the latest pending share replaces an earlier one. If the
session expired, sign in promptly and re-share if needed. The direct server share
fallback still requires authentication/CSRF protection and may show JSON or an
authentication error when no service worker is active.

Manual Android verification checklist (not run in this environment):

1. Serve over trusted HTTPS, set `LOCALVOX_SECURE_COOKIE=true`, sign in in Chrome
   on Android, and install the PWA through the browser menu.
2. Reopen it once to ensure the service worker controls the home page.
3. In Files or an audio app, share one OGG/OPUS file to LocalVox; verify it starts
   transcription automatically, then export the result. Confirm manual file
   selections still wait for the Transcribe button.
4. Repeat with several files, an invalid file, expired sign-in, and a large file.
5. Try WhatsApp's export/share action for a voice message. Depending on Android,
   WhatsApp version, and message type, it may not offer the audio or LocalVox as a
   target. This project does not integrate with WhatsApp Business or guarantee
   that WhatsApp exposes every voice message.
6. Use the in-app file picker as the fallback after saving/exporting the audio.
   Also check browser suspension, cancellation, and sharing while already open.

The server-side multipart `/share` fallback and a Node-based unit exercise of the
worker multipart redirect and file handoff are tested. Actual Android
intent delivery, PWA installation, service-worker handoff, and WhatsApp behavior
remain manual validation items. See [Chrome's Web Share Target documentation](https://developer.chrome.com/docs/capabilities/web-apis/web-share-target)
and [secure context requirements](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts).

## Security and operations

Use a long random token, firewall the port, and keep dependencies updated.
There is no login rate limiter; high token entropy and restricted exposure matter.
Browser sign-in sets a signed, HttpOnly, SameSite=Lax session for 12 hours; the raw
token is never returned in HTML, URLs, cookies, or API responses. Logout clears
the current browser cookie; copied session cookies remain valid until expiration
or token rotation plus restart. Set the Secure flag for HTTPS. Cookie mutations
require same-origin Origin; Bearer API clients do not need this header. There is
no cross-origin API permission or third-party script dependency.

Access logs are disabled by the CLI, and native worker output is suppressed.
Startup/shutdown logs go to stderr. No request body, authorization header, audio,
or transcript is intentionally logged. Do not enable debug request logging in
fronting infrastructure. The configured token is redacted from display filenames,
transcriptions, and exposed error strings as an additional guard.

FFmpeg runs with an argument list, no shell, generated input paths, no stdin, a
decoding timeout, and restricted formats/protocols. This is reasonable prototype
validation, not a hardened sandbox for hostile media; keep FFmpeg updated and use
container/OS isolation. Only trusted administrators should control environment
variables, model caches, and temporary roots. Do not share a temp root with
unrelated applications. Health liveness is public; transcription and app content
are protected before body parsing.

## Development and verification

```bash
uv pip install --require-hashes -r requirements-test.lock
uv pip install --no-deps -e .
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke.py --backend mock
node --check localvox/static/app.js
node --check localvox/static/sw.js
node scripts/test_share_worker.mjs
node scripts/test_app_queue.mjs
```

Tests generate short synthetic audio, use the mock engine, and require no weights.
They cover health, authentication, sessions/CSRF, batch isolation, byte/count/duration
limits, decoding, queue bounds, safe filenames, cleanup, token leaks, multipart
sharing, and model download integrity/timeout lifecycle. The smoke script starts
an actual server on 0.0.0.0 with a random port and ephemeral token, calls health and
the API over loopback, checks logs and audio cleanup, then stops it.

For a real inference smoke test, supply a nonpersonal audio file:

```bash
.venv/bin/localvox download-model
.venv/bin/python scripts/smoke.py --backend parakeet --audio /path/to/speech.wav
```

See [the executed validation record](docs/VALIDATION.md) for this environment's
results and exact commands. CI/dependency refresh can regenerate hashed locks with
`uv pip compile pyproject.toml --generate-hashes -o requirements.lock` and the same
command with `--extra test -o requirements-test.lock`. Python build tooling is
pinned separately in `pyproject.toml`; Docker's base image is a moving tag, so this
is a reproducible dependency set, not a bit-for-bit image guarantee.

Layout: `app.py` handles auth/HTTP/batches; `audio.py` decodes; `engine.py` defines
the replaceable engine interface and mock/native implementations; `models.py`
provisions the catalog entry; `static/` contains plain HTML/CSS/JS. There are no
frontend build dependencies or database migrations.

## Troubleshooting

- **Missing model:** run `download-model` with the same model directory/volume as
  the service. Merely starting the server does not download it.
- **Checksum mismatch:** retry the dedicated downloader; check disk space and
  network. Do not bypass validation or replace a loaded file in place.
- **401:** check the exported token, stale cookies, and token rotation. Never
  append the token to a URL. The placeholder token is intentionally refused.
- **403:** browser requests must be same-origin. A manual cookie API call needs
  the correct `Origin`; use Bearer auth for scripts.
- **503:** another batch is active or queued. Retry later or use fewer files.
- **Audio error:** export a real supported audio container. Renaming a non-audio
  file is insufficient. Check duration and MiB limits; decode failures may reflect
  an unsupported codec or a damaged export.
- **Slow/OOM:** shorten recordings, reduce CPU threads and duration limits, and
  measure RAM. Raise Docker's memory limit only with available host capacity.
- **PWA not installable:** verify trusted HTTPS on the phone and use a supported
  Android browser. File upload remains usable over trusted LAN HTTP.
- **Native wheel unavailable:** use a supported Linux x86-64/Python 3.11 host.
  Upstream provides source build instructions; that route was not tested here.
- **Temporary data after a crash:** restart the single server using its dedicated
  temp root to clean stale run directories. Never delete another running server's
  files. Container tmpfs is discarded when the container is removed.

## Known limits

Verified: Linux x86-64 install, real Ultra Q8_0 CPU transcription of one short
English sample, mock batch API, health/auth, cleanup, model hash and cache reuse,
and automated security/resource tests. Browser JavaScript syntax was checked.

Not verified: Docker build/start, Android/PWA/WhatsApp end-to-end, browser layout
and screen-reader behavior on actual devices, French speech accuracy, long/noisy
recordings, sustained concurrent load, resource minima, TLS/reverse-proxy setup,
and LAN/WAN reachability from another device. No uptime, offline browser support,
or production hardening claim is made. Files and tasks do not survive a restart;
there is no permanent transcript history, speaker diarization, translation, or
cloud fallback. A client disconnect is not immediate cancellation of computation.

## Licenses

LocalVox source and original icons: **MIT**, explicitly chosen in [LICENSE](LICENSE).
Model weights: **CC BY 4.0**, separate from this project's license. Attribution is
to NVIDIA, Moondream, and Handy for the base model, post-training, and GGUF conversion
respectively. See [NOTICE.md](NOTICE.md) for source links, modification chain,
redistribution obligations, and dependency/FFmpeg licensing notes. No weights or
personal recordings are included in Git or downloaded into the Docker image build.
