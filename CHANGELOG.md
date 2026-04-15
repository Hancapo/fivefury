# Changelog

All notable changes to `fivefury` are documented in this file.

This project follows a simple release-oriented changelog format with consistent sections per version.

## [Unreleased]

## [0.1.35]

### Changed
- Refined `YCD` UV animation semantics around real runtime slot bindings: UV clip names and hashes now derive from `<object>_uv_<slot_index>` and `MetaHash(object) + slot_index + 1`, with explicit validation during export.
- Added `YDR` helpers to expose material slot indices and derive matching `YCD` UV clip bindings, names, and hashes directly from drawable materials and models.

## [0.1.34]

### Changed
- Reworked `YCD` sequence writing so encoded resources are rebuilt from parsed high-level channels and sequences instead of depending on preserved raw sequence blobs.
- Split the oversized `fivefury.ycd.sequences` implementation into smaller track, channel, and codec modules while keeping the public import surface stable.

## [0.1.33]

### Added
- Added `YND` area helpers and `YndNetwork` partitioning so high-level node graphs can be split into game-style pathfind regions automatically.

### Changed
- Tightened `YND` final-resource validation so a single `Ynd` rejects nodes whose coordinates belong to a different pathfind area, while keeping the pathfind representation limits (`WORLDLIMITS_REP_*`) distinct from global world/navmesh limits.

## [0.1.32]

### Added
- Added a native `bounds` backend for hot geometry helpers, octant generation, and BVH construction used by `YBN`/embedded collision workflows.

### Changed
- Split the native `bounds` backend into smaller C++ modules so the Python binding layer stays easier to maintain.

## [0.1.31]

### Added
- Added real `YDD` read/write support for drawable dictionaries, including hash/drawable pairing and parsing each embedded drawable through the shared `YDR` reader.

## [0.1.30]

### Added
- Added generic bounds geometry helpers for building `GeometryBVH`/`BoundComposite` collision bounds from triangle lists, exposed through `fivefury.bounds` and top-level `fivefury` imports.
- Added YDR convenience helpers to build and attach embedded collision bounds from render geometry.

### Fixed
- Fixed RPF resource writing for large `RSC7` entries by using the CodeWalker-compatible `0xFFFFFF` sentinel and storing the true size in the resource header.

## [0.1.29]

### Fixed
- Corrected the shared `phBound` header layout used by `YBN` bounds read/write so bounding-box vectors, centroid data, and packed material words now align with real game resources instead of being written one `Vec4` block too late.
- Fixed regenerated `YBN` collision resources that could load but fail broadphase/physical interaction because child bounds were serialized with the wrong common header offsets.

## [0.1.28]

### Changed
- Tightened `YBN` bounds normalization and validation so composite child bounds, triangle adjacency data, and public composite flags are modeled more explicitly at the high-level API.

### Fixed
- Rebuilt composite `YBN` BVHs from child bounds during export and normalized inverted bound boxes on read, reducing drift against real `CodeWalker`-style collision resources.
- Hardened `YDR` resource writing around drawable-model/material block layout so generated resources stay aligned with the expected `RSC7` page structure.

## [0.1.27]

### Changed
- Unified `RSC7` page-layout flag calculation across `YBN`, `YDR`, and `YCD` writers using a CodeWalker-style block packing strategy.
- Aligned META resource pages-info counts with the page counts encoded by the written resource flags.

### Fixed
- Fixed generated `YDR` files that wrote mismatched `ResourcePagesInfo` page counts versus the `RSC7` header, which could produce invalid virtual-page/fixup metadata.
- Fixed generated and roundtripped `YBN` files with stale root pages-info metadata from bad source files.
- Fixed `YCD` pages-info metadata so it is sized and written from the actual encoded resource page layout instead of a fixed single-page placeholder.

## [0.1.26]

### Added
- Added `YDR` joint-limit read/write support with `YdrJoints`, rotation limits, translation limits, and high-level helpers for attaching joints to drawables.
- Added real-reference `YDR` roundtrip coverage for the expanded `references/ydrs` sample set.

