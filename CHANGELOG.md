# Changelog

All notable changes to `fivefury` are documented in this file.

The changelog is release-oriented and uses a small fixed set of categories:
`Breaking Changes`, `Added`, `Changed`, `Fixed`, and `Performance`.

## [Unreleased]

## [0.1.48]

### Added
- `CutSceneFlags`, `DEFAULT_PLAYABLE_CUTSCENE_FLAGS`, and pack/unpack helpers for `.cut` flag arrays, covering sectioning, concat mode, story-mode playback, camera interpolation, DOF, fades, and ambient/vehicle-light suppression.
- Explicit `.cut` scene metadata fields for scene names, ranges, section timing, camera-cut lists, section split lists, relocation offsets, trigger offsets, and concat-data records.
- `CutLightType`, `CutLightProperty`, and `CutLightFlag` enums for cutscene light objects, replacing raw integer flag authoring.
- `CutScene.ensure_ydr_embedded_lights(...)` for materializing embedded `YDR` lights as real `cutfLightObject` entries with matching `SET_LIGHT` events.
- `YdrLight` to cutscene-light conversion helpers that preserve compatible type, shadow, volume, reflection, alpha, colour, intensity, falloff, cone, corona, and hour-mask data.
- `animation_clip_base` on cutscene prop bindings, allowing `.cut` animation targets to resolve clips by the drawable/model clip basename instead of the object handle name.
- `YCD_CUTSCENE_SEQUENCE_FRAME_LIMIT` export and long object/skeletal cutscene clip support in the high-level `YCD` cutscene builder.
- Static vector/quaternion channels and quantized transform channels for high-level `YCD` cutscene object clips, reducing invalid raw-float output for object, mover, and bone tracks.
- Cutscene-prop `YTYP` helpers: `cutscene_prop_flags(...)`, `mark_cutscene_prop_archetypes(...)`, `CUTSCENE_STATIC_PROP_ARCHETYPE_FLAGS`, and `CUTSCENE_ANIMATED_PROP_ARCHETYPE_FLAGS`.
- `YTYP` LOD inference helpers: `infer_archetype_radius`, `infer_archetype_lod_dist`, `infer_archetype_hd_texture_dist`, and the default/radius-scale constants used by generated archetypes.
- Explicit `GameFileCache` indexing for `.cut`, `.ycd`, `.ynd`, and `.ynv` resources inside `RPF` archives.
- Public exports for the new cutscene, YCD, YDR skeleton, and YTYP helper APIs from `fivefury`, `fivefury.cut`, `fivefury.cut.scene`, `fivefury.ycd`, `fivefury.ydr`, and `fivefury.ytyp`.

### Changed
- Cutscene writing now defaults to playable root metadata: a real face directory, range bounds, section duration, concat-data entries, scene offsets, trigger offsets, and default cutscene flags.
- Cutscene writing now keeps `LOAD_SCENE`, model loads, and animation dictionary loads in game-like order, and delays initial `SET_ANIM` events one frame when they would otherwise start on the same tick as the first camera cut.
- Cutscene writing now treats camera cut events and `cameraCutList` separately, so one-section cuts can contain camera events without accidentally enabling `SECTION_BY_CAMERA_CUTS`.
- Cutscene writing now switches streamed prop scenes from internal concat to external concat, matching the runtime path needed by prop-heavy cutscenes.
- Cutscene `LOAD_SCENE` event args now keep the scene name in concat data and leave the event `cName` empty, preserving relocation semantics used by retail cutfiles.
- Animated cutscene prop objects now leave `cHandle` empty when the runtime should resolve the handle from `AnimStreamingBase`, avoiding object-animation binding failures caused by forcing `cHandle = cName`.
- Cutscene animation validation now checks `animation_clip_base`, derived `<clip>-<section>` names, `cutscene_name`, and `AnimStreamingBase` hashes, and warns when the streaming base does not match the expected JOAAT partial hash.
- `YCD` object/skeletal cutscene tracks are now sorted by semantic track type and bone id, matching the stricter runtime ordering used by game cutscene dictionaries.
- `YCD` cutscene cameras keep section splitting with the 287-frame sequence limit, while object/skeletal props are kept in a single sequence to avoid the runtime applying only root motion on skinned props.
- `YCD` animation classification now treats mover and facial tracks as skeletal/object-style animation tracks when deriving runtime metadata such as `Unknown1C`.
- `YDR` skeleton bones now default to animatable transform flags, formally expose `HAS_CHILD` and `IS_SKINNED`, and automatically rebuild `HAS_CHILD` flags during skeleton construction.
- `YDR` writing now recalculates skeleton hash fields by default and still allows opting out with `recalculate_skeleton_hashes=False`.
- `YDR` writing now normalizes the root bone tag to `0` and remaps mesh palettes and joint limits accordingly, matching the root-bone convention required by cutscene/skinned-object workflows.
- `YDR` skinned mesh preparation now normalizes bone palettes against the skeleton, remaps blend indices to skeleton bone indices, rejects unknown bone ids/tags, and sets the skinned model flag automatically while preserving existing model flags.
- `YDR` skinned blend indices now use the packed colour byte order expected by the drawable vertex layout.
- `YTYP` archetypes built from YDR folders now infer non-zero `lodDist` and `hdTextureDist` from drawable bounds and can optionally mark generated archetypes as cutscene props.

