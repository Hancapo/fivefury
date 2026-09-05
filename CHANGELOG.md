# Changelog

All notable changes to `fivefury` are documented in this file.

The changelog is release-oriented and uses a small fixed set of categories:
`Breaking Changes`, `Added`, `Changed`, `Fixed`, and `Performance`.

## [Unreleased]

### Breaking Changes

- YMAP entity flag names use their correct bit positions. Existing numeric flags remain unchanged; runtime IPL light flags have separate explicit names.

### Added

- Typed progress and cooperative cancellation for YCD authoring, validation and saving.

### Changed

- PR checks validate one wheel on Python 3.11; release candidates retain the complete Python 3.11–3.14 matrix.

### Fixed

- YMAP extents use decoded runtime placement transforms, including ordinary quaternion conjugation, simple-heading behavior, MLO orientation and fragment scaling rules.
- LOD-light positions, directions and hash bounds use the same decoded placement as YMAP extents.

### Performance

- Building dense, multi-actor YCD animation sections is about 170x faster, with each section constructed only once per build.
- Binary YCD precision validation is about 190x faster while retaining integer, quarter-frame and sequence-boundary checks at the requested tolerances.
- YCD serialization is about 1.5x faster by reusing encoded sequences during resource layout; saving validated sections also avoids a second serialization.
- Compact YCD sample buffers reduce peak memory by about 10% during large skeletal-animation builds.

## [0.4.23] - 2026-09-05

### Changed

- Automated wheel validation covers Python 3.11 through 3.14 using the same test suite as source checkouts.
- Unit, external integration, ABI and performance tests have explicit suites; selected tests fail rather than silently skipping missing requirements.
- Test contracts target the current public API and no longer tolerate removed APIs through compatibility lookups or optional assertions.

### Added

- Read-only NumPy views of binary arrays, preserving endian and byte strides without copying data.

### Fixed

- Cached YCD rotations interpolate stored channels before reconstruction or normalization, matching fractional-frame playback.
- YCD angular precision validation checks intermediate poses and sequence boundaries independently of integer samples, with separate diagnostics for subframe errors.
- YCD quaternion export preserves hemisphere continuity and uses normalized four-component channels when three-component reconstruction would distort intermediate poses.
- Native RPF reading and scanning support Unicode filenames and directories on Windows.
- CPU skinning and GPU palette packing reject overlapping buffers before modifying outputs.
- Native audio decoding rejects unrepresentable output sizes without terminating Python.
- YCD frame channels reject invalid types, widths and truncated frame data.
- Native bindings share exception-safe buffer ownership and GIL handling.
- Native RPF, audio, and metadata readers remain compatible with Python 3.11 and 3.12 when the wheel is built on newer Python versions.

### Performance

- Binary array reads into Python lists are about 1.2x faster for large scalar arrays and no longer allocate intermediate 64-bit buffers.
- Mesh splitting checks are about 3.6x faster for large meshes already within the vertex limit, avoiding unnecessary remapping tables and chunk allocations.

## [0.4.22] - 2026-09-04

### Breaking Changes

- Failed GameFile decoding now leaves `parsed` unset and `loaded` false; requesting loaded content raises the recorded error instead of returning undecoded bytes.

### Added

- Typed GameFile decoding diagnostics and loading from in-memory bytes.
- Retail AWC MP3 authoring at 32,000 and 44,100 Hz alongside 48,000 Hz.

### Changed

- Native C++ sources and bindings are grouped by domain.

### Fixed

- Multichannel AWC authoring preserves speaker order with correctly ordered stream lookups and compact final MP3 blocks.
- Encrypted RPF rewrites preserve untouched compressed entries and resource layouts without double encryption.
- AWC writers reject out-of-range frequencies, sample counts, playback fields, and chunk-table indices instead of truncating them.
- RPF encryption changes preserve the original payload cipher, key context, and names while writing the requested output mode.
- Nested RPF edits are preserved for archives inserted from bytes, loaded from files, or read from existing archives.
- Repeated RPF writes preserve source payload locations, including in-place saves and interrupted writes.

### Performance

- Reading many entries from the same RPF is about 15.3x faster with reusable native archive tables and indexed directory lookups.
- Cached resource loading performs one decompression per asset instead of two, avoiding a redundant full-size allocation on native and Python archive reads.
- Name-based AssetSet resolution is about 1,100x faster across 2,000 assets by indexing names instead of rescanning the collection for each reference.

## [0.4.21] - 2026-08-31

### Breaking Changes

- `CutScene.cutscene_flags` and its factory argument have been replaced by typed `CutSceneSettings`; direct flag packing is now owned by the writer.
- The fixed `DEFAULT_PLAYABLE_CUTSCENE_FLAGS` constant has been removed.
- `build_cutscene_audio_assets()` now requires `BuildContext` so edition policy is explicit.
- `CutScene.clip_dicts`, `CutScene.clip_dictionary()`, and `CutsceneAssets.ycds` have been replaced by `CutsceneAnimationDictionary`.
- `YcdCutsceneTrack.samples` now uses indexed `YcdTrackSamples` instead of a materialized list.

### Added

- Typed compiled REL metadata families with runtime, release, and external-name-table payloads.
- General DLC mounting for compiled REL sound metadata with typed logical and physical paths.
- General AWC channel-codec inspection and validation of incompatible encryption flags.
- Retail AWC MP3 authoring from PCM with independent frames, streaming blocks, packet indexes, and binary validation.
- Automatic CUT flag derivation from semantic authoring settings, audio bindings, section data, blend-out metadata, and concatenation mode.
- Explicit typed preparation of the global indexes required by CUT dependency resolution, with cancellation, monotonic progress, diagnostics, and per-index timings.
- Typed CUT audio authoring from mastered AWC streams, including DAT54 sound graphs, deterministic bank naming, duration derivation, and binary round-trip validation.
- Edition-aware CUT audio authoring from decoded PCM with explicit retail and analysis profiles.
- Declarative CUT audio binding with explicit offsets, lifecycle events, owned REL/AWC assets, and playback-range validation.
- CUT audio DLC packaging with typed wavepack registration, final RPF verification, and exact cache resolution by bank path.
- Logical CUT animation dictionaries with explicit ownership of their technical YCD sections.

### Fixed

- Enhanced YTD writers now place texture graphics data within representable RSC7 pages while preserving exact texture bytes.
- YFT cloth writers now leave empty morph-map payloads zeroed instead of writing template reference-count data into them.
- CUT vehicle bindings now support mounted vehicle metadata as an explicit runtime source while preserving a zero `typeFile`.
- Retail-cached YCD quaternion tracks now preserve rotations whose component signs change within a sequence window.
- Retail MP3 AWC streams now include and validate their block seek tables.
- CUT audio round-trips now preserve the target edition and speaker layout, including mono codec diagnostics.
- CUT concatenation flags no longer depend on whether the scene contains prop models.
- Authored CUT audio now uses retail DAT54 streaming headers, channel routing, and edition-specific multichannel AWC flags.
- CUT audio DLCs now use the retail sound-metadata layout in Legacy and Enhanced.
- Enhanced retail CUT masters now use the runtime MP3 layout instead of preview-only PCM.
- Sectioned CUT animations now load and bind once while the runtime streams their technical YCD sections.
- CUT validation and asset resolution now follow the authored technical section schedule across attached, loose, and cached YCDs.

### Performance

- Dense CUT/YCD track authoring is about 43.5x faster by sampling only the sequence windows being serialized.
- Indexed source tracks and compact numeric channel buffers retain 99.18% fewer samples instead of expanding complete timelines into Python objects.
- Concurrent CUT preparation and resolution now share one coordinated index build instead of repeating full-corpus work.
- Vehicle appearance and REL sound indexes now persist in compact validated sidecars and load without reparsing their META or REL sources.
- Selective native YTYP relationship extraction makes cold Enhanced asset-to-texture indexing about 10.8 times faster on the tested game corpus.
- Independent vehicle, facial, subtitle, and audio resolution stages run concurrently while retaining deterministic outputs and diagnostics.

## [0.4.20] - 2026-08-24

### Breaking Changes

- Deprecated authoring exports have been removed from the public package.
- Public textual enums now use Python 3.11 `StrEnum` semantics, so `str(member)` returns the serialized value.
- Handling model, handling, and damage flags now use `HandlingFlagValue` instead of `MetaHash`, with `None` representing an absent XML field.
- Null YFT fragment-drawable skeleton names now use `YftFragmentDrawableName.NULL` instead of an empty string.
- Omitted YFT damaged mass, damaged inertia, and group damaged-mass totals now use `None`; numeric zero is an explicit preserved value.
- RPF and DLC authoring now use `RpfEncryption` instead of raw encryption integers or a separate DLC enum.
- File-backed RPF authoring now requires `RpfFileSource.raw()`, `compressed()`, `resource()`, or `archive()` instead of implicit path and nested-archive APIs.

### Added

