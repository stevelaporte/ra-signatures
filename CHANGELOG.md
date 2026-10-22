# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-10-22

Most of this release ran in production from 2026-06-30 before being committed.

### Added

- **Override system** (`overrides.py`): manually fake the "currently playing" section of any user's signature. Real account stats (points, softcore, mastery count) always come from the live RA API; only `Title`, `ConsoleName`, `ConsoleID`, `ImageIcon`, and `RichPresenceMsg` are substituted. Lookup is case-insensitive.
  - Convention-based icons: drop `./overrides/<username>.png` and it's picked up automatically.
  - `ImageIcon` can be omitted (auto-detect), set to `"local:./path/to/file.png"`, set to an RA-style `/Images/` path, or set to `None`.
  - Overridden users skip the `API_GetGameInfoAndUserProgress` call entirely.
  - `overrides.py` is optional and gitignored; `overrides.example.py` is the template. If it's missing, the app runs with no overrides.
- **Color emoji rendering**: emoji in game titles and rich presence render in color instead of tofu boxes.
  - `NotoColorEmoji.ttf` (SIL OFL 1.1) is rendered at its native 109px bitmap strike and LANCZOS-downscaled to the surrounding text size.
  - `EmojiFallback.ttf` (OpenMoji black, CC BY-SA 4.0) is the monochrome fallback for glyphs the color font lacks.
  - `_split_runs()`, `draw_mixed_text()`, and `mixed_textlength()` handle mixed Pixellari + emoji text.
  - Rendered glyphs are cached per process in `_emoji_glyph_cache`; the color font loads once at import.
  - Tunables: `EMOJI_SIZE_SCALE` (default `0.85`), `EMOJI_Y_SHIFT` (default `-2`).
- **Console icon on the Platform line**, between `Platform: ` and the console name.
  - Icon URLs come from `API_GetConsoleIDs?a=1&g=1` (`IconURL` field).
  - The console list is cached to `api_cache/console_icon_map.json` (24-hour on-disk TTL, `CONSOLE_ICON_MAP_TTL`) and kept in memory for the life of the process.
  - Icons are resized to `CONSOLE_ICON_HEIGHT` (default `14`px) and centered on the 16px line; cached per process.
  - Falls back to text-only if the icon list can't be fetched or there is no `ConsoleID`.
  - Tunables: `CONSOLE_ICON_HEIGHT` (default `14`), `CONSOLE_ICON_GAP` (default `4`).
- **Unsupported character substitution** (`CHAR_SUBSTITUTIONS`): characters Pixellari can't render are swapped for ASCII lookalikes in `RichPresenceMsg`.
  - Initial set: bullet (`\u2022`) and middle dot (`\u00b7`) -> `|`; en dash (`\u2013`) and em dash (`\u2014`) -> `-`; curly quotes (`\u2019`, `\u201c`, `\u201d`) -> straight quotes.
  - Keys use `\uXXXX` escapes so the source file stays ASCII.
- `User-Agent` header (`ra-signatures/<version>`) on all outbound requests to RetroAchievements.
- `__version__` constant in `app.py`.
- Startup check for required settings: the app refuses to start, with a clear error, if `RA_API_USERNAME` or `RA_API_KEY` is missing.
- Generic placeholder backgrounds (`backgrounds/*_default.png`) and a placeholder softcore overlay (`softcore_default.png`), so the app works out of the box.
- `.env.example`, `overrides.example.py`, and `licenses/` (third-party license texts).

### Changed

- **Background selection**: replaced hard-coded `background{01-26}.png` names with a scan of `./backgrounds/*.png` at startup. Any `.png` there joins the pool after a restart. When at least one custom (non-`*_default.png`) background exists, the placeholders are left out of the pool.
- **Bundled assets**: the copyrighted game backgrounds and the original softcore overlay were removed from the repository and replaced with original placeholders. Custom backgrounds and `softcore.png` are now gitignored and stay local.
- "Now Playing" title and "Currently:" line now use `draw_mixed_text()` / `mixed_textlength()`.
- Platform line now renders as label -> console icon -> console name.
- `GamerProfile.fetch_data()` checks overrides after user/awards data is fetched but before the game-info call.
- `GamerProfile._build_override_game_data()` is now an instance method, for the per-user icon lookup.
- **Softcore overlay**: a local `softcore.png` (gitignored) is used if present; otherwise the bundled `softcore_default.png`. Overlays that aren't 768x192 are resized to fit instead of failing.
- The API credentials template is now `.env.example` (documented, empty values); `.env` is no longer tracked.
- `app.py` is ASCII-only.

### Fixed

- `app.py` would fail to import (`SyntaxError: Non-UTF-8 code`) after a restart, because comments had been saved as Windows-1252 bytes.
- Override entries could never show a console icon, because `ConsoleID` was dropped when shaping override data.
- The previously defined User-Agent header was never sent.
- The 1.0.0 `.env` placeholder used `RA_API_USER`, but the app reads `RA_API_USERNAME`. When upgrading, rename the variable in your `.env`.
- An empty `./backgrounds/` directory crashed image generation instead of falling back to a plain background.
- Override users no longer trigger a console-list lookup when no `ConsoleID` is set.

### Notes

- **Encoding gotcha:** pasting non-ASCII characters into source files through some editors/terminals saves Windows-1252 bytes and breaks the Python import. Use `\uXXXX` escapes in string literals and keep the source ASCII.
- Existing `cache/` and `api_cache/` contents are forward-compatible; no migration needed.
- The example systemd unit now sets `PYTHONUNBUFFERED=1` so app log output reaches the journal immediately.
- `overrides/` is created automatically at startup.

## [1.0.0] - 2025-04-08

Initial public release: dynamic RetroAchievements signature PNGs served at `/users/<username>.png`, with hardcore/softcore points, mastery count, current game, rich presence, game icon, random backgrounds, softcore overlay, on-disk image and API caching with ETag/Last-Modified support, and `/invalidate` endpoints.

[Unreleased]: https://github.com/tmfc666/ra-signatures/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/tmfc666/ra-signatures/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/tmfc666/ra-signatures/releases/tag/v1.0.0