### Fixed
- Generated cutscenes that could start in viewers but fail to show runtime props in-game because the root flags, concat mode, load order, offsets, face directory, or scene-name placement did not match the runtime path.
- Cutscene prop animation binding when the `.cut` object name differs from the drawable/YCD clip basename, which previously caused only root motion or no animation to play.
- Skinned/object cutscene `YCD` output where splitting long non-camera clips into multiple sequences produced parseable files that the game applied incorrectly.
- `YDR` skinned drawables with non-zero root bone ids, stale skeleton hashes, missing skinned model flags, or palette/tag mismatches that could import in tools but fail to animate correctly.
- Generated `YTYP` archetypes with zero LOD distances that made props disappear or become nearly invisible when streamed.
- `.cutxml` file-type detection; it now resolves to `UNKNOWN` instead of `CUT`.

## [0.1.47]

### Added
- `.cut` high-level authoring now covers additional real-world scene objects and events, including decals, fixup objects, hidden-object visibility control, extra light/decal payloads, and more explicit runtime-source helpers for cutscene props.
- `YCD` now exposes a dedicated cutscene builder that can derive section files from camera-cut timings, generate sectioned clip dictionaries directly, and author camera/object clips without manually assembling low-level track tables.
- The cutscene `YCD` builder now supports multi-bone object clips declaratively, so animated props and other articulated cutscene assets can be authored with per-bone transforms plus root-motion tracks from a single high-level input structure.

### Changed
- Cutscene prop authoring now uses clearer runtime-facing semantics around model names, type sources, and animation presets, making it easier to build `.cut` props from loose `YDR`/`YTYP` assets instead of hand-filling obscure fields.
- Public exports were updated so the new cutscene `YCD` builder types and the expanded `.cut` helpers are available directly from `fivefury`.

## [0.1.46]

### Added
- `YMAP` now exposes typed enums for map flags, content flags, entity flags, MLO instance flags, car generator flags, `LOD` levels, priority levels, and `LOD light` categories/types on the high-level API.
- `YTYP` time archetypes now expose `TimeArchetypeFlags` as a real enum instead of a bare integer and provide helpers for hour masks and `flip_while_visible`.

### Changed
- `YMAP` `LOD lights` generation now normalizes paired `LODLightsSOA` and `DistantLODLightsSOA` data before writing, ensuring street lights occupy the leading prefix required by the runtime and automatically recalculating `numStreetLights`.
- High-level `YMAP` `LOD light` authoring now accepts semantic angle, capsule, color, and corona-intensity inputs and packs them into the byte ranges used by the game instead of forcing callers to provide raw packed values.

### Fixed
- `YMAP` validation and build paths now catch mismatched `LODLightsSOA`/`DistantLODLightsSOA` counts and invalid street-light partitioning before serialization, reducing malformed `LOD light` outputs.

## [0.1.45]

### Added
- `YDR` skeleton hash helpers now expose the formal bone-flag names as enums and can calculate the `unknown_50h`, `unknown_54h`, and `unknown_58h` fields required by some animated rigid skeletons.