- Typed whole-network YNV validation for area identity, target resolution, and reciprocal polygon links.
- Typed YFT articulated-body authoring with explicit joint frames, angular ranges, branching link graphs, and per-link mass properties.
- Typed fragment-drawable authoring directly from `YdrBuild` or a donor fragment, including matrices, extra bounds, skeleton-name policy, and skeleton loading state.
- Public RSC7 header inspection, file-backed RPF payloads, and reusable YMF dependency indexes.
- Structured RPF validation for names, directory ranges, platform encryption, packed offsets, payload sizes, nested archives, resource headers, and overlaps.
- AES and NG RPF writing with encrypted compressed payloads and byte-preserving unchanged round-trips.
- PS3 RPF writing with big-endian tables, console AES encryption, and platform-correct archive alignment.

### Changed

- Binary readers, writers, and validators now use structural pattern matching for typed dispatch.
- Multi-cell YNV authoring now rejects unresolved or non-reciprocal polygon networks before returning assets.

### Fixed

- Preserve-profile YFT writing now retains explicit zero damaged mass and inertia values for intact-only physics children.
- Handling metadata now preserves unsigned 32-bit hexadecimal flag values, explicit zero fields, and unknown bits in the retail XML dialect.
- Enhanced drawable writers now preserve explicit 32-bit vertex-buffer bind flags across standalone YDRs, embedded YFT drawables, and split meshes.
- Timed archetypes now preserve typed spatial and hash fields when read from YTYP metadata.
- YFT authoring now preserves explicit null skeleton-name pointers and rejects stale resource pointers in fragment-drawable tail fields.
- Gen9 shader adaptation now omits unsupported Legacy parameters only when they retain their default values and rejects non-default values that cannot be represented.
- Preserve-profile YFT writing now retains legitimate unowned null bound slots in imported fragments.
- YFT cloth writers now preserve controller names that fill the complete 32-byte runtime field.

### Performance

- RPF packaging now streams existing nested archives and inspects resource headers without parsing, reserializing, or inflating their payloads.
- File-backed binary compression now writes DEFLATE incrementally without retaining the source or compressed payload in memory.
- NG encryption tables are compressed in the package and loaded only when an NG archive is written.
- Regional YMF builds can reuse one prepared YTYP dependency index across map groups.

## [0.4.19] - 2026-08-22

### Breaking Changes

- Spatial fields across assets now require and return immutable `Vector2`, `Vector3`, `Vector4`, `Quaternion`, `Aabb2`, and `Aabb3` values instead of anonymous float tuples.
- Vector and quaternion components are accessed through `x`, `y`, `z`, and `w`; positional indexing and sequence-style length checks are no longer supported.
- Procedural vector, quaternion, interpolation, and bounding-box helpers have been removed in favor of operations on the value objects themselves.
- Axis-aligned bounds now expose typed `minimum` and `maximum` values instead of tuple pairs.

### Added

- Public spatial value classes with arithmetic, distance, normalization, interpolation, and finite-value inspection.
- Quaternion construction, composition, rotation, interpolation, continuity, and Euler conversion as typed operations.
- Typed two-dimensional and three-dimensional bounds with center, size, radius, containment, union, and point-derived construction.

### Changed

- Readers, writers, validators, authoring APIs, and asset models now preserve the same spatial types across CUT, drawable, fragment, collision, map, navigation, audio, and cache workflows.
- Conversion to tuples or indexed arrays now occurs only at binary, NumPy, and native-extension boundaries.

## [0.4.18] - 2026-08-17

### Fixed

- Ped init records duplicated across same-tier DLC copies of `peds.ymt` now resolve instead of blocking expression-set and YED resolution.

## [0.4.17] - 2026-08-16

### Fixed

- Vehicle-glass projection bases now preserve raster-centred pane placement.

## [0.4.16] - 2026-08-16

### Breaking Changes

- Enhanced car, bike, boat, helicopter, and train stream assets now require paired base and high-detail YFTs.

### Added

- Paired vehicle YFT authoring and cross-fragment validation.

## [0.4.15] - 2026-08-16

### Fixed

- Vehicle-glass validation now resolves polygon materials in direct collision geometry.
- Sparse skinning palettes now resolve local blend indices before skeleton indices.

## [0.4.14] - 2026-08-16

### Breaking Changes

- Vehicle metadata flags and repeated IK offsets now use lossless typed containers.

### Added

- Typed vehicle-glass shatter-map authoring and cross-asset validation.
- Retail vehicle metadata XML authoring and dialect validation.

## [0.4.13] - 2026-08-16

### Breaking Changes

- Platform DLC paths now distinguish virtual registrations from physical payload entries.

### Fixed

- Enhanced vehicle DLCs now store platform archives under `x64` while registering them through `%PLATFORM%`.

## [0.4.12] - 2026-08-16

### Breaking Changes

- `VehiclePackBuilder` now requires explicit setup metadata with a timestamp and load order.

### Added

- Platform-relative DLC archive authoring and mounted-registration resolution.

### Fixed

- Enhanced vehicle packs now use platform-relative streaming archives and explicit startup activation.

## [0.4.11] - 2026-08-16

### Added

- Axis-aware collision discs and declarative vehicle-wheel bounds.
- Vehicle YFT physics profiles now support direct wheel discs and rider capsules.

## [0.4.10] - 2026-08-16

### Added

- Typed authoring, validation, cloning, and XML writing for vehicle metadata.
- GTA V Enhanced vehicle DLC assembly with streamed YFT/YTD assets and complete pack validation.

## [0.4.9] - 2026-08-15

### Added

- Strict YTD mip-chain, payload-size, descriptor-limit, and target-format validation.

### Fixed

- Enhanced YTD authoring now emits retail-compatible runtime texture descriptors for multi-level textures.

## [0.4.8] - 2026-08-15

### Added

- Typed per-builder and per-track YCD channel encoding policies with binary read-back accuracy validation.

### Fixed

- Breakable-glass authoring now accepts declarative drawable models, meshes, materials, and optional skinning arrays.

## [0.4.7] - 2026-08-15

### Added

- Typed CUT YCD quaternion encoding options and channel-layout auditing.

### Changed

- CUT YCD dynamic rotations now use retail cached-quaternion channels by default.

### Fixed

- CUT YCD quaternion sampling now preserves shortest-path continuity across keyframes and sequence boundaries and rejects invalid rotation samples.

## [0.4.6] - 2026-08-15

### Fixed

- Animated CUT cameras now bind their technical YCD clips in every active section, with cross-asset validation for missing runtime bindings.
- CUT animation validation now follows runtime concatenation sections and accepts animated weapons, lights, and particle effects.
- CUT particle stop, decal removal, and attached-light events now preserve their runtime argument payloads.

## [0.4.5] - 2026-08-15

### Breaking Changes

- YDR, YCD, and YED validation now returns structured reports and no longer exposes format-specific validation issue types.
- YFT semantic and binary validation now uses structured reports with stable diagnostic codes and no assertion-style public helpers.
- CUT and DLC validation now returns structured reports and uses the shared validation error contract.
- Bounds and YBN validation now uses structured, path-aware diagnostics.
- GTA5 cache, heightmap, and water validation now uses structured diagnostics and the shared validation error contract.
- YMAP, YTYP, MLO, and LOD-light validation now uses structured cross-asset diagnostics.
- YMF manifest and PSO layout validation now uses structured diagnostics with binary field paths.
- YND and YNV validation now uses structured diagnostics for navigation limits, references, and topology.
- YTD, ped expression binding, and AWC lip-sync validation now uses the shared structured-report contract.
- `BuildContext` validation now requires the canonical structured-report signature without reflection or string adaptation.
- `validate_resource_pointer()` has been renamed to `resolve_resource_pointer()` to reflect its resolving behavior.
- CUT animation checks now return structured warnings instead of compatibility text lists.

### Added

- CUT resolution for high-detail vehicle fragments and their texture dependencies.
- Runtime camera authoring and cross-asset validation for CUT/YCD projects.

## [0.4.4] - 2026-08-15

### Added

- Typed vehicle appearance resolution from `carvariations` and `carcols` for standalone models and CUT vehicle bindings.

### Changed

- Vehicle metadata now shares one typed API across XML metadata and binary YMT resources in Legacy and Enhanced.

## [0.4.3] - 2026-08-14

### Breaking Changes

- `CutsceneAssets.validate()` now returns a non-mutating `ValidationReport`; mutable finalization belongs to `build()`.
- DAT54 synth, transform, and sound-list fields now use their runtime names instead of guessed labels.

### Added

- GPU-resident vertex and compute skinning for GLSL and HLSL renderers.
- Compact four-influence streams and reusable three-row bone palettes for GPU upload.
- Typed loose-file and loose-directory loading for cross-asset authoring contexts.
- Context-aware CUT project validation for YCDs, streamed models, archetypes, skeletons, facial tracks, and audio containers.
- Graphics-page YCD reading.
- Public REL sound-graph traversal and audio endpoint resolution.
- Typed reading and writing for every DAT54 sound variant.
- Typed reading and writing for DAT4 audio configuration values, wave slots, variable lists, and early-reflection settings.
- Typed DAT149, DAT150, and DAT151 world ambience, zone, and emitter metadata.
- Typed DAT15 dynamic mixer patches, scenes, groups, modules, category maps, and tri-state metadata.
- AWC stream and multichannel layout validation.

