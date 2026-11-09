# Executed validation record

Deployment hostnames and LAN addresses below have been replaced with documentation
examples for public release; commands and observed results otherwise remain as recorded.

Date: 2026-11-09. Repository initially had no source files, instructions, or Git
commits. No existing application work was replaced. All project text is English.

## Environment and installation

- Linux x86-64; system `python3 --version`: Python 3.12.3; `python` not found.
- `uv --version`: 0.11.26. `uv venv .venv` selected managed CPython 3.11.15.
- Available: git, curl, g++, Node v22.23.3. No system FFmpeg, CMake, or Docker.
- The initial `uv venv` attempt failed because the default cache was read-only.
  Retrying with `UV_CACHE_DIR=/tmp/localvox-uv` succeeded.
- Sandbox networking initially failed DNS, and socket creation was denied.
  Dependency/download commands and HTTP tests succeeded with approved sandbox
  escalation. The sandboxed pytest run stalled and was interrupted; its complete
  reruns with socket access passed. These were environment restrictions, not
  successful initial tests.

Executed installation commands (cache variable set for each `uv` command):

```bash
UV_CACHE_DIR=/tmp/localvox-uv uv venv .venv
UV_CACHE_DIR=/tmp/localvox-uv uv pip install --python .venv/bin/python fastapi uvicorn python-multipart pytest httpx imageio-ffmpeg
UV_CACHE_DIR=/tmp/localvox-uv uv pip install --python .venv/bin/python transcribe-cpp
UV_CACHE_DIR=/tmp/localvox-uv uv pip install --python .venv/bin/python -e '.[test]'
UV_CACHE_DIR=/tmp/localvox-uv uv pip compile pyproject.toml --generate-hashes -o requirements.lock
UV_CACHE_DIR=/tmp/localvox-uv uv pip compile pyproject.toml --extra test --generate-hashes -o requirements-test.lock
UV_CACHE_DIR=/tmp/localvox-uv uv pip check --python .venv/bin/python
```

Initial editable installation with `--no-build-isolation` failed because setuptools
was not in the virtual environment. Normal isolated installation succeeded. The
final build backend is explicitly pinned to setuptools 80.9.0. All 27 installed
packages passed dependency compatibility checks. Runtime wheels installed
`transcribe-cpp==0.4.1` and `transcribe-cpp-native==0.4.1`; native device enumeration
identified a CPU backend on an Intel Core i5-12450H. No GPU backend was used.
The imageio-ffmpeg wheel supplied FFmpeg `n9.0.2-17-g2a571b6068-20260930`.

## Model and real CPU inference

The pinned Handy Q8_0 model was downloaded using:

```bash
mkdir -p .cache/models
curl --fail --location --max-time 180 \
  --output .cache/models/parakeet-ultra-Q8_0.gguf.part \
  https://huggingface.co/handy-computer/parakeet-ultra-gguf/resolve/39eeb55181f0d354fd934f06e92fd8d5037fed8e/parakeet-ultra-Q8_0.gguf
```

`localvox.models.verified()` checked expected size 740,363,168 and SHA-256
`007a59761e9258779f189df396b50d12b83bb5b79e66df4b955c230d2f2a0a59` before
renaming the `.part` file. `.venv/bin/localvox download-model` then successfully
verified and reused that cache. Downloader network/atomic behavior is also covered
with synthetic mocked responses; the initial live transfer used curl.

A public-domain 11-second JFK speech sample was fetched into the ignored cache:

```bash
curl --fail --location --max-time 30 --output .cache/jfk.wav \
  https://raw.githubusercontent.com/handy-computer/transcribe.cpp/main/samples/jfk.wav
.venv/bin/python scripts/smoke.py --backend parakeet --audio .cache/jfk.wav
```

Real HTTP response: status `done`, duration 11.0 seconds, transcript:

> And so, my fellow Americans, ask not what your country can do for you, ask what you can do for your country.

The first run took 2.820 seconds wall time for the HTTP transcription call,
including checksum verification, decoding, worker startup, and model loading.
A rerun after format validation changes took 3.687 seconds. These are smoke
observations on a shared host, not performance benchmarks or resource minima.
Each smoke invocation starts a fresh server/model worker. No French evaluation
or recognition-accuracy benchmark was run.