### Changed
- `YDR` writing can explicitly recalculate skeleton hashes via `recalculate_skeleton_hashes=True` while keeping the default roundtrip path preservative.

## [0.1.44]

### Fixed
- `YCD` object-track `QuantizeFloat` channels now keep their existing quantization metadata during export instead of being sanitized and recomputed like generic tracks, preventing valid object quaternion/object transform clips from collapsing from `17/18` bit layouts down to `16` bits.
- `YCD` export no longer applies the non-UV quantization sanitizer to object tracks, matching the workaround previously required by downstream tools and preserving known-good object animation ranges more faithfully.
- Added regression coverage for object-track quantization so future writer changes cannot silently reintroduce the metadata collapse seen in converted `good`/`bad` binary comparisons.

## [0.1.43]

### Fixed
- `YCD` export preparation now derives `Unknown1C` more defensively for rebuilt animation clips, preserving existing values, forcing the known runtime constant for UV clips, and only applying the observed `hash + 1` fallback to object/skeletal `{0,1}` track sets when the field would otherwise be empty.
- Added regression coverage for `Unknown1C` derivation so rebuilt UV clips keep the expected special-case value and rebuilt object animations no longer serialize an empty field in the authoring path.

## [0.1.42]

### Fixed
- `YCD` writer now sanitizes invalid non-UV `QuantizeFloat` channels before packing sequence data, preventing skeletal and object animation channels from overflowing into 17+ bit payloads when source quantization steps are too small.
- Rewritten skeletal/object `YCD` sequences now rebuild with valid per-channel bit widths and smaller frame payloads, matching the structure of known-good files more closely and avoiding the malformed sequence blocks seen in crashing converted clip dictionaries.
- Added regression coverage for quantized non-UV channel overflow so future writer changes cannot silently reintroduce invalid skeletal sequence packing.

## [0.1.41]

### Fixed
- `YCD` animation bone entries now write the correct per-track format byte instead of treating that field as an opaque unknown, aligning skeletal exports with the layout expected by downstream XML tooling and the game runtime.
- `YCD` track-format mapping now covers additional real sample tracks encountered in skeletal clip dictionaries, preventing fallback guesses during export preparation.
- High-level `YCD` authoring now auto-derives bone-entry formats from track semantics, so skeletal animations built from scratch no longer emit `BoneRotation` entries with an invalid vector format.

## [0.1.40]

### Fixed
- `YCD` export preparation now normalizes skeletal channel slot indices before serialization, preventing malformed component layouts when animations are built from high-level objects instead of reparsed samples.
- `YCD` export preparation now derives and synchronizes animation `bone_ids` from sequence bindings, so skeletal animations no longer depend on callers manually keeping bone tables in sync with sequence data.
- `YCD` high-level `build()` now hardens skeletal animations before writing, making the authoring path behave more like the validated roundtrip path used by parsed sample files.

## [0.1.39]

### Fixed
- `YCD` animation headers now write `MaxSeqBlockLength` and `UsageCount` into correct fields instead of shifting later header values during export.
- `YCD` animation usage counting now matches actual animation-map ownership and clip references, avoiding malformed rebuilt animation metadata.
- `YCD` `LinearFloat` channel encoding now writes sign bits for every non-zero delta, matching reader expectations and preserving non-UV animation channels through roundtrip export.
- `YCD` roundtrip tests now compare rebuilt files against fresh parses from real samples instead of reusing mutated in-memory objects, catching writer corruption that previous tests masked.

## [0.1.38]

### Added
- Static `YdrShader` `.sps` enums generated from the shader XML, so IDEs can autocomplete known drawable shader-file variants directly.
- Shader inspection helpers: `get_ydr_shader_info`, `format_ydr_shader_info`, and `print_ydr_shader_info`, exposing render buckets, layouts, texture slots, and numeric parameters without reading `Shaders.xml` by hand.
- Clearer high-level bounds helpers for `BoundBox`, `BoundDisc`, `BoundCylinder`, and `BoundCloth`, including declarative primitive builders, aliases, and collision-material enums on the public API.