### Fixed
- Preserved legacy `YDR` vertex declarations and vertex-buffer flags during roundtrip instead of rebuilding every mesh through a simplified declaration.
- Fixed sparse UV-channel handling so declarations using higher UV slots without all intermediate channels no longer collapse or corrupt texture coordinate streams.
- Updated the `YDR` vertex encoder to serialize components according to their declaration type, including half-float and packed byte formats, instead of writing every vector-like value as 32-bit floats.
- Fixed skinned `YDR` parsing and roundtrip for packed blend-index streams that use the legacy `COLOUR` component type.

## [0.1.25]

### Fixed
- Fixed a `YBN` writer stall when exporting generated bounds from geometry-heavy inputs.
- Kept the improved page-count preservation path for valid source `YBN` files, while restoring a fast direct flags path for generated collision resources that do not carry explicit root page metadata.

## [0.1.24]

### Fixed
- Reworked `YBN` resource paging so generated standalone collision resources no longer derive `RSC7` flags only from raw byte length.
- Added page-flag calculation from real bound block sizes and preserved explicit root `ResourcePagesInfo.system_pages_count` when roundtripping valid `YBN` files.
- Updated `YBN` writing to pad `system` payloads to the exact size encoded by the written `RSC7` flags, preventing mismatches between the root pages-info metadata and the actual packed resource layout.
- Added regressions to keep real `YBN` roundtrips aligned with the page-count metadata found in working collision resources.

## [0.1.23]

### Fixed
- Reworked legacy `YDR` mesh-buffer serialization so vertex data now lives in `system` pages instead of being emitted into `graphics` pages.
- Updated written legacy `YDR` roots to use `FileUnknown = 'HCLA'`, matching working resource headers instead of the older generic value.
- Added regressions for system-only legacy `YDR` output and real-file roundtrips against working samples.

## [0.1.22]

### Fixed
- Reworked `YBN` bounds serialization to write a real `ResourceFileBase` root, including `FileVFT`, `FileUnknown`, and `ResourcePagesInfo`, instead of emitting zeroed root metadata.
- Preserved additional bound header fields during `YBN` read/write roundtrips, including previously ignored common `Bounds` unknowns and the root pages-info block.
- Aligned generated `YBN` root page counts with the encoded `RSC7` system flags so large collision resources no longer export with an empty or inconsistent pages-info header.
- Updated `BoundBVH` writing to emit `NaN` W components in the BVH bounding vectors, matching the layout used by working resources and CodeWalker.

## [0.1.21]

### Added
- Added generated octants for `BoundGeometry` plus roundtrip support for reading and writing geometry octant data in `YBN` and embedded `YDR` bounds.

### Fixed
- Reworked META/RSC7 writing for `YMAP` and `YTYP` so generated files now preserve the page-based system layout, table ordering, and resource flags used by working game files.
- Corrected `MetaBuilder` block grouping to match CodeWalker-style `DataBlock` packing, which fixes `YTYP` block counts and page placement for larger archetype sets.
- Aligned `Meta.to_rsc7()`, `Ymap.to_bytes()`, and `Ytyp.to_bytes()` with explicit META page flags instead of falling back to adaptive compact flags.

## [0.1.20]

### Fixed
- Corrected `YDR` `DrawableModel` writing so the render-mask word no longer overwrites `GeometriesCount3`.
- Restored the repeated geometry count in written model headers, which aligns generated `YDR` files with the structure expected by the game runtime.

## [0.1.19]

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
- Expanded `YCD` parsing and evaluation with formal track names, plus support for UV, object, camera, root motion, and facial animation tracks.

### Added
- `YCD` write support with `build_ycd_bytes(...)`, `save_ycd(...)`, `Ycd.to_bytes()`, and `Ycd.save(...)`.
- Real `YCD` roundtrip coverage against the sample clip dictionaries in `references/ycd`.

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