### Changed

- DAT54 authoring validates runtime capacities for sounds, transforms, variables, ranges, and sets.
- Game REL authoring preserves source item spacing and derives required item alignment.

### Fixed

- YED component reads use runtime defaults for missing facial, generic, and bone tracks.
- Animated CUT instances can share one streamed model while resolving distinct sectioned YCD clips.
- CUT templates can be used when writing attached YCD dictionaries.
- CUT audio resolution handles metadata bank references and multichannel sound graphs.
- Simultaneous CUT events preserve their authored order.
- Multichannel REL sound graphs preserve container and stream pairing.
- DAT54 layouts preserve runtime integer widths and compact count fields.

### Performance

- Cached REL sound indexes avoid repeated metadata scans during CUT resolution.
- Compact influence streams reduce static GPU upload storage by 75%.
- Three-row affine palettes reduce per-frame bone uploads by 25%.
- GPU-resident compute skinning is up to 164x faster than reusable CPU skinning for one million vertices on a high-end Ada Lovelace GPU.

## [0.4.2] - 2026-08-13

### Added

- Batch vertex skinning for positions and normals.
- Reusable skinning batches with caller-owned output buffers.

### Performance

- CUT parsing is about 2.4x faster.
- Persistent archetype texture indexes make repeated cutscene asset resolution about 14x faster.
- Lazy relationship sidecars make warm cutscene dependency resolution about 1.2x faster.
- Native vertex skinning is about 16x faster.
- Prepared per-frame skinning is up to 2.2x faster.
- Native skeleton hierarchy composition is about 79x faster.

## [0.4.1] - 2026-08-13

### Breaking Changes

- Assimp and Impasse mesh APIs have been replaced by Trimesh scene import.

### Added

- In-memory Trimesh scene conversion for YDR and YNV authoring.

### Changed

- Mesh files, materials, instances, transforms, UVs, and vertex colours use one shared Trimesh frontend.
- NumPy 2.4 and Trimesh 5 are now the supported dependency versions.
- Mesh indices and material slots reject lossy numeric conversions.

### Performance

- Mesh normal generation is about 7x faster.
- Mesh tangent generation is about 4x faster.
- Mesh transforms are about 1.9x faster.
- Skeleton matrix inversion is about 11x faster.

## [0.4.0] - 2026-08-13

### Breaking Changes

- The incomplete `.cutxml` parser and scene-loading API have been removed.
- Shared map extension models now live only in `fivefury.map_extensions`.
- PSO value helpers moved from `fivefury.vehiclemeta.common` to `fivefury.pso_values`.
- Generic `add(...)`, `add_*`, duplicate `create_*`, and ordinary `set_*` authoring aliases have been removed. Existing objects now use typed collection operations such as `append`, `extend`, or mapping assignment; convenience construction uses singular noun factories; and one-to-one relationships use properties.
- Typical migrations include `ymap.add_entity(entity)` to `ymap.entities.append(entity)`, `ymap.create_entity(...)` to `ymap.entity(...)`, and `ydr.set_bound(bound)` to `ydr.bound = bound`.
- Explicit domain verbs now carry fixed behavioral contracts instead of acting as assignment aliases: `ensure_*` returns an existing component or creates only its minimum empty form, `bind_*` establishes and validates a semantic relationship, and `resolve_*` performs lookup without mutating source data.
- Derived-state verbs are similarly distinct: `derive_*` produces data from authoritative inputs, `normalize_*` canonicalizes an existing representation without inventing content, and `recalculate_*` explicitly replaces derived values after their source data changes.
- CUT and YCD builders now use `binding(...)`, `object(...)`, `track(...)`, `event(...)`, `ped(...)`, `prop(...)`, `camera(...)`, and other typed noun factories.
- YMAP, YTYP, YDR, YBN, YTD, bounds, GTXD, RPF, Water, and cache models now expose one canonical insertion path per relationship.
- `create_ymf_for_ymaps(...)` has been removed; use `build_ymf_for_ymaps(...)`.
- YMAP and YMF cross-asset operations now receive a single `BuildContext` instead of separate YTYP, YBN, cache, and strictness arguments.

### Added

- Shared `AssetRef`, `AssetSet`, and `BuildContext` primitives for typed cross-asset authoring.
- Structured validation diagnostics with stable codes, severity, asset names, and field paths.
- A strict authoring and implementation style guide covering naming, duplication, module boundaries, performance, validation, and compatibility policy.
- Runtime-compatible YDR light extraction, LOD-light hashing, categorization, transforms, and source-bound validation.
- Deterministic distant-light and LOD-light YMAP generation with spatial partitioning and script-controlled groups.
- Lazy texture dictionary catalogs with searchable texture metadata and deferred pixel loading.
- Texture dictionary relationship graphs with source precedence, conflict, cycle, and missing-parent diagnostics.
- Contextual texture resolution across embedded dictionaries, archetypes, GTXD parents, same-name dictionaries, and explicit global fallback.
- Lazy ped outfit catalogs with on-demand component and prop resolution.

### Changed

- YMAP LOD and distant-light maps serialize and validate independently, matching the parent-child streaming layout.
- Gen9 material initialization uses named presets with stable serialized hashes.
- XML source handling, navigation, coercion, formatting, and atomic persistence share common helpers.
- DLC, Water, YMF, GTXD, and expression-set XML models use the shared XML layer.
- CUT and legacy/Enhanced shader XML loaders use the shared XML frontend.
- AWC reading and writing use isolated container, table, stream, chunk-layout, and payload phases.
- RPF archive implementation is separated from its public package facade.
- Reports, extension containers, and unsigned-field validation share common infrastructure.
- PSO-backed formats share field, hash, text, list, and vector coercion helpers.
- YMAP and YTYP extensions share one implementation instead of parallel copies.
- Internal imports, control flow, and type validation are normalized across formats.
- Internal format readers no longer depend on package facade import order.
- Internal annotations, exports, imports, and collection helpers follow the current Python style.
- YCD sequence bitstreams are decoded and encoded by the native backend.
- YDR and YFT vertex decoding and oversized mesh splitting use the native backend.
- Bounds polygon and BVH records, plus YNV edge lists, are decoded by the native backend.
- PSO and Meta readers use a native binary document for checked bulk array decoding.
- RPF construction uses constant-time child lookup instead of linear sibling scans.
- GameFileCache keeps a byte-bounded LRU of decoded asset payloads.

### Performance

- Native YCD bitstream decoding is about 16x faster.
- Native vertex decoding makes representative YDR and YFT loading about 3.1x and 7.1x faster.
- Native bounds and navmesh decoding makes representative YBN and YNV loading about 2.9x and 4.1x faster.
- Native binary documents perform bulk unsigned-integer decoding about 2.4x faster.
- Native batch hashing is about 2.2x faster than scalar FFI calls.
- META block assembly makes representative YMAP serialization about 10% faster.
- Native batch vector and quaternion interpolation is about 16.6x faster.
- Reusing prepared BVHs makes representative YBN writing about 25% faster.
- Native bulk point bounds are about 4x faster than the replaced Python loop.

### Fixed

- Typed YMAP LOD-light vector arrays serialize through the public authoring API.

## [0.3.16] - 2026-08-12

### Fixed
- Windows ABI3 wheels decode encrypted AWC containers on Python 3.11.

## [0.3.15] - 2026-08-12

### Fixed
- YCD rotation tracks interpolate through the shortest quaternion path between sub-frame samples.
- CUT prop bindings resolve archetype texture dictionaries and their GTXD parent chains.

## [0.3.14] - 2026-08-12

### Added
- Typed loading of shared ped expression-set metadata.
- CUT ped bindings resolve shared expression sets and their ordered YED programs.

## [0.3.13] - 2026-08-11

### Fixed
- Compact multichannel AWC blocks use their encoded channel sizes without consuming block padding.

## [0.3.12] - 2026-08-11

### Fixed
- Euler XYZ conversion follows the runtime's world-axis rotation order.

## [0.3.11] - 2026-08-11

### Added
- Deterministic YED expression evaluation for facial animation tracks.
- CUT resolution of ped expression metadata and YED dictionaries.

### Fixed
- Conditional YED branches preserve their runtime meanings.
- Encrypted multichannel AWC streams decode and rebuild per audio block.
- CUT audio resolution uses the scene's logical audio container names and exact stream identities.

### Performance
- YED facial expressions execute through a cached native VM.

## [0.3.10] - 2026-08-11

### Added
- Declarative CUT facial animation modes with YCD clip resolution and runtime validation.
- Complete ped expression bindings and facial skeleton validation for YMT and YED assets.
- Declarative YCD facial authoring for merged cutscene clips, controls, visemes, blend shapes, transforms, animated normal maps, and tinting.
- Formal names for the built-in RAGE animation tracks used by YCD assets.
- Composable YDR render-pass masks with named default, shadow, reflection, mirror, and water-reflection flags.
- Public skeleton transform and skinning matrix helpers for runtime animation consumers.
- AWC codec metadata and PCM extraction for Enhanced MP3 and Vorbis streams.
- Embedded AWC lip-sync clip dictionaries with typed 32-bit, 64-bit, and custom chunk tags.
- CUT dependency resolution for sectioned animations, actors, textures, audio, and subtitles.
- Structured CUT resolution traces, audits, benchmarks, and cooperative cancellation.