### Changed
- `YDR` material inputs now accept `YdrShader` enum values in addition to raw strings.
- Shader-file inputs now infer their canonical render bucket automatically, and `SpecularSampler` is normalized to the real shader slot name `SpecSampler`.
- `YTYP` archetype definitions now expose `asset_type` as the typed `ArchetypeAssetType` enum on the high-level API instead of a bare integer.
- Bounds common-header fields and primitive metadata were renamed away from generic `unknown_*` and `reserved_*` placeholders where their storage role is now understood, improving authoring clarity without changing the binary layout.

## [0.1.37]

### Fixed
- Canonical skinned `YDR` vertex-declaration typing for `BLEND_INDICES`, exporting the field with the packed colour layout expected by real drawable resources instead of an invalid `UBYTE4` declaration.
- Explicit rigid bone-binding support for non-skinned drawable models attached to skeleton bones, matching animated-prop layouts that use a skeleton without per-vertex skinning.

## [0.1.36]

### Changed
- Correct archetype-flag naming and bit mapping for `YTYP`, so `CBaseArchetypeDef.flags` reflects actual archetype load flags instead of an unrelated entity-style flag set.
- Removal of internal source-tree references from public library strings and documentation where they did not belong.

## [0.1.35]

### Changed
- `YCD` UV animation semantics aligned with runtime slot bindings: UV clip names and hashes now derive from `<object>_uv_<slot_index>` and `MetaHash(object) + slot_index + 1`, with explicit validation during export.
- `YDR` helpers for exposing material slot indices and deriving matching `YCD` UV clip bindings, names, and hashes directly from drawable materials and models.

## [0.1.34]

### Changed
- `YCD` sequence writing rebuilt from parsed high-level channels and sequences instead of preserved raw sequence blobs.
- Oversized `fivefury.ycd.sequences` implementation split into smaller track, channel, and codec modules while keeping the public import surface stable.

## [0.1.33]

### Added
- `YND` area helpers and `YndNetwork` partitioning, so high-level node graphs can be split into pathfind regions automatically.

### Changed
- Stricter `YND` final-resource validation, so a single `Ynd` rejects nodes whose coordinates belong to a different pathfind area while keeping pathfind representation limits (`WORLDLIMITS_REP_*`) distinct from global world and navmesh limits.

## [0.1.32]

### Added
- Native `bounds` backend for hot geometry helpers, octant generation, and BVH construction used by `YBN` and embedded-collision workflows.

### Changed
- Native `bounds` backend split into smaller C++ modules, keeping the binding layer easier to maintain.

## [0.1.31]

### Added
- `YDD` read/write support for drawable dictionaries, including hash/drawable pairing and embedded drawable handling through the shared `YDR` reader and writer.

## [0.1.30]

### Added
- Generic bounds geometry helpers for building `GeometryBVH` and `BoundComposite` collision bounds from triangle lists.
- `YDR` convenience helpers for building and attaching embedded collision bounds from render geometry.

### Fixed
- `RPF` resource writing for large `RSC7` entries, using the `0xFFFFFF` sentinel and storing the true size in the resource header.

## [0.1.29]

### Fixed
- Shared `phBound` common-header layout in `YBN` bounds read/write, so generated collision resources align with the proper header structure instead of serializing child bounds at the wrong offsets.

## [0.1.28]

### Changed
- Tighter `YBN` bounds normalization and validation, with more explicit modeling of composite child bounds, triangle-adjacency data, and public composite flags at the high-level API.

### Fixed
- Composite `YBN` BVHs rebuilt from child bounds during export, plus normalization of inverted bound boxes on read to reduce drift against real collision resources.
- Hardened `YDR` resource writing around drawable-model and material block layout so generated resources stay aligned with the expected `RSC7` page structure.

## [0.1.27]

### Changed
- Unified `RSC7` page-layout flag calculation across `YBN`, `YDR`, and `YCD` writers using a proper block-packing strategy.
- `META` resource `pages_info` counts aligned with the page counts encoded by the written resource flags.

### Fixed
- Generated `YDR` files with mismatched `ResourcePagesInfo` page counts versus the `RSC7` header, which could produce invalid virtual-page and fixup metadata.
- Generated and roundtripped `YBN` files with stale root `pages_info` metadata inherited from bad source files.
- `YCD` `pages_info` metadata sizing and writing based on the actual encoded resource page layout instead of a fixed single-page placeholder.

