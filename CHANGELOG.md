# Changelog

All notable changes to `fivefury` are documented in this file.

The changelog is release-oriented and uses a small fixed set of categories:
`Breaking Changes`, `Added`, `Changed`, `Fixed`, and `Performance`.

## [Unreleased]

### Changed
- Project licensing is now declared as `CC0-1.0` and packaged with a `LICENSE` file.
- README now reflects the current YFT, YMF, YMT, GTXD/RBF, AWC, cache, and native-helper support more accurately.

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
- CUT to CutScript export with hash resolution from known names and sibling files.
- CutScript declarations for static props, animated props, peds, vehicles, camera quaternions, type files, animation bases, and raw flags.
- Declarative YMAP component authoring for entities, physics dictionaries, occluders, LOD lights, car generators, timecycle modifiers, instanced data, and block descriptors.
- Declarative YTYP dependency and composite-entry authoring with build-time deduplication.

### Changed
- CUT decompilation now emits a readable script instead of a noisy dump of internal fields.
- CutScript keeps unresolved hashes readable while preserving their numeric value.
- Streamed model declarations now separate loaded model name, cutscene binding name, animation base, and type file.

### Fixed
- Hex strings assigned to hashed cutscene fields now stay numeric instead of being hashed as text.
- CUT roundtrips now preserve camera quaternions, raw flags, load events, animation events, object events, light events, subtitle events, audio events, and animated/static model intent.

### Performance
- GameFileCache format views now reuse native kind buckets instead of rescanning every asset in Python.

## [0.2.1] - 2026-05-02

### Added
- Initial CutScript DSL for authoring CUT files from readable timeline scripts.
- CutScript asset declarations for managers, cameras, props, peds, vehicles, lights, audio, subtitles, fades, overlays, and decals.
- CutScript timeline commands for loading, camera cuts, draw distance, animation binding, visibility, attachments, fades, overlays, lights, subtitles, audio, and cleanup.
- Multiline CutScript blocks with explicit section endings.
- Cutscene validation with structured errors before binary export.
- CSS-style color parsing shared across cutscenes, YDR lights, vertex colors, YMAP lights, bounds material colors, and light extensions.
- Native-backed magic-table decryption for encrypted game data.

### Changed
- CUT export validates authored scenes by default before writing bytes.
- CUT serialization now handles optional templates consistently.
- CutScript examples now match the multiline syntax accepted by the parser.
- Local VS Code CutScript tooling is kept outside the Python package.

### Fixed
- Cutscene validation now catches missing metadata, invalid duration, duplicate object IDs, missing streamed-object metadata, invalid event targets, unsafe camera clipping, missing camera cuts, and events outside the scene range.
- CUT writing without a template now rejects obviously incomplete scenes instead of producing unreadable files.
- CutScript no longer treats CSS hex colors as comments.
- CutScript errors now include concrete line numbers.
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
