# Changelog

All notable changes to `fivefury` are documented in this file.

This project follows a simple release-oriented changelog format with consistent sections per version.

## [Unreleased]

### Breaking Changes
- Normalized the high-level authoring API around `add_*` for collections, `set_*` for single assignments, plus `build()` and `validate()` as the preferred normalization and checking steps.
- Renamed the newer high-level `YDR` helpers to match that convention. Notable renames include:
  - `create_bone(...)` -> `add_bone(...)`
  - `embed_texture(...)` -> `add_embedded_texture(...)`
  - `unembed_texture(...)` -> `remove_embedded_texture(...)`
  - `use_bound(...)` -> `set_bound(...)`
  - `skin_model(...)` -> `set_model_skin(...)`
  - `YdrModel.enable_skin(...)` -> `YdrModel.set_skin_binding(...)`
  - `YdrModel.disable_skin(...)` -> `YdrModel.clear_skin_binding(...)`

### Changed
- Added or standardized `build()` and `validate()` entry points across the higher-level `YDR`, `YTD`, `YBN`, `bounds`, `YTYP`, `YMAP`, and `CUT` authoring surfaces.
- Updated the test suite and high-level examples to follow the normalized API style instead of the older mixed naming scheme.

## [0.1.18]

### Fixed
- Relaxed RSC7 page sizing for large resources so oversized but valid legacy `YTD` graphics sections no longer fail during save.
- Applied adaptive resource flag sizing at the shared `RSC7` layer instead of forcing callers to downscale textures, strip mipmaps, or split assets.

## [0.1.17]

### Added
- Real `YDR` skeleton support with `YdrSkeleton`, `YdrBone`, `YdrBoneFlags`, bone lookup helpers, and skinned drawable roundtrip support.
- Small declarative skeleton helpers including `YdrSkeleton.create()`, `add_bone(...)`, `Ydr.ensure_skeleton()`, `Ydr.add_bone(...)`, and `calculate_bone_tag(...)`.

### Changed
- `YDR` LOD names now use the `YdrLod` enum instead of plain strings in the main API surface.
- `YDR` readers and builders now preserve skeleton data instead of only passing through blend weights, blend indices, and skeleton binding flags.

## [0.1.13]

### Changed
- Consolidated duplicated offset-based binary read and write helpers into `fivefury.binary` and switched `YDR`, `YCD`, embedded asset, and `CUT` PSO modules to reuse those shared primitives.

### Fixed
- Reduced drift risk between little-endian resource readers and big-endian `CUT` PSO helpers by centralizing the primitive byte operations.

## [0.1.12]

### Added
- Initial high-level `CUT` and `YCD` animation integration helpers for authoring animation-manager events without working directly against raw PSO nodes.

### Fixed
- Improved PSO inline array handling used by the `CUT` pipeline.

## [0.1.11]

### Added
- High-level `CUT` animation manager authoring helpers for loading animation dictionaries and binding or clearing animation state on scene objects.

### Changed
- `CUT` no-template authoring now includes typed animation payloads and timeline helpers around the animation manager path.

## [0.1.10]

### Added
- `YDR` light support with parsed `Drawable` light attributes exposed as `ydr.lights`, plus `YdrLight` and `YdrLightType`.

### Changed
- `YDR` writer now preserves light lists during roundtrip save workflows.
- `YDR` builder keeps the newer models-first structure while allowing lights to be authored from `YdrBuild` and `create_ydr(...)`.

## [0.1.9]

### Added
- Initial `YCD` reader support with `read_ycd(...)`, clip dictionary parsing, animation metadata, and cutscene-oriented clip name mapping.

## [0.1.8]

### Added
- `merge_ytyps(...)` for combining multiple `YTYP` files, including directory-based merges.
- `ytyp_from_ydr_folder(...)` for generating a minimal `YTYP` from a folder of `YDR` files.

### Changed
- Expanded top-level exports for the `YDR` builder and `YTYP` helper workflows.

### Fixed
- Corrected `OBJ -> YDR` axis conversion so imported models no longer come out laid down.
- Corrected companion `YTYP` generation so the archetype uses `ASSET_TYPE_DRAWABLE` instead of `ASSET_TYPE_DRAWABLEDICTIONARY`.
- Preserved sparse `YDR` UV channel indices instead of compacting them during parsing.

## [0.1.7]

### Added
- Optional companion `YTYP` generation for `OBJ -> YDR`, with `textureDictionary` set to `<model>_txd`.

### Changed
- Lowercased generated `OBJ -> YDR` and companion `YTYP` names so output files and archetype-derived names stay consistent.

## [0.1.6]

### Fixed
- Flipped OBJ `V` texture coordinates during `OBJ -> YDR` import so generated drawables no longer come out with vertically inverted UVs.

## [0.1.5]

### Added
- Documented `RPF -> folder` workflows, `RpfExportMode`, and direct loading of encrypted standalone `.rpf` archives in the public README.

### Changed
- Refreshed the package README so the published PyPI page reflects the current `RPF` export API and standalone archive behavior.

## [0.1.4]

### Added
- `RpfArchive.to_folder(...)`, `RpfArchive.from_folder(...)`, and the functional helper `rpf_to_folder(...)` for exporting archives directly to folders.
- `RpfExportMode` as an explicit enum for `RPF` export workflows, including descriptions for `STORED`, `STANDALONE`, and `LOGICAL`.
- Automatic default crypto initialization for encrypted standalone `RPF` loading, so `RpfArchive.from_path(...)` can open encrypted archives without preloading game keys.

### Changed
- Unified `RPF` ZIP and folder export around the same traversal logic so nested `.rpf` archives are exported consistently.
- Made standalone export the default for folder and ZIP export, which means GTA resources are now written with valid `RSC7` headers unless `LOGICAL` is requested explicitly.
- Cleaned the `RPF` export API so it uses `RpfExportMode` directly instead of the older boolean-style export flag.

### Fixed
- Fixed folder extraction so resource assets no longer lose their `RSC7` container by default.
- Fixed `RPF` export behavior for nested archives by preserving them as directories during recursive export.

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
