# Changelog

All notable changes to `fivefury` are documented in this file.

This project follows a simple release-oriented changelog format with consistent sections per version.

## [Unreleased]

## [0.1.3]

### Changed
- Moved more `RPF` point-read work into the native backend so `GameFileCache` relies less on Python archive objects for one-off reads.
- Split the native Python binding layer by domain (`index`, `crypto`, `rpf`, module bootstrap) to keep the C++ boundary easier to maintain.
- Switched archive-table and entry-payload decryption paths to the native crypto backend instead of keeping redundant Python fallbacks.

### Fixed
- Removed dead and duplicated scan helpers left behind by the `GameFileCache` refactor.
- Reduced the chance of Python and native `RPF` decryption paths diverging over time.

### Performance
- Reduced Python-side overhead for archive table decryption and point reads inside `RPF` archives.
- Batched native archive variant reads used by `get_file()` so stored and standalone reads do not re-resolve the same entry twice.

## [0.1.2]

### Changed
- Reorganized `GameFileCache` into the `fivefury.cache` package with smaller modules for `core`, `scan`, `views`, and asset helpers.
- Split resource texture assets into per-format modules under `fivefury.resource_assets`.
- Refreshed the public README around current `GameFileCache`, extraction, and texture workflows.

### Added
- `ARCHITECTURE.md` with an internal map of the codebase, backend boundaries, and refactor guidance.
- Lazy `GameFileCache` lookups such as `archetype_dict`, per-kind dictionaries, iteration helpers, and kind statistics.
- Helpers to extract all referenced assets from a `YMAP`, including support for loose `.ymap` files.

### Fixed
- Resource extraction now writes valid standalone `RSC7` files by default instead of invalid raw internal blobs.

## [0.1.1]

### Added
- `YTD` texture extraction helpers for listing and exporting textures as `DDS`.
- Embedded texture extraction for `YDR`, `YDD`, `YFT`, and `YPT` assets.
- Per-format resource asset abstractions for embedded texture traversal.

### Changed
- `GameFileCache` can now resolve texture dictionaries through `YTYP` data and `gtxd.meta` parent relationships.
- README documentation now includes texture extraction workflows for `YTD` and resource assets.

## [0.1.0]

### Added
- Initial public release of `fivefury`.
- Native `GameFileCache` scanning for GTA V `RPF` archives with DLC filtering, exclusions, and type-aware lookups.
- `YMAP` and `YTYP` creation, parsing, and saving APIs.
- Global hash resolution utilities and `MetaHash` support.
- Core `YTD` handling and GTA V asset workflow helpers for Python 3.11+ on Windows.