### Changed
- YCD rotation tracks evaluate cached quaternion channels using their declared track format.
- YMT files expose formal content types for all roots used by the Legacy and Enhanced game data.

### Fixed
- YCD writing preserves explicitly serialized track formats instead of replacing them with inferred defaults.
- Enhanced sampler-state parameters no longer inherit colliding legacy texture metadata.
- YDR validation reports genuinely null optional texture slots as informational instead of warnings.
- Gen9-to-legacy drawable conversion ignores unbound Gen9-only texture resources.
- Archive scans classify named metadata consistently with loose files.
- Enhanced MP3 AWC seek tables preserve their serialized entry width.

### Performance
- AWC ADPCM, PCM channel operations, peak generation, and RSXXTEA run in the native backend.
- AWC PCM WAV handling and multichannel block extraction run in the native backend.
- GameFileCache uses stored asset types directly and supports batched typed hash and name lookups.
- CUT dependency resolution uses direct container, prefix, and metadata indexes instead of global asset and YMT scans.
- GameFileCache retains larger dependency sets and reuses parsed texture-parent metadata.

## [0.3.9] - 2026-08-08

### Added
- Coordinated high-level authoring and package output for CUT scenes and their YCD sections.
- YCD cutscene builders support explicit starting section indices.
- YFT tune-name rewrites can opt into trailing page padding.

### Changed
- Authored cutscenes now require semantic validation and a successful binary round-trip before saving.
- PSO block alignment can be selected per format while preserving YMF layouts.

### Fixed
- Cutscene validation rejects invalid target roles, attachment cycles, non-finite values, and unresolved animation dictionaries.
- Cutscene YCD sections follow technical streaming cuts independently of camera shots.
- Cutscene ped validation permits streaming without a type file.
- Path-backed RPF entries remain readable before packaging.
- Path-based DLC reads release their archive handles.
- Enhanced shader constant buffers accept flat multi-vector values.
- YCD dictionaries preserve valid hash keys that overlap resource address ranges.

## [0.3.8] - 2026-08-08

### Fixed
- Enhanced drawables with embedded textures now serialize with valid resource ownership.

## [0.3.7] - 2026-08-07

### Added
- Texture usage and usage flags on texture dictionary entries.

### Fixed
- Enhanced shader texture references use the layout the runtime expects, so Enhanced YDR, YDD, and YFT assets load correctly.
- Enhanced shader groups, shader parameter info, and vertex declarations match shipped drawables.
- Texture usage is preserved when reading and rewriting Legacy and Enhanced texture dictionaries.

## [0.3.6] - 2026-08-06

### Added
- Public Legacy-to-Enhanced shader adaptation for drawable authoring.
- Native Enhanced shader parameter defaults.

### Changed
- Enhanced materials preserve their source render behavior while using native shader families.
- YDR validation issues expose a consistent severity value.

### Fixed
- Reflective Enhanced materials preserve environment texture bindings.
- Enhanced alpha and cutout materials retain their intended rendering behavior.

## [0.3.5] - 2026-08-06

### Added
- Context-aware runtime profiles for full-ped and cutscene-component YDD dictionaries.
- Complete DLC content metadata, change-set conditions, resource references, and content groups.
- Target-aware DLC validation for embedded Legacy and Enhanced assets.
- Target-aware validation for loose DLC folders.

### Changed
- DLC metadata is split into focused content and setup modules.
- DLC RPF output validates its contents and exposes the supported encryption markers.

## [0.3.4] - 2026-08-05

### Added
- Runtime profiles for Legacy cutscene-ped YDD dictionaries.
- Safe in-place rewriting of YFT tune names.

### Changed
- YDD writers now order drawable hashes and reject duplicates.
- YCD writers now reject hashes that collide with the resource pointer range.

### Fixed
- YDD runtime headers are preserved across binary round-trips.
- External texture references in cutscene-ped YDDs use their matching runtime class.
- Mixed YDD runtime profiles are rejected instead of being silently rewritten.
- Explicit null texture parameters survive YDR read and write operations.
- Cutscene YCDs preserve final-frame samples and static quaternion orientation.

## [0.3.3] - 2026-08-04

### Breaking Changes
- `set_draw_distance` now requires near and far distances.
- `set_attachment` now identifies the child, parent, and attachment bone.

### Added
- Named animation clip events.
- Complete camera render overrides, character lighting, and time-of-day DOF modifiers.
- CUT bindings for weapons, animated lights, particle effects, bounds, rayfire objects, and generic event objects.
- Vehicle colour, livery, dirt, and extra-bone variation payloads.
- Public CUT runtime and binary capacity constants.

### Changed
- CUT events now use the runtime event ordering without modifying authored times.

### Fixed
- CUT files loaded from RPF archives now decode through `GameFileCache`.
- CUT rewriting now preserves dynamic fields and vehicle bone-name lists.
- CUT saves now replace destination files atomically.
- Draw-distance and attachment events now use their proper argument layouts.
- Template-free CUT authoring now uses the complete object and event-argument schemas.
- CUT validation now rejects invalid durations, frame ranges, section layouts, and array capacities.

## [0.3.2] - 2026-08-03

### Fixed
- Generated YNV edges now preserve both persistent neighboring-polygon references.
- Box occluder size and rotation fields now use the runtime layout.
- YDR/YFT root render-bucket masks now reflect the materials used by each LOD.

## [0.3.1] - 2026-08-02

### Added
- PSCH enum definitions can now be read and written through the public PSO API.
- Public validation for YMF PSO roots, blocks, arrays, pointers, and schemas.

### Changed
- Rewriting a YMF now preserves PSO schemas and sections without semantic model equivalents.

### Fixed
- YMF manifests now use the runtime-compatible PSO layout required for streamed MLO registration.

## [0.3.0] - 2026-08-01

### Added
- Enhanced YFT environment-cloth authoring, including controllers, simulation bridges, tuning, morph controllers, Verlet data, and nested collision bounds.
- Target-aware YED authoring and cross-edition rebuilding for expression dictionaries.
- Target-aware YCD authoring for animation maps, animations, clips, clip lists, properties, tags, attributes, and cutscene animation dictionaries.
- Bone-scale animation tracks in YCD sequences.
- Target-aware YND and YNV authoring across road networks, in-memory polygon builders, and Assimp navmesh conversion.
- Target-aware YBN authoring with automatic source detection and canonical collision-bound headers for each edition.
- Target-aware YDD authoring for drawable dictionaries, embedded drawables, shaders, and the resource version required by each edition.
- Binary reading, writing, and authoring for `gta5_cache_y.dat` from in-memory or loose YMAP, YTYP, and YBN assets, with `GameFileCache` integration.
- Enhanced YDR and YFT authoring for drawables, skinned geometry, physics, and collision bounds.
- Automatic YFT mass, center-of-gravity, angular-inertia, and inverse-property calculation from physics bounds.
- Collision-material densities and volume-weighted composite density calculation.
- Public YMF runtime limits and validation for map dependencies, type dependencies, managed groups, interior bounds, and serialized capacities.
- Formal YNV polygon flags and declarative pedestrian-density and audio fields.
- Declarative YFT breakable-glass authoring from drawable geometry, skeleton bindings, physics groups, and collision bounds.

### Changed
- YFT mass calculation now derives density from collision materials by default.
- YED saves now replace destination files atomically.
- Project license changed to The Unlicense.

### Fixed
- Enhanced shader sampler semantics and runtime parameter resolution.
- Composite-bound active counts and reserved capacity during binary round-trips.
- YFT physics archetype filenames during binary round-trips.
- Enhanced material parameter layouts during binary round-trips.
- YFT event-set layout and target-specific runtime headers.
- Enhanced YFT articulated-joint runtime headers during reconstruction.
- Enhanced YFT breakable-glass pane layouts and vertex declarations.
- YFT breakable-glass group, pane, shader, bone, geometry, and bound validation.
- YFT validation of native unavailable mass and angular-inertia values.
- Enhanced YFT drawable layout detection and byte-identical lossless round-trips.
- Enhanced skinned geometry now preserves declared vertex offsets.
- Enhanced resource streams with zero-initialized DEFLATE history can be decompressed.
- YMAP parent and manual-streaming flag semantics.

## [0.2.25] - 2026-07-31

### Fixed
- YMF manifests now mark YTYP dependencies containing MLO archetypes as
  interior data, including YTYPs without child dependencies.

## [0.2.24] - 2026-07-31

### Fixed
- YTYP and MLO primitive metadata now uses the native type identifiers required
  by the streaming runtime.
- Byte and vector metadata blocks no longer serialize as unresolved structure
  references.

## [0.2.23] - 2026-07-30

### Fixed
- Removed the incorrect 11-entity limit for the first MLO room while retaining
  the actual packed room and portal limits.

## [0.2.22] - 2026-07-30

