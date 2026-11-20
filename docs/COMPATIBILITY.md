# Browser compatibility

## Supported API and operating-system contract

The implementation targets current **desktop Chromium browsers on Windows** with
Manifest V3, content scripts, scripting, extension storage, and Native Messaging.
Loading unpacked extensions and contacting a local native host must be permitted
by the browser and its management policies. Private windows and managed profiles
can impose additional restrictions.

The browser-facing code uses shared `chrome.*` extension APIs; it does not depend
on a Vivaldi-specific API. Mobile browsers, Firefox, Safari, macOS, and Linux are
not supported by the current Windows native-host installer.

## Native-host registration

The installer writes current-user keys in both Windows registry views:

```text
HKCU\Software\<browser prefix>\NativeMessagingHosts\com.ytdl.vivaldi
```

| Browser family | Registration prefix or behavior |
| --- | --- |
| Chrome | `Google\Chrome` |
| Chromium | `Chromium` |
| Edge | `Microsoft\Edge`, plus Chromium/Chrome fallback locations |
| Brave | `BraveSoftware\Brave-Browser` |
| Brave Beta / Nightly | Corresponding `Brave-Browser-Beta` / `Brave-Browser-Nightly` prefixes |
| Vivaldi | `Vivaldi` and shared Chrome location |
| Opera / Opera GX | Shared Chrome location documented by Opera |
| Other forks | Vendor-documented prefix supplied through the installer option |

Defaults are listed in `extension-vivaldi/browsers.json`. Additional prefixes are
validated and recorded so the uninstaller can remove entries still owned by this
installation. The browser must genuinely support native messaging; adding a key
does not add an API to a browser that removed it.

The host identifier and unpacked extension ID remain stable across these browsers:

```text
Host:      com.ytdl.vivaldi
Extension: folnohikggmdphdpningknpkkbmnimpo
```

A future store publication can assign a different extension ID. In that case the
allowed origin must be updated deliberately; wildcard origins must not be used.

## Verification status

Native protocol, installer generation, worker options, UI state, and FFmpeg
processing have automated coverage on Windows. Vivaldi functionality has also
been exercised by the project owner. Chrome, Edge, Brave, Opera, and arbitrary
forks have registration/API support but have **not all been tested end to end**
in this development environment. Do not describe an untested browser as verified.

Browser compatibility does not guarantee that YouTube will provide a particular
format or accept a request. Authentication requirements, unavailable media,
network restrictions, and upstream changes can affect all browsers.

## Manual acceptance matrix

Before marking a browser verified, record its version, Windows version, and date,
then check:

1. Load the unpacked extension and connect the engine after a browser restart.
2. Download one MP4 and one MP3 into the chosen destination.
3. Mark a 2–62 second clip, verify its duration, and listen through its final quarter.
4. Download a multi-entry playlist and confirm its folder name and order.
5. Confirm no completion glow appears between playlist entries; confirm one appears
   after the full successful request and clears when acknowledged.
6. Close/reopen the panel, click outside it, scroll it, and test fullscreen playback.
7. Cancel during a download and during FFmpeg processing; check that descendants stop.
8. Test a failed playlist entry and confirm the request is not reported as successful.
9. Unregister the host, reconnect to confirm an actionable error, and reinstall.

## Primary references

- [Chrome Native Messaging registration](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
- [Edge native-host locations and fallback order](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/native-messaging)
- [Opera Native Messaging](https://help.opera.com/en/extensions/message-passing/)
- [Vivaldi extension installation](https://help.vivaldi.com/desktop/appearance-customization/extensions/)
- [Bitwarden native-host registration implementation](https://github.com/bitwarden/clients/blob/main/apps/desktop/src/main/native-messaging.main.ts), a reference for vendor-specific Windows locations