## Automated tests and server smoke

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke.py --backend mock
node --check localvox/static/app.js
node --check localvox/static/sw.js
node scripts/test_share_worker.mjs
.venv/bin/python -m compileall -q localvox tests scripts
UV_CACHE_DIR=/tmp/localvox-uv uv build --out-dir /tmp/localvox-dist
```

- Pytest: **29 passed**, zero failed, in 0.49 seconds on the final application
  changes. One upstream Starlette warning: its httpx TestClient integration is
  deprecated in favor of httpx2. Current tests still pass with pinned httpx 0.28.1.
- Real mock-server HTTP smoke: success, 0.041 seconds for synthetic 0.1-second
  audio on the rerun. Health and unauthorized API rejection also passed.
- Both mock and real Parakeet smoke scripts confirmed clean shutdown, no remaining
  temporary audio directories, and absence of their generated token in logs and
  response text. The generated secret is not written into project files.
- Node syntax checks and Python compileall: passed.
- Node share-worker unit exercise: multipart POST with two synthetic files,
  303 redirect, file handoff to the app, and one-time consumption all passed.
  This mocks worker globals; it does not validate browser/Android integration.
- Python source distribution and wheel builds succeeded; wheel includes catalog,
  HTML/CSS/JS, manifest, icons, LICENSE, and NOTICE. Packaging uses a manifest to
  include test fixtures/helpers and deployment docs in the source distribution.

The server smoke scripts bind on 0.0.0.0 and connect over 127.0.0.1. They stop the
server after verification; no service was intentionally left running.

## Not executed or not established

- Docker image build, Docker healthcheck, Compose startup, volume ownership,
  read-only filesystem/tmpfs behavior, and container resource limits: Docker absent.
- A real Android browser, PWA installation, WhatsApp share UI, browser service
  worker lifecycle, clipboard permissions, responsive layout, or screen reader.
- Reachability from a second LAN device, firewall rules, HTTPS/reverse proxy, VPN,
  Internet exposure, or certificates.
- Other OS/architectures/Python versions, long/noisy/French recordings, sustained
  load, minimum RAM, OOM recovery under container limits, or hard power-loss tests.
- Immediate cancellation on client disconnect. An active bounded batch may finish.

Use the README's manual Android checklist and validate Docker/network deployment
on the target host before relying on either. Dependency installation and model
inference were actually performed; the untested deployment paths are not claimed
as validated.

## LAN sign-in regression fix

A subsequent user report exposed a browser form issue: the original
`Referrer-Policy: no-referrer` response header caused Chromium to submit the login
form with `Origin: null`; the CSRF guard returned 403 even on the LAN URL.
This was reproduced in the installed headless Chromium browser using a deliberately
invalid token. The policy is now `same-origin`, retaining origin information for
same-origin form submissions while limiting cross-origin referrer disclosure.
Null and foreign origins remain rejected; no permissive CORS behavior was added.

Validation after the fix:

- `.venv/bin/python -m pytest -q`: **32 passed**, zero failed, in 0.46 seconds,
  with the same upstream TestClient deprecation warning.
- Restarted the real Parakeet server on 0.0.0.0:8000.
- Used system Python's installed Playwright and Chromium 1234 to open
  `http://192.0.2.10:8000/login` with a 390 × 844 viewport, submit the existing
  private token, and check the actual emitted Origin header, HTTP 303 redirect,
  authenticated home, model-status display, sign-out redirect, and health response.
  All passed. The token was neither printed nor changed.
- This browser check establishes desktop Chromium sign-in behavior with mobile
  viewport emulation; it does not establish real Android/WhatsApp/PWA behavior.

## HTTPS deployment and Android share-target investigation

The user configured a Cloudflare Tunnel at `https://transcription.example.org` and
reported successful PWA installation, followed by a missing Android share target.
Public health, manifest, service worker, and login requests all returned HTTP 200.
Actual Chromium diagnostics on that HTTPS origin found no manifest parsing errors,
a secure context, and an active controlling service worker. The installability
API's only error was the diagnostic browser's private/incognito context; this does
not describe the user's installed Android app.

The manifest was extended to accept `application/ogg` and
`application/octet-stream`, plus the remaining supported audio extensions, and
linked from the login page as well as the home page. Generic binary acceptance is
intended for mislabelled attachments; WhatsApp's actual emitted MIME type has not
been measured on the user's phone. Decoder/extension validation remains in force.

Validation:

- `.venv/bin/python -m pytest -q`: **33 passed**, zero failed, in 0.57 seconds;
  the existing upstream deprecation warning remains.
- `node scripts/test_share_worker.mjs`: passed with OGG and generic-binary MIME
  files; file types survive the one-time handoff.
- Actual Chromium at the public HTTPS origin parsed the updated manifest without
  errors, submitted a synthetic two-file multipart form to `/share`, and displayed
  both files as waiting tasks after the service worker redirect. No real audio was
  uploaded or transcribed in this browser test.

Android OS registration, the user's installed manifest version, and WhatsApp's
share action remain unverified. Reinstallation and a Files-app comparison are the
next phone-side diagnostic steps; the MIME compatibility change is not represented
as a confirmed resolution of Android registration.

## Automatic transcription for shared files

The user confirmed installing through Chrome made Android sharing work, then
requested automatic transcription for shared files while retaining an explicit
start for picker/drop uploads. `app.js` now distinguishes ready tasks from manual
waiting tasks and drains one sequential runner. Shared files arriving during an
active run join that queue; pending manual files are not started by a share.
Empty worker messages have no effect. Queue readiness is omitted from exports.

Executed checks:

- `node --check localvox/static/app.js`: passed.
- `node scripts/test_share_worker.mjs`: passed.
- `node scripts/test_app_queue.mjs`: passed; covers picker and drop waiting,
  automatic multi-file sharing, another share during active processing, manual
  additions during processing, empty worker messages, continuation after a
  per-file error, and at most one active transcription request.
- Actual Chromium at `https://transcription.example.org`: submitted a synthetic OPUS/OGG
  multipart share through the real service worker. Both files triggered API
  requests automatically without clicking start. A subsequent picker selection
  stayed waiting and triggered its request only after clicking Transcribe files.
  API responses were mocked in the browser for this UI test; no speech inference
  was performed or claimed during it. The existing server and inference backend
  were unchanged.

The deployed static assets were verified through the public HTTPS origin. Reopen
or reload the installed app to fetch the new JavaScript; this change does not
require reinstallation or changing Android share registration.