## [0.1.26]

### Added
- `YDR` joint-limit read/write support with `YdrJoints`, rotation limits, translation limits, and high-level helpers for attaching joints to drawables.
- Expanded real-reference `YDR` roundtrip coverage for the larger `references/ydrs` sample set.

### Fixed
- Preservation of legacy `YDR` vertex declarations and vertex-buffer flags during roundtrip instead of rebuilding every mesh through a simplified declaration.
- Sparse UV-channel handling for declarations using higher UV slots without all intermediate channels, avoiding collapsed or corrupted texture-coordinate streams.
- `YDR` vertex encoding by declared component type, including half-float and packed-byte formats, instead of writing every vector-like value as `float32`.
- Skinned `YDR` parsing and roundtrip for packed blend-index streams that use the legacy `COLOUR` component type.

## [0.1.25]

### Fixed
- `YBN` writer stall when exporting generated bounds from geometry-heavy inputs.
- Preservation of the improved page-count path for valid source `YBN` files while restoring a fast direct-flags path for generated collision resources without explicit root page metadata.

## [0.1.24]

### Fixed
- `YBN` resource paging for generated standalone collision resources, so `RSC7` flags are no longer derived only from raw byte length.
- Page-flag calculation from real bound-block sizes, with preservation of explicit root `ResourcePagesInfo.system_pages_count` during roundtrip of valid `YBN` files.
- `YBN` system-payload padding to the exact size encoded by the written `RSC7` flags, preventing mismatches between root `pages_info` metadata and actual packed resource layout.
- Regression coverage keeping real `YBN` roundtrips aligned with the page-count metadata found in working collision resources.

## [0.1.23]

### Fixed
- Legacy `YDR` mesh-buffer serialization so vertex data now lives in `system` pages instead of `graphics` pages.
- Written legacy `YDR` roots now use `FileUnknown = 'HCLA'`, matching working resource headers instead of the older generic value.
- Regression coverage for system-only legacy `YDR` output and real-file roundtrips against working samples.

## [0.1.22]

### Fixed
- `YBN` bounds serialization now writes a real `ResourceFileBase` root, including `FileVFT`, `FileUnknown`, and `ResourcePagesInfo`, instead of emitting zeroed root metadata.
- Preservation of additional bound-header fields during `YBN` read/write roundtrip, including previously ignored common bound fields and the root `pages_info` block.
- Generated `YBN` root page counts aligned with the encoded `RSC7` system flags, avoiding empty or inconsistent `pages_info` headers on large collision resources.
- `BoundBVH` writing now emits `NaN` W components in the BVH bounding vectors, matching the layout used by working resources.

## [0.1.21]

### Added
- Generated octants for `BoundGeometry`, plus roundtrip octant read/write support for `YBN` and embedded `YDR` bounds.

### Fixed
- `META` and `RSC7` writing for `YMAP` and `YTYP`, preserving the page-based system layout, resource flags, and `DataBlock` packing used by working game files.
- `MetaBuilder` block grouping aligned with the larger `CMapTypes` `DataBlock` layout seen in real `YTYP` files.

## [0.1.20]

### Fixed
- `YDR` `DrawableModel` writing so the render-mask word no longer overwrites `GeometriesCount3`.
- Restoration of the repeated geometry count in written model headers to match the structure expected by the runtime.

## [0.1.19]

### Breaking Changes
- High-level authoring API normalized around `add_*` for collections, `set_*` for single assignments, plus `build()` and `validate()` as the preferred normalization and validation steps.
- Newer high-level `YDR` helpers renamed to match that convention:
  - `create_bone(...)` -> `add_bone(...)`
  - `embed_texture(...)` -> `add_embedded_texture(...)`
  - `unembed_texture(...)` -> `remove_embedded_texture(...)`
  - `use_bound(...)` -> `set_bound(...)`
  - `skin_model(...)` -> `set_model_skin(...)`
  - `YdrModel.enable_skin(...)` -> `YdrModel.set_skin_binding(...)`
  - `YdrModel.disable_skin(...)` -> `YdrModel.clear_skin_binding(...)`

