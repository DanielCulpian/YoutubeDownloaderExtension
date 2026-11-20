# Third-party components

The MIT license in this repository applies to project-owned source. Dependencies
and downloaded media retain their own licenses and rights. Installation downloads
dependencies locally; generated environments and binaries must not be committed.

| Component | Role | Upstream licensing information |
| --- | --- | --- |
| yt-dlp and default extras | YouTube extraction, format selection, download orchestration, JavaScript challenges | [yt-dlp repository and licensing section](https://github.com/yt-dlp/yt-dlp) |
| imageio-ffmpeg | FFmpeg executable discovery and platform wheels | [imageio-ffmpeg license](https://github.com/imageio/imageio-ffmpeg/blob/main/LICENSE) |
| FFmpeg | Stream merging, conversion, clipping, duration verification | [FFmpeg legal information](https://ffmpeg.org/legal.html) |
| Python / Tkinter | Native bridge, worker, Windows folder picker | [Python licensing](https://docs.python.org/3/license.html) |
| Node.js or Deno | JavaScript challenge runtime | [Node.js license](https://github.com/nodejs/node/blob/main/LICENSE), [Deno license](https://github.com/denoland/deno/blob/main/LICENSE.md) |

FFmpeg obligations depend on its build configuration and included codecs; builds
may be subject to LGPL or GPL terms. Do not assume that a binary obtained through
a Python wheel is covered by this project's MIT license. Review the exact upstream
licenses and redistribution obligations before packaging dependency binaries.

The extension icons are simple project-generated geometric assets. Product names
and trademarks belong to their owners. No license to third-party media is granted.