### Fixed
- YFT fragment composites now omit child-flag arrays when no flags were
  authored, preserving their runtime physics classification.
- Standalone collision composites continue to serialize explicitly authored
  child flags.

## [0.2.21] - 2026-07-28

### Fixed
- YFT physics archetype reference counts are now read, preserved, and written
  instead of being replaced by an implicit default.

## [0.2.20] - 2026-07-28

### Fixed
- Damaged YFT collision bounds now account for their LOD, archetype, and
  drawable owners.
- Binary validation now verifies the expected owner count for each physics
  bound state.

## [0.2.19] - 2026-07-27

### Fixed
- YFT prop profiles now preserve valid empty collision slots across damage
  states.
- YFT validation distinguishes intentionally empty collision slots from active
  slots with missing or invalid bounds.

## [0.2.18] - 2026-07-27

### Breaking Changes
- YFT authoring now defaults to the prop collision profile and rejects
  incompatible bound topology.

### Added
- Public YFT physics-bound profiles and fragment collision geometry authoring.

### Changed
- YFT binary validation now covers physics-bound topology, ownership, and
  packed geometry limits.

## [0.2.17] - 2026-07-27

### Breaking Changes
- `YftFragmentDrawable.extra_bound_indices` is replaced by
  `extra_bounds`, which exposes owned bounds instead of numeric indices.

### Fixed
- Corrected YFT fragment drawable extra-bound serialization and validation.

## [0.2.16] - 2026-07-26

### Added
- Public YNV authoring APIs build cells directly from in-memory polygons,
  expose grid conversions and binary limits, and return source-polygon
  provenance.
- Common bound ownership and RSC7 pointer validation utilities.

### Changed
- Assimp navmesh conversion now uses the public YNV polygon authoring path.
- Core binary asset writers replace destination files atomically.

### Fixed
- Cross-cell YNV polygons now retain external-edge adjacency between generated
  cells, and polygons above the native vertex limit are triangulated.
- YFT bound reference counts now reflect their serialized LOD, archetype,
  composite, and drawable ownership.
- YFT validation rejects invalid drawable shader references and glass shader
  indices before writing.
- YBN, YFT, YND, and YNV writers reject invalid null-bound metadata, resource
  pointers, and packed field ranges before serialization.

## [0.2.15] - 2026-07-26

### Fixed
- YCD writers now emit runtime class markers, clip lifetime fields, and empty
  tag and property containers required by animated map objects.
- YNV special links now validate polygon IDs against the endpoint area.
- YNV polygon split-array block indices are recalculated during writing.
- YFT damaged archetypes now own independent bounds and physics entity
  drawables reference their matching archetype child bounds.
- YFT authoring no longer creates damaged physics data without a damaged state.
- YFT damping masks, root damage regions, and root-inclusive bony-child ranges
  now use their native values.
- YFT physics LODs no longer overwrite the high LOD's drawable-bound links.
- YFT readers and writers preserve sparse and nullable composite child slots.
- YFT binary validation now accepts auxiliary vanilla composite slots and
  rejects invalid data retained by null slots.

## [0.2.14] - 2026-07-25

### Fixed
- Rebuilt YND links now clamp their distance to the valid 1..255 range.
- Single-child YFT physics fragments no longer alias their Physics LOD child as the fragment root child, preventing duplicate runtime construction and invalid fixups.

## [0.2.13] - 2026-07-25

### Added
- Public `YnvEdgeFlags` names expose adjacency-disabled, cover, high-drop, and external-edge semantics without requiring callers to edit packed bits.

### Fixed
- YNV edge polygon references now use GTA V's native 15-bit layout, reserve `0x7FFF` as the null polygon sentinel, and place adjacency and free-space fields at their correct bit offsets.
- Assimp navmesh generation now marks cross-cell links with the native external-edge flag.
- YNV validation now rejects polygon and index counts that cannot be represented by the runtime format, invalid local polygon references, and more than 32 adjacent-area lookups before serialization can truncate them.

## [0.2.12] - 2026-07-25

### Fixed
- YFT secondary visual and physics drawables now share the common drawable shader group, with remapped material indices and inherited reader materials.

## [0.2.11] - 2026-07-25

### Added
- Public YDR bone-transform helpers provide consistent local composition, matrix multiplication, and absolute skeleton transforms.

### Fixed
- Material-less drawables now use a null shader-group pointer instead of emitting an empty runtime structure.
- YFT shared rest-pose matrices now preserve absolute bone transforms instead of writing identities.

## [0.2.10] - 2026-07-25

### Added
- Binary YFT validation reports invalid resource pointers, class headers, page maps, and physics-array dimensions before files are saved.
- Fragment drawable fixup validation covers shaders, skeletons, joints, models, geometries, buffers, and fragment-specific arrays.

### Fixed
- YFT physics structures now use runtime-compatible class headers and resource states.
- YFT group-name arrays reserve the sentinel slot required by the resource constructor.
- Multi-child props no longer receive an unrelated Euphoria articulated body automatically.
- Root fragment children now receive their required runtime header even when no physics LOD is present.
- Embedded YFT drawables now use the runtime class headers present in legacy breakable props without changing standalone YDR output.

## [0.2.9] - 2026-07-24

### Added
- Readable and writable `heightmap.dat` world-height grids with native quantization, row RLE, water masks, spatial queries, validation, and cache integration.

### Fixed
- Python 3.11 wheel imports no longer fail in native hash initialization.
- Slotted dataclass inheritance no longer relies on version-specific zero-argument `super()` behavior.
- YDR and YFT bounds now include rigid bone transformations.

## [0.2.8] - 2026-07-24

### Added
- Readable, writable, and declarative `water.xml` surfaces, calming regions, and wave regions, including game-aligned validation and `GameFileCache` integration.
- Geometry-oriented water constructors, named corner alphas, translation, aggregate bounds, bulk insertion, and point queries.

### Changed
- External corpus tests now resolve fixtures from the repository or `FIVEFURY_REFERENCE_DIR`.
- Optional Assimp colour-texture tests now skip cleanly when their optional image dependencies are unavailable.

### Fixed
- `GameFileCache` now closes RPF handles during eviction, clearing, and context-manager shutdown.
- Package metadata now declares the required NumPy runtime dependency.

## [0.2.7] - 2026-07-24

### Breaking Changes
- `Ydr.meshes` now returns meshes from every LOD; use `primary_meshes` for the previous first-populated-LOD behavior.
- YFT physics event slots now expose `YftEventSet` objects through `YftPhysicsChildEvents` and `YftPhysicsGroupEvents` instead of raw pointer containers.

### Added
- Structured binary models for `vehicles.meta`, `handling.meta`, `carcols.meta`, `carmodcols.meta`, and `carvariations.meta`.
- Readable and writable native light arrays on legacy YFT fragments.
- Readable, writable, and skeleton-derived YFT shared matrix sets.
- Readable and writable legacy YFT breakable panes and vehicle glass distance fields.
- Readable and writable legacy YFT environment cloth, including tuning, simulation bridges, morph maps, Verlet LODs, constraints, bounds, and user data.
- Readable and writable resource-backed YFT event sets for the empty continuous-event graphs used by legacy game assets.
- Structured YFT 1DOF and 3DOF articulated joints with writable orientations, limits, and muscle torques.
- PS3 CDR drawable reading, including PS3 resource pages, materials, shader mappings, QB geometry and compressed EDGE geometry.
- PS3 RPF7 reading support, including PS3 AES table decryption, endian-aware headers, name-shift handling, and cache indexing.
- RPF extraction conflict policies and explicit primary-LOD mesh accessors.
- Batched YDR skeleton bone insertion.
- Declarative MLO room, portal, entity, entity-set, and timecycle construction.
- MLO collision-room helpers and automatic YMF interior-bound entries.

### Changed
- YDR and CDR now share a format-neutral drawable model, LOD handling, material queries, parameter definitions, and shader catalog.
- Nested RPF archives are loaded on demand instead of during the initial archive parse.
- YDR skeleton lookups now use indexes rebuilt with the hierarchy.
- YTYP and YMAP writers now validate MLO graphs, synchronize portal counts, infer physics dictionaries, calculate transformed extents, and cross-check supplied YTYPs and YBNs.

### Fixed
- YNV writing now emits the required resource base metadata and page table, and packs split arrays and sector trees into valid RSC7 blocks.
- RSC7 layout now relocates packed 64-bit pointers aligned to 4-byte boundaries, including YNV sector-tree pointers.
- YNV validation now accepts two-vertex zero-area DLC stitch polygons used by game assets.
- YFT application user data is preserved as an opaque value instead of being treated as a resource pointer.
- YFT rebuilding now rejects unsupported event-player and character-cloth graphs instead of silently discarding them.
- Drawable writing now pads vertex channels to the component width declared by the original asset.
- YFT physics LODs now use the correct block sizes, resource-backed link transforms, root-child ownership, and relocated child drawable pointers.
- `GameFileCache` can now fall back to the Python RPF reader when the native archive scanner rejects a valid archive variant.
- RPF folder extraction now handles paths used as both files and directories.
- RPF folder creation now keeps stable absolute source paths, ignores dot-prefixed directories, and rejects offsets or name tables that cannot be represented by RPF7.
- Native hashing and crypto bindings now use size-safe Python argument parsing.
- MLO YTYP writing now includes nested entity structures, and META Vector3 arrays use their native 16-byte slots.
- YMAP box occluders now preserve their encoded orientation, rotated bounds, and minimum representable dimensions.
- CDR materials now resolve effect and preset hashes independently, including PS3-only shader names and parameters.