### Added
- `YCD` writer support through `build_ycd_bytes(...)`, `save_ycd(...)`, `Ycd.to_bytes()`, and `Ycd.save(...)`.
- Real `YCD` roundtrip coverage against the clip dictionaries in `references/ycd`.

### Changed
- Standardized `build()` and `validate()` entry points across higher-level `YDR`, `YTD`, `YBN`, `bounds`, `YTYP`, `YMAP`, and `CUT` authoring surfaces.
- Test suite and high-level examples updated to the normalized API style instead of the older mixed naming scheme.
- `YCD` parsing and evaluation expanded with formal track names plus UV, object, camera, root-motion, and facial-animation support.

## [0.1.18]

### Fixed
- Adaptive `RSC7` page sizing for oversized but valid legacy `YTD` saves.
- Shared `RSC7` resource-layer sizing logic so the same fix applies beyond `YTD`.

## [0.1.17]

### Added
- Real `YDR` skeleton support with `YdrSkeleton`, `YdrBone`, `YdrBoneFlags`, bone lookup helpers, and skinned-drawable roundtrip support.
- Declarative skeleton helpers including `YdrSkeleton.create()`, `add_bone(...)`, `Ydr.ensure_skeleton()`, `Ydr.add_bone(...)`, and `calculate_bone_tag(...)`.
- Initial shared bounds and `YBN` support, including embedded `YDR` collisions, decoded typed collision polygons, material-name helpers, and minimal `YBN` geometry/BVH writing.

### Changed
- `YDR` LOD names now use the `YdrLod` enum instead of plain strings on the main API surface.
- Readers and builders now preserve full skeleton data instead of only blend weights, blend indices, and skin-binding flags.
- Shared resource, `META`, cache, `CUT`, and `YDR` helper layers deduplicated to reduce repeated logic across formats.
- README updated with higher-level `YMAP` builder examples.

## [0.1.16]

### Added
- Declarative `CarGen` builders with heading, body-color helpers, and higher-level defaults that fit the rest of the `YMAP` authoring API.
- Declarative `TimeCycleModifier` builders using center/size-style inputs, plus helpers to create modifiers from either explicit dimensions or existing bounds.

### Changed
- `YMAP` high-level helpers now expose more ergonomic `car_gen(...)` and `time_cycle_modifier(...)` creation paths instead of requiring callers to work directly against raw extents and packed fields.

## [0.1.15]

### Added
- High-level occluder builders for `YMAP`, including `BoxOccluder` creation from world-space position and size plus `OccludeModel` builders from faces, boxes, and quads.

### Changed
- Occlude-model authoring now auto-splits generated geometry when the encoded occluder vertex budget would be exceeded, making the high-level API safer for larger source meshes.

## [0.1.14]

### Added
- Typed `ContainerLodDef` support plus a `Ymap.container_lod()` helper for authoring container-LOD metadata directly from the high-level API.

### Changed
- `ymap` implementation split into smaller package modules while keeping the public import surface stable.
- `obj_to_ydr(...)` now returns the built `YdrBuild`, defaults its output beside the source `.obj`, skips unused materials during import, and infers more appropriate drawable shaders from normal and specular texture slots in the source material data.

## [0.1.13]

### Added
- `YTYP` package split into dedicated modules for archetypes, MLO, flags, helpers, and model.
- Flag enums for `EntityFlags`, `MloInstanceFlags`, `MloInteriorFlags`, `PortalFlags`, and `RoomFlags`.
- Complete `YTYP` extension support via `META_NAME_MAP` entries for all fourteen extension types and their fields.
- Extension enums for `CExtensionDefLadderMaterialType`, `CExtensionDefLightShaftDensityType`, and `CExtensionDefLightShaftVolumeType`.

### Changed
- Shared offset-based binary read and write helpers consolidated into `fivefury.binary`, with `YDR`, `YCD`, embedded-asset, and `CUT` PSO modules moved to the shared primitives.

### Fixed
- Reduced drift risk between little-endian resource readers and big-endian `CUT` PSO helpers by centralizing primitive byte operations.

## [0.1.12]

### Added
- Initial `CUT` and `YCD` animation-integration helpers for authoring animation-manager events without editing raw PSO nodes directly.

