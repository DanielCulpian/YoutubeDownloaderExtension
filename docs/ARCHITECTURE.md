# Architecture

## Components

| Component | Responsibility |
| --- | --- |
| `extension/manifest.json` | Manifest V3 permissions, public extension key, YouTube content script, native bridge access |
| `extension/player.js` | Player button, isolated panel iframe, click-away behavior, tab-scoped completion glow |
| `extension/popup.html`, `popup.css`, `popup.js` | Shared toolbar/embedded interface, draft settings, clip markers, folder selection, progress |
| `extension/background.js` | Persistent native port, single-job state, bounded logs, terminal success notification |
| `backend/native_host.py` | Binary framing, command dispatch, request validation, worker lifecycle, event forwarding |
| `backend/download_worker.py` | yt-dlp setup, playlist output templates, structured progress, postprocessing |
| `backend/download_options.py` | URL and timestamp validation, format selection, FFmpeg/runtime discovery |
| `backend/clips.py` | Local H.264/AAC or MP3 encoding, independent stream-duration verification, collision-safe clip publication |
| `backend/process_group.py` | Windows job ownership and descendant cancellation, with termination fallbacks |
| `backend/system_paths.py` | Windows known-folder resolution, including redirected Downloads directories |
| `backend/folder_picker.py` | Native folder dialog isolated from the binary messaging stream |
| `install.ps1`, `uninstall.ps1`, `installer_support.ps1`, `browsers.json` | Reproducible dependency setup and ownership-checked per-user registration |

All component paths above are relative to `extension-vivaldi/`.

## Request lifecycle

1. Clicking the player button asks the background service for the sender's
   YouTube tab context. It opens an extension-origin iframe; the YouTube page
   cannot directly invoke the Python bridge.
2. The shared panel reads the source video's URL/title/time using the browser
   scripting API and persists a serializable draft and destination preference.
3. The background service connects to `com.ytdl.vivaldi` using `connectNative`.
   The browser starts `.runtime/host.cmd`, which starts the isolated Python host.
4. The host validates an allowlisted request, assigns its worker to a Windows job,
   and forwards line-delimited worker events as framed native messages.
5. The worker uses yt-dlp to obtain the best accessible streams. FFmpeg merges or
   converts them as necessary. A playlist stays one request across all entries.
6. Individual completed files produce `archivo` events for the log. The worker
   emits `fin` only after `YoutubeDL.download()` returns for the whole request.
7. The host waits for process termination and resource cleanup, then emits
   `terminado`. Only a successful `fin` plus exit code zero and no cancellation
   can publish a completion notice for the source tab.

## Native protocol

Browser/host messages are UTF-8 JSON objects prefixed by an unsigned 32-bit byte
length in native Windows little-endian order. The host caps each message at 1 MiB,
handles partial reads, and rejects malformed lengths and non-object payloads.
Standard output is reserved exclusively for framed messages; logging must not
write raw text into it.

The internal worker protocol uses one JSON event per line. stderr is captured by
the host and becomes bounded log text rather than corrupting the browser protocol.

| Command | Purpose |
| --- | --- |
| `ping` | Confirm the engine connection and return the system Downloads path |
| `descargar` | Start a validated video, playlist, or clip request |
| `cancelar` | Stop the owned worker and its children |
| `carpeta` | Launch the native folder selector |
| `abrir` | Open an existing destination directory in the file manager |

Command and event identifiers are intentionally retained across versions for
compatibility; documentation and implementation summaries are in English.
Requests cannot select arbitrary executables or pass shell commands. Only a
fixed Python worker and known FFmpeg/runtime helpers are launched.

## State and persistence

- `storage.session`: active job, progress, title, bounded log, connection status,
  source tab, and request-level success state.
- `storage.local`: user destination, form draft, and unread completion notice.
- Native process memory: active worker, job handle, temporary-source directory.
- `.runtime/`: generated launcher, allowlisted native-host manifest, registration plan.
- `.venv/`: generated Python environment and installed dependencies.

Closing the panel does not disconnect the native port. Closing the browser or
reloading/disabling the extension disconnects it and cancels the owned job. A
worker crash is a failed request rather than a successful file completion.

The completion glow is local to the originating tab and is acknowledged when
that tab's panel opens. A different tab cannot acknowledge it accidentally.
The beginning of another request clears the previous notice.

## Clip pipeline

Clips use complete source downloads rather than simultaneous seeking in remote
audio/video streams. The host owns the temporary source directory so it can
clean it after cancellation as well as normal completion.

After source assembly, a custom yt-dlp postprocessor:

1. Seeks and encodes the requested interval with FFmpeg.
2. Decodes the audio stream and checks its observed duration.
3. For MP4, also decodes video and compares both durations with the requested
   interval, allowing small codec/frame-boundary tolerances.
4. Publishes the verified output, adding a numeric suffix if the filename exists.
5. Removes temporary sources on completion.

No silence is added to conceal a truncated track. MP4 clips use H.264/AAC and
MP3 clips use VBR MP3. A forced kill during output encoding can leave a temporary
`.ytdl-*` fragment in the selected destination. Unknown duration metadata can
delay a boundary error until postprocessing, where actual stream checks still apply.

## Security and privacy boundaries

The native manifest accepts only the stable extension origin derived from the
checked-in public key. This key is public identity material, not a secret. The
unpacked extension must retain it or registration must be regenerated.

Player/frame close messages verify both the extension origin and the actual
iframe window. UI rendering uses text content instead of interpreting external
titles and diagnostics as HTML. Registry removal checks ownership before deleting
an entry. No installer step changes the user's PATH or registers a startup service.

The browser executes its own registered native host; there is no project HTTP
server and no remote-control port. This does not make third-party dependencies
or user-supplied content inherently trustworthy. Keep dependencies current and
do not share personal paths, video URLs, or logs unintentionally.

## Scope

The GUI application has been removed. The separate console application in the
owner's Documents directory is not part of this repository and is not required
for the extension. The folder name and native-host identifier containing
`vivaldi` are historical compatibility identifiers, not browser restrictions.