### Performance
- RPF saves now stream payloads through a seekable temporary file instead of retaining the complete archive twice in memory.
- RPFs created from folders defer reading file payloads until the archive is written.
- YDR collection bounds no longer flatten every mesh vertex into a temporary list.
- YDR and YFT validation avoid repeated linear searches.

## [0.2.6] - 2026-07-06

### Changed
- Project licensing is now declared as `CC0-1.0` and packaged with a `LICENSE` file.
- README now reflects the current YFT, YMF, YMT, GTXD/RBF, AWC, cache, and native-helper support more accurately.
- `RpfArchive` now keeps a cached read handle for its source file and gained `close()` and context-manager support; the `rpf_to_zip`/`rpf_to_folder` helpers close archives they open internally.
- RSC7 page packing and BVH construction are now provided solely by the native backend, removing the duplicated pure-Python implementations.

### Fixed
- The native crypto context now validates the AES key length before initializing the cipher, surfacing a clear error instead of a low-level BCrypt failure.

### Performance
- YDR drawable vertex buffers are now packed in the native backend, replacing the per-component Python encoder for roughly an order-of-magnitude speedup on large meshes.
- Collision generation now collects render triangles, computes triangle areas, and quantizes bound vertices in the native backend instead of one Python call per triangle or vertex.
- RSC7 pointer relocation now uses a sorted binary search over resource blocks instead of a linear scan for every pointer.
- Bounds now build their BVH a single time per shape rather than rebuilding it to recompute metrics.
- Octant construction no longer allocates temporary lists per vertex.
- Collision, GXT2, AWC, and REL readers now decode fixed-size tables with batched struct unpacking.
- `GameCrypto` now derives its AES cipher and NG subkeys lazily, avoiding setup work when only the native decryptor is used.

## [0.2.5] - 2026-05-11

### Added
- Basic YFT fragment reading and writing, including common, damaged, extra and cloth drawables, geometry, materials, LOD meshes, bounding sphere metadata, fragment flags, physics LODs, physics groups, physics children, child entity drawables, per-child breaking/inertia data, damping constants, damping archetypes, articulated body metadata, link attachments, group and child event references, editable composite bounds, mass/inertia helpers, glass/cloth/vehicle semantic queries, corpus scanning, validation, declarative physics helpers, geometry summaries, raw field inspection and cache decoding.
- YMT can now decode binary RBF and PSO containers, expose known `CMapParentTxds`, scenario manifest, scenario region, ped variation, ped metadata, and streaming request roots, and preserve raw RBF/PSO bytes for safe roundtrips.
- Generic RBF parsing helpers for binary metadata containers, including structures, attributes, primitive values, byte nodes, detection, and string-field extraction.
- GTXD can now read binary RBF `CMapParentTxds` data in addition to XML parent texture dictionary metadata.
- YMF now exposes `CPackFileMetaData` relationships for IMAP to ITYP dependencies, ITYP to ITYP dependencies, IMAP groups, interior bounds, and HD texture dictionary bindings.
- YMF manifests can now be generated from YMAP sets, resolving entity archetypes through explicit YTYP inputs or `GameFileCache`.
- `GameFileCache` now exposes convenience helpers for building YMF manifests from loaded or explicit YMAP sets.
- Shared vector and AABB helpers now cover common vector math used by bounds, YDR tangent generation, YND node distances, and YTYP LOD inference.
- Shared XML helpers now back DLC, GTXD, and YMF parsing/writing to avoid duplicated XML boilerplate.

### Changed
- Bounds now compute volume, center of gravity, volume distribution, and angular inertia for primitive and composite shapes during build.
- YDR mesh preparation now uses the shared vector helpers for normal and tangent generation.
- YND node distance and YTYP archetype radius inference now use the shared vector/AABB helpers.

## [0.2.4] - 2026-05-09

### Breaking Changes
- YMAP and YTYP extensions now live inside their owning format packages instead of a shared extension package.

### Added
- GTXD parent texture dictionary metadata support, including XML read/write, parent-chain lookup, duplicate handling, and cache loading.
- YND junction heightmap generation with game-aligned sample spacing, XY anchoring, and Z quantization.
- Initial YED expression dictionary support for reading, editing, validating, and writing spring-focused expression data.
- Radial skinning helpers for adding missing jiggle-bone weights to YDR and YDD meshes.
- Ped-variation helpers for editing component drawable metadata backed by generic YMT data.

### Changed
- YMAP code is now split by data type: base metadata, car generators, grass, lights, occluders, packing, timecycle modifiers, and extensions.
- YTYP code is now split by data type: asset types, base archetypes, timed archetypes, MLO data, and extensions.
- Texture lookup now respects GTXD parent chains and embedded resource texture dictionaries.
- Radial rigging now reuses existing ped-component bone palettes before appending new jiggle influences.

### Fixed
- YND junction heightmaps now encode minimum XY, 2.0-unit sample spacing, 1/32 Z bounds, and the correct 256-step decode range.

## [0.2.3] - 2026-05-06

### Added
- Declarative DLC metadata support for setup, content, DLC lists, title updates, change sets, and DLC patch overlays.
- High-level DLC pack and patch helpers for building folder-backed DLC packages and update overlays.
- Folder inference for DLC metadata, allowing a DLC directory to produce matching setup and content files.
- DLC list and title-update manifest helpers for pack registration and patch mounting.
- XML read/write support for the supported DLC metadata files.

### Changed
- README support tables and examples now cover DLC metadata, folder inference, and patch overlays.

## [0.2.2] - 2026-05-05

### Added
- Initial REL support with binary read/write, raw preservation for unknown records, and cache decoding.
- Typed REL coverage for synth presets, curves, audio categories, sound graphs, routing data, randomization, sound sets, hashes, and lookup tables.
- Audio conversion from WAV, MP3, OGG, and FLAC into PCM AWC, including mono and multichannel output.
- AWC helpers for PCM and WAV extraction from streams and dictionaries.
- Declarative YMAP component authoring for entities, physics dictionaries, occluders, LOD lights, car generators, timecycle modifiers, instanced data, and block descriptors.
- Declarative YTYP dependency and composite-entry authoring with build-time deduplication.

### Fixed
- Hex strings assigned to hashed cutscene fields now stay numeric instead of being hashed as text.

### Performance
- GameFileCache format views now reuse native kind buckets instead of rescanning every asset in Python.

## [0.2.1] - 2026-05-02

### Added
- Cutscene validation with structured errors before binary export.
- CSS-style color parsing shared across cutscenes, YDR lights, vertex colors, YMAP lights, bounds material colors, and light extensions.
- Native-backed magic-table decryption for encrypted game data.

### Changed
- CUT export validates authored scenes by default before writing bytes.
- CUT serialization now handles optional templates consistently.

### Fixed
- Cutscene validation now catches missing metadata, invalid duration, duplicate object IDs, missing streamed-object metadata, invalid event targets, unsafe camera clipping, missing camera cuts, and events outside the scene range.
- CUT writing without a template now rejects obviously incomplete scenes instead of producing unreadable files.
- Windows magic-table decryption no longer depends on the removed Python-only path.

## [0.2.0] - 2026-04-28

### Added
- High-level cutscene subtitle authoring, including subtitle events and optional GXT2 label dictionaries.
- Full known CUT event coverage for cutscene authoring.
- GXT2 localization table read/write/edit support.
- Initial AWC support with stream chunks, codec metadata, encryption helpers, PCM WAV helpers, and ADPCM decoding.
- Generic YMT and YMF support on top of the shared META/RSC7 layer.
- Shared helpers for byte loading, hash coercion, clip-name normalization, and flexible integer enums.

### Changed
- New CUT files now use more complete retail-style root defaults.
- Partial and final JOAAT hash helpers now use the native backend.
- AWC code is split into constants, crypto, conversion, binary I/O, and data models.
- Shared PSO reading and writing logic now backs CUT instead of duplicated format-local code.
- Repeated byte, hash, clip-name, enum, YDR parameter, YCD channel, and bounds math helpers were consolidated.
- GameFileCache kind filtering is now centralized and consistent across strings, extensions, integers, and enum values.
- Public exports were tightened to avoid broad internal reexports.
- Long skeletal and object cutscene clips now follow the vanilla sequence frame limit more consistently.
- Dead imports, wrappers, and redundant safeguards were removed across cache, crypto, CUT, YCD, YDD, YDR, YMAP, YND, YNV, and YTYP code.

### Fixed
- GameFileCache kind counts now report logical file types for extension-backed resources inside archives.
- Root package exports now include recently added high-level APIs.
- YDR reader compatibility with older Python syntax support was restored.
- Windows crypto tests now cover the expected AES decryptor path.
- Built-in CUT schema coverage now includes object-variation and particle-effect event arguments.