### Fixed
- `CUT` PSO inline-array handling used by the animation path.

## [0.1.11]

### Added
- High-level `CUT` animation-manager authoring helpers for loading animation dictionaries and binding or clearing animation state on scene objects.
- `CutScene.play_animation(...)` orchestration over `load_anim_dict` and `set_anim`, with optional cleanup support.
- `YCD` clip-dictionary association helpers on `CutScene`: `attach_clip_dict`, `get_clip`, `get_animation`, and `available_clips`.
- `validate_animations` helpers for checking referenced animation dictionaries and clip targets against attached `YCD` data.

### Changed
- Template-free `CUT` authoring now includes typed animation payloads and timeline helpers around the animation-manager path.

### Fixed
- PSO reader handling for inline subtype-4 (`MEMBER`) arrays, avoiding `KeyError` crashes on `.cut` files with inline fixed-size arrays such as `BlockingBounds`.
- Robust PSO block lookups so missing block references return empty values instead of crashing.

## [0.1.10]

### Added
- `YDR` light support with parsed drawable light attributes exposed as `ydr.lights`, plus `YdrLight` and `YdrLightType`.
- Editable `YDR` material roundtrip support for higher-level material workflows.

### Changed
- `YDR` writer now preserves light lists during roundtrip saves.
- `YDR` builder keeps the newer models-first structure while allowing lights to be authored from `YdrBuild` and `create_ydr(...)`.
- `YDR` material and light read/write helpers split into smaller modules.

## [0.1.9]

### Added
- Initial `YCD` reader support with `read_ycd(...)`, clip-dictionary parsing, animation metadata, and cutscene-oriented clip-name mapping.
- Initial `CUT` readers for both PSO-based `CUT` and `CUTXML` inputs.
- Template-free `CUT` writing through a scene-layer and timeline model, plus builtin schema fallback support.
- High-level `CUT` scene builder primitives and event specs for from-scratch cutscene authoring.

### Changed
- `CUT` scene authoring API refined around typed payloads.

## [0.1.8]

### Added
- `merge_ytyps(...)` for combining multiple `YTYP` files, including directory-based merges.
- `ytyp_from_ydr_folder(...)` for generating a minimal `YTYP` from a folder of `YDR` files.

### Changed
- Expanded top-level exports for the `YDR` builder and `YTYP` helper workflows.

### Fixed
- `OBJ -> YDR` axis conversion, so imported models no longer come out laid down.
- Companion `YTYP` generation, so the archetype uses `ASSET_TYPE_DRAWABLE` instead of `ASSET_TYPE_DRAWABLEDICTIONARY`.
- Sparse `YDR` UV-channel indices preserved during parsing instead of being compacted.

## [0.1.7]

### Added
- Optional companion `YTYP` generation for `OBJ -> YDR`, with `textureDictionary` set to `<model>_txd`.

### Changed
- Lowercased generated `OBJ -> YDR` and companion `YTYP` names so output files and archetype-derived names stay consistent.

## [0.1.6]

### Added
- XML-driven `YDR` material descriptors.
- Builder support for writing valid legacy `YDR` resources.

### Fixed
- Flipped OBJ `V` texture coordinates during `OBJ -> YDR` import so generated drawables no longer come out with vertically inverted UVs.

## [0.1.5]

### Added
- README coverage for `RPF -> folder` workflows, `RpfExportMode`, and direct loading of encrypted standalone `.rpf` archives.

### Changed
- Published package README refreshed so the PyPI page reflects the current `RPF` export API and standalone-archive behavior.

## [0.1.4]

### Added
- `RpfArchive.to_folder(...)`, `RpfArchive.from_folder(...)`, and the functional helper `rpf_to_folder(...)` for exporting archives directly to folders.
- `RpfExportMode` as an explicit enum for `RPF` export workflows, including descriptions for `STORED`, `STANDALONE`, and `LOGICAL`.
- Automatic default-crypto initialization for encrypted standalone `RPF` loading, so `RpfArchive.from_path(...)` can open encrypted archives without preloading game keys.