### Performance
- Cutscene hash-heavy paths now use the compiled native backend.
- RSC7 page assignment, pointer remapping, and section materialization now use native code.

## [0.1.48]

### Added
- Cutscene flag enums and defaults for sectioning, concat mode, playback, camera behavior, fades, DOF, and ambient suppression.
- Explicit CUT scene metadata for names, ranges, timing, camera cuts, section splits, offsets, trigger data, and concat records.
- Cutscene light enums and conversion from embedded YDR lights to cutscene light objects.
- Animation clip base support for cutscene props whose runtime animation name differs from the object handle.
- Long object and skeletal cutscene clip support in the high-level YCD cutscene builder.
- Static and quantized transform channels for high-level YCD object clips.
- YTYP helpers for marking generated archetypes as cutscene props.
- YTYP LOD inference helpers for generated archetypes.
- GameFileCache indexing for CUT, YCD, YND, and YNV resources inside archives.

### Changed
- CUT writing now defaults to playable root metadata and game-like load ordering.
- Initial animation events now start after the first camera tick when needed.
- Camera cut events and camera cut lists are handled separately.
- Streamed prop scenes now use the concat mode required by prop-heavy cutscenes.
- Scene names now stay in concat data during load events to preserve relocation behavior.
- Animated cutscene props now avoid forcing handles that should be resolved from the animation streaming base.
- Cutscene animation validation now checks clip bases, derived section names, cutscene names, and streaming-base hashes.
- YCD object and skeletal tracks now use stricter semantic ordering.
- Camera clips keep section splitting, while object and skeletal props remain in one sequence to avoid root-only playback.
- YDR skeletons now default to animatable transform flags and rebuild child flags automatically.
- YDR writing now recalculates skeleton hashes by default.
- YDR writing normalizes the root bone to the expected tag and remaps mesh palettes and joint limits.
- YDR skinned mesh export now validates palettes, blend indices, unknown bones, and skinned model flags.
- YTYP archetypes built from YDR folders now infer non-zero LOD distances.

### Fixed
- Generated cutscenes that loaded in tools but failed to show props in-game because root flags, concat mode, load order, offsets, face directory, or scene-name placement were wrong.
- Cutscene prop animation binding when object names differ from drawable or clip names.
- Long skinned/object YCD clips that only played root motion after being split incorrectly.
- Skinned YDR files with invalid root bone IDs, stale skeleton hashes, missing skinned flags, or palette mismatches.
- Generated YTYP archetypes with zero LOD distances.
- CUTXML file detection now resolves as unknown instead of CUT.

## [0.1.47]

### Added
- More cutscene scene objects and events, including decals, fixups, hidden-object visibility, and extra light/decal payloads.
- A dedicated cutscene YCD builder for camera and object clips.
- Declarative multi-bone object clips for animated props and articulated cutscene objects.

### Changed
- Cutscene prop authoring now uses clearer runtime-facing model, type, and animation metadata.
- Public exports now expose the expanded cutscene and YCD builder APIs.

## [0.1.46]

### Added
- YMAP enums for map flags, content flags, entity flags, MLO flags, car generator flags, LOD levels, priority levels, and LOD light metadata.
- YTYP timed-archetype flags as enums, with hour-mask and visibility helpers.

### Changed
- YMAP LOD light generation now normalizes paired near/far data and recalculates street-light counts.
- High-level LOD light authoring now accepts semantic angle, capsule, color, and corona values instead of raw packed bytes.

### Fixed
- YMAP validation now catches mismatched LOD light counts and invalid street-light partitions before writing.

## [0.1.45]

### Added
- YDR skeleton hash helpers and formal bone flag names for animated rigid skeletons.

### Changed
- YDR writing can recalculate skeleton hashes explicitly while preserving roundtrip behavior by default.

## [0.1.44]

### Fixed
- YCD object-track quantization metadata is now preserved instead of being recomputed as generic animation data.
- Object quaternion and transform clips keep their known-good bit layouts during export.
- Regression coverage now protects object-track quantization.

## [0.1.43]

### Fixed
- YCD export now derives the animation header hash field more defensively for rebuilt clips.
- UV clips keep their required special-case value.
- Object animations no longer serialize an empty header field in the authoring path.

## [0.1.42]

### Fixed
- YCD writer now sanitizes invalid non-UV quantized channels before packing sequence data.
- Skeletal and object sequences now rebuild with valid per-channel bit widths and smaller frame payloads.
- Regression coverage now protects against invalid skeletal sequence packing.

## [0.1.41]

### Fixed
- YCD skeletal exports now write the correct per-track format byte.
- Additional real skeletal track formats are now mapped during export preparation.
- High-level YCD authoring now derives bone-entry formats from track semantics.

## [0.1.40]

### Fixed
- YCD export now normalizes skeletal channel slot indices before serialization.
- YCD export now synchronizes animation bone tables from sequence bindings.
- High-level YCD builds now harden skeletal animations before writing.

## [0.1.39]

### Fixed
- YCD animation headers now write sequence block length and usage count into the correct fields.
- YCD animation usage counts now match animation-map ownership and clip references.
- YCD linear-float channels now write sign bits for non-zero deltas.
- Roundtrip tests now compare rebuilt files against fresh parses from real samples.

## [0.1.38]

### Added
- Static YDR shader enums for IDE autocomplete.
- Shader inspection helpers for render buckets, layouts, texture slots, and numeric parameters.
- Clearer high-level builders for box, disc, cylinder, and cloth bounds.

### Changed
- YDR material inputs now accept shader enum values.
- Shader inputs now infer canonical render buckets and normalize the specular sampler slot.
- YTYP archetype asset types now use enums instead of bare integers.
- Bounds header and primitive fields were renamed where their role is now understood.

## [0.1.37]

### Added
- BoundDisc, BoundCylinder, and BoundCloth support.
- Declarative BoundBox helpers and material enum support across bound types.
- Additional bound metadata preservation for simple primitive bounds.

### Changed
- Bound subclasses now own their shape-specific data instead of storing primitive fields on the base type.

## [0.1.36]

### Added
- High-level YDR helpers for skeletons, bones, skinning, embedded textures, embedded collisions, lights, and material editing.
- Declarative material, sampler, shader, and parameter editing helpers.
- Drawable model support for YDR files containing multiple models.

### Changed
- YDR high-level APIs now use explicit build and validation steps.
- Material editing is now model-aware instead of treating all materials as one implicit global list.

## [0.1.35]

### Added
- YDR light read/write support.
- High-level light authoring helpers for drawable lights.

### Fixed
- YDR files with embedded lights now preserve them during roundtrip.

## [0.1.34]

### Added
- YDR material-by-material editing for shaders, samplers, parameters, and render buckets.
- Embedded texture and embedded collision read/write support for YDR.

### Changed
- YDR material APIs are more declarative and less string-heavy.

## [0.1.33]

### Added
- YND area helpers and automatic node partitioning into pathfind regions.

### Changed
- YND validation now rejects nodes assigned to the wrong pathfind area while keeping world, navmesh, and pathfind limits distinct.

## [0.1.32]

### Added
- Native bounds backend for heavy geometry helpers, octant generation, and BVH construction.

### Changed
- Native bounds code was split into smaller C++ modules.

## [0.1.31]

### Added
- YDD read/write support for drawable dictionaries, hashed drawable entries, and embedded drawables.

## [0.1.30]

### Added
- Bounds geometry helpers for building BVH and composite collision bounds from triangles.
- YDR helpers for embedded collision bounds built from render geometry.

### Fixed
- RPF resource entries larger than the normal size field now store the true size correctly.

## [0.1.29]

### Fixed
- YBN common bound-header layout now matches the expected child-bound offsets.

## [0.1.28]

### Changed
- YBN normalization and validation now model composite children, triangle adjacency, and public composite flags more explicitly.

### Fixed
- Composite YBN BVHs are rebuilt from child bounds during export.
- Inverted bound boxes are normalized on read.
- YDR resource writing now keeps drawable-model and material blocks aligned with the expected RSC7 layout.

## [0.1.27]

### Changed
- RSC7 page-layout calculation is now shared by YBN, YDR, and YCD writers.
- META resource page counts now match the encoded resource flags.

### Fixed
- Generated YDR files no longer write mismatched page counts and fixup metadata.
- Generated and roundtripped YBN files no longer inherit stale root page metadata.
- YCD page metadata now follows the actual encoded resource layout.

## [0.1.26]

### Added
- YDR joint-limit read/write support for rotation and translation limits.
- Expanded real-reference YDR roundtrip coverage.

### Fixed
- Legacy YDR vertex declarations and vertex-buffer flags are preserved during roundtrip.
- Sparse UV-channel declarations no longer collapse intermediate texture coordinates.
- YDR vertices now encode by declared component type.
- Skinned YDR files with packed blend-index streams now parse and roundtrip correctly.

## [0.1.25]

### Fixed
- YBN writer no longer stalls on geometry-heavy generated bounds.
- Generated YBN files use a fast direct-flags path unless explicit root page metadata is present.

## [0.1.24]

### Fixed
- Generated standalone YBN resources now calculate RSC7 paging from bound-block sizes instead of raw byte length.
- Roundtripped YBN files preserve explicit root page counts.
- YBN system payload padding now matches the encoded resource flags.
- Regression coverage protects real YBN roundtrips against page-count drift.

## [0.1.23]

### Fixed
- Legacy YDR mesh buffers now live in system pages.
- Written legacy YDR roots now use the expected resource header marker.
- Regression coverage protects system-only legacy YDR output.

## [0.1.22]

### Fixed
- YBN serialization now writes a complete resource root instead of zeroed metadata.
- Additional bound-header fields are preserved during YBN roundtrip.
- Generated YBN page counts now match the encoded RSC7 flags.
- BVH bounding vectors now use the expected NaN marker components.

## [0.1.21]

### Added
- Generated octants for geometry bounds.
- Octant read/write support for YBN and embedded YDR bounds.

### Fixed
- META and RSC7 writing for YMAP and YTYP now preserves page layout, resource flags, and data-block packing.
- YTYP data-block grouping now matches larger real-world map-type files.

## [0.1.20]

### Fixed
- YDR drawable-model writing no longer overwrites render-mask data with geometry counts.
- Written model headers now preserve the repeated geometry count expected by the runtime.

## [0.1.19]

### Breaking Changes
- High-level authoring APIs were normalized around explicit collection edits, single-value setters, build steps, and validation steps.
- Several newer YDR helper names were renamed to follow the normalized high-level style.

### Added
- YCD writer support.
- Real YCD roundtrip coverage using sample clip dictionaries.

### Changed
- High-level YDR, YTD, YBN, bounds, YTYP, YMAP, and CUT authoring now share the same build and validation style.
- Tests and examples now use the normalized high-level API style.
- YCD parsing and evaluation now cover UV, object, camera, root-motion, and facial animation tracks.

## [0.1.18]

### Fixed
- Oversized but valid legacy YTD saves now use adaptive RSC7 page sizing.
- Shared RSC7 sizing logic now applies the same fix beyond YTD.

## [0.1.17]

### Added
- Real YDR skeleton support with bones, flags, lookup helpers, and skinned-drawable roundtrips.
- Declarative skeleton authoring helpers.
- Initial shared bounds and YBN support, including embedded YDR collisions, typed collision polygons, material names, and minimal geometry/BVH writing.

### Changed
- YDR LOD names now use enums instead of plain strings.
- Readers and builders now preserve full skeleton data.
- Shared resource, META, cache, CUT, and YDR helper layers were deduplicated.
- README now includes higher-level YMAP builder examples.

## [0.1.16]

### Added
- Declarative car generator builders with heading, body-color helpers, and safer defaults.
- Declarative timecycle modifier builders with center/size inputs and bounds-based creation.

### Changed
- YMAP high-level helpers now avoid forcing callers to work with raw extents and packed fields.

## [0.1.15]

### Added
- High-level YMAP occluder builders for boxes, faces, quads, and generated occlusion models.

### Changed
- Occluder authoring now auto-splits generated geometry when the encoded vertex budget would be exceeded.

## [0.1.14]

### Added
- Typed container LOD support for YMAP authoring.

### Changed
- YMAP code was split into smaller modules without changing the public API.
- OBJ to YDR conversion now returns build metadata, defaults output beside the source model, skips unused materials, and infers better shaders from material textures.

## [0.1.13]

### Added
- YTYP code was split into dedicated modules for archetypes, MLO data, flags, helpers, and models.
- More YTYP and MLO flag enums.
- Full YTYP extension coverage for known extension types.
- More enums for ladder, light shaft density, and light shaft volume extension data.

### Changed
- Shared offset-based binary read/write helpers now back YDR, YCD, embedded assets, and CUT PSO code.

### Fixed
- Primitive byte operations are now centralized, reducing endian handling drift between readers and writers.

## [0.1.12]

### Added
- Initial CUT and YCD animation integration helpers for authoring animation-manager events.

### Fixed
- CUT PSO inline-array handling used by animation payloads.

## [0.1.11]

### Added
- High-level CUT animation-manager helpers for loading animation dictionaries and setting or clearing object animation state.
- CUT helpers for attaching clip dictionaries and checking available clips.
- Animation validation helpers for checking clip targets against attached YCD data.

### Changed
- Template-free CUT authoring now includes typed animation payloads and timeline helpers.

### Fixed
- CUT PSO reader now handles inline fixed-size member arrays.
- Missing PSO block references now resolve to empty values instead of crashing.

## [0.1.10]

### Added
- YDR light parsing and editing support.
- Editable YDR material roundtrip support.

### Changed
- YDR writer now preserves light lists during roundtrip saves.
- YDR builder can author lights alongside drawable models.
- YDR material and light code was split into smaller modules.

## [0.1.9]

### Added
- Initial YCD reader support with clip dictionaries, animation metadata, and cutscene-oriented clip names.
- Initial CUT readers for binary and XML inputs.
- Template-free CUT writing with scene and timeline models.
- High-level CUT scene builder primitives and event specs.

### Changed
- CUT scene authoring now uses typed payloads.

## [0.1.8]

### Added
- YTYP merge support.
- Minimal YTYP generation from a folder of YDR files.

### Changed
- Top-level exports now cover more YDR builder and YTYP helper workflows.

### Fixed
- OBJ to YDR axis conversion now imports models upright.
- Companion YTYP generation now uses the correct drawable asset type.
- Sparse YDR UV-channel indices are preserved during parsing.

## [0.1.7]

### Added
- Optional companion YTYP generation for OBJ to YDR conversion.

### Changed
- Generated OBJ to YDR and companion YTYP names are now lowercased consistently.

## [0.1.6]

### Added
- XML-driven YDR material descriptors.
- Builder support for valid legacy YDR resources.

### Fixed
- OBJ texture V coordinates are flipped correctly during YDR import.

## [0.1.5]

### Added
- README coverage for RPF folder export, export modes, and encrypted standalone archive loading.

### Changed
- Published README now reflects the current RPF export behavior.

## [0.1.4]

### Added
- RPF folder export and folder import helpers.
- Explicit RPF export modes for stored, standalone, and logical output.
- Automatic default crypto initialization for encrypted standalone RPF loading.

### Changed
- RPF ZIP and folder export now share traversal behavior.
- Standalone export is now the default for folder and ZIP output.
- RPF export options now use an enum instead of a boolean-style flag.
- Core format modules were split into smaller domain packages.

### Fixed
- Folder extraction now preserves standalone resource containers by default.
- Nested RPF archives are preserved as directories during recursive export.

## [0.1.3]

### Changed
- More RPF point reads now use the native backend.
- Native binding code was split by domain.
- Archive table and payload decryption now use native crypto paths.
- GameFileCache was reorganized into smaller cache modules.
- Resource texture assets were split into per-format modules.
- README was refreshed around current cache, extraction, and texture workflows.

### Added
- Internal architecture documentation for codebase layout and backend boundaries.
- Lazy GameFileCache lookups, per-kind dictionaries, iteration helpers, and kind statistics.
- Helpers to extract all assets referenced by a YMAP.
- YTD texture extraction as DDS.
- Embedded texture extraction for YDR, YDD, YFT, and YPT assets.
- Resource-asset abstractions for embedded-texture traversal.

### Fixed
- Resource extraction now writes valid standalone resources by default.
- Dead and duplicated scan helpers were removed after the cache refactor.
- Python and native RPF decryption paths are less likely to diverge.

### Performance
- Archive table decryption and point reads now do less Python-side work.
- Batched native archive reads reduce duplicate entry resolution.
- Native JOAAT hashing and hash-value caching reduce repeated hash work.
- Performance benchmarks were added for native and Python paths.
- GameFileCache archive scanning moved further into native code.

## [0.1.2]

### Changed
- GameFileCache was reorganized into smaller cache modules.
- Resource texture assets were split into per-format modules.
- README was refreshed around current cache, extraction, and texture workflows.

### Added
- Internal architecture documentation for codebase layout and backend boundaries.
- Lazy GameFileCache lookups, per-kind dictionaries, iteration helpers, and kind statistics.
- Helpers to extract all assets referenced by a YMAP.

### Fixed
- Resource extraction now writes valid standalone resources by default.

## [0.1.1]

### Added
- YTD texture extraction as DDS.
- Embedded texture extraction for YDR, YDD, YFT, and YPT assets.
- Resource-asset abstractions for embedded-texture traversal.

### Changed
- GameFileCache can now resolve texture dictionaries using YTYP data and GTXD parent relationships.
- README now includes texture-extraction workflows for YTD and embedded resources.

## [0.1.0]

### Added
- Initial public release of fivefury.
- Native GameFileCache scanning for GTA V RPF archives with DLC filtering, exclusions, and type-aware lookups.
- YMAP and YTYP creation, parsing, and saving APIs.
- Global hash-resolution utilities and MetaHash support.
- Core YTD handling and GTA V asset workflow helpers for Python 3.11+ on Windows.