### Changed
- Unified `RPF` ZIP and folder export around the same traversal logic, so nested `.rpf` archives are exported consistently.
- Standalone export made the default for folder and ZIP export, meaning GTA resources are now written with valid `RSC7` headers unless `LOGICAL` is requested explicitly.
- `RPF` export API cleaned up around `RpfExportMode` instead of the older boolean-style export flag.
- Core format modules split into smaller domain packages, including `RPF`, `META`, `YTD`, crypto, cache I/O, and native archive layers.

### Fixed
- Folder extraction for resource assets, so extracted files no longer lose their `RSC7` container by default.
- Nested-archive export behavior, preserving nested `.rpf` archives as directories during recursive export.

## [0.1.3]

### Changed
- More `RPF` point-read work moved into the native backend, reducing dependence on Python archive objects for one-off reads.
- Native Python binding layer split by domain (`index`, `crypto`, `rpf`, and module bootstrap) to keep the C++ boundary easier to maintain.
- Archive-table and entry-payload decryption paths switched to the native crypto backend instead of redundant Python fallbacks.
- `GameFileCache` reorganized into the `fivefury.cache` package, with smaller modules for core behavior, scanning, views, and asset helpers.
- Resource texture assets split into per-format modules under `fivefury.resource_assets`.
- Public README refreshed around current `GameFileCache`, extraction, and texture workflows.

### Added
- `ARCHITECTURE.md` with an internal map of the codebase, backend boundaries, and refactor guidance.
- Lazy `GameFileCache` lookups such as `archetype_dict`, per-kind dictionaries, iteration helpers, and kind statistics.
- Helpers to extract all referenced assets from a `YMAP`, including support for loose `.ymap` files.
- `YTD` texture-extraction helpers for listing and exporting textures as `DDS`.
- Embedded texture extraction for `YDR`, `YDD`, `YFT`, and `YPT` assets.
- Per-format resource-asset abstractions for embedded-texture traversal.

### Fixed
- Standalone extraction for resource assets, so extraction writes valid standalone `RSC7` files by default instead of raw internal blobs.
- Removal of dead and duplicated scan helpers left behind by the `GameFileCache` refactor.
- Reduced risk of divergence between Python and native `RPF` decryption paths.

### Performance
- Reduced Python-side overhead for archive-table decryption and point reads inside `RPF` archives.
- Batched native archive-variant reads used by `get_file()`, avoiding duplicate entry-resolution work for stored and standalone reads.
- Native `jenk_hash` implementation and additional caching around `MetaHash.uint`, reducing repeated hash work.
- Performance benchmark suite added for the optimized native and Python paths.
- `GameFileCache` archive scanning moved further into the native backend, with better skip performance and stabler Windows AES handling.

## [0.1.2]

### Changed
- `GameFileCache` reorganized into the `fivefury.cache` package with smaller modules for core behavior, scanning, views, and asset helpers.
- Resource texture assets split into per-format modules under `fivefury.resource_assets`.
- Public README refreshed around current `GameFileCache`, extraction, and texture workflows.

### Added
- `ARCHITECTURE.md` with an internal map of the codebase, backend boundaries, and refactor guidance.
- Lazy `GameFileCache` lookups such as `archetype_dict`, per-kind dictionaries, iteration helpers, and kind statistics.
- Helpers to extract all referenced assets from a `YMAP`, including support for loose `.ymap` files.

### Fixed
- Resource extraction now writes valid standalone `RSC7` files by default instead of invalid raw internal blobs.

## [0.1.1]

### Added
- `YTD` texture-extraction helpers for listing and exporting textures as `DDS`.
- Embedded texture extraction for `YDR`, `YDD`, `YFT`, and `YPT` assets.
- Per-format resource-asset abstractions for embedded-texture traversal.

### Changed
- `GameFileCache` can now resolve texture dictionaries through `YTYP` data and `gtxd.meta` parent relationships.
- README documentation now includes texture-extraction workflows for `YTD` and resource assets.

## [0.1.0]

### Added
- Initial public release of `fivefury`.
- Native `GameFileCache` scanning for GTA V `RPF` archives with DLC filtering, exclusions, and type-aware lookups.
- `YMAP` and `YTYP` creation, parsing, and saving APIs.
- Global hash-resolution utilities and `MetaHash` support.
- Core `YTD` handling and GTA V asset workflow helpers for Python 3.11+ on Windows.
