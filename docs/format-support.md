# Format Support

Support levels and current scope by GTA V file family.
Support levels:

| Status | Meaning |
| --- | --- |
| Full | Has practical read/write support and public high-level helpers for normal workflows. |
| Partial | Recognized or parsed enough for selected workflows, but not complete authoring support. |
| Indexed | Detected by `GameFileCache` and RPF tooling, but no dedicated high-level parser/writer yet. |
| Not implemented | Known GTA V format, but FiveFury does not currently expose dedicated support. |

### Full Support

| Format | Scope |
| --- | --- |
| `YDR` | Drawable resources: materials, shaders, samplers, numeric parameters, drawable models, LODs, render masks, lights, embedded textures, embedded bounds, skeletons, skinning, radial weight generation, rigid bone bindings, shader inspection, and skeleton hash recalculation. |
| `YDD` | Drawable dictionaries with multiple embedded drawables, high-level creation from named `YDR` drawables, and external-skeleton radial rigging helpers for ped components. |
| `YBN` | Bounds/collisions: primitive bounds, composite bounds, geometry bounds, BVH bounds, octants, material names, material colors, and generated collision chunks from triangle meshes. |
| `YCD` | Clip dictionaries: parsed metadata, sequence rebuilds, known track types, UV clip bindings, object animation metadata, skeletal tracks, root motion, camera tracks, and facial samples. |
| `YMAP` | Map metadata: entities, car generators, timecycle modifiers, occluders, content flags, entity flags, LOD lights, distant lights, and typed metadata. |
| `YTYP` | Archetypes: base/time/MLO archetypes, extensions, rooms, portals, entity sets, typed asset metadata, flags, LOD distances, physics dictionaries, and cutscene prop helpers. |
| `YMF` | Map manifests: `CPackFileMetaData` read/write, IMAP/ITYP dependency relationships, IMAP groups, interior bounds, HD texture bindings, relationship iteration, and manifest generation from YMAP sets with optional `GameFileCache` archetype lookup. |
| `YTD` | Texture dictionaries: read/write, resource texture payload preservation, cache extraction, and embedded-asset helpers. |
| `YND` | Path node resources: nodes, links, typed flags/enums, area helpers, automatic area ID calculation, network partitioning, and game-aligned junction heightmap generation. |
| `YNV` | Navmesh resources: sectors, polys, points, portals, typed metadata, validation, and basic Assimp/OBJ partitioning. |
| `CUT` | Cutscene files: cameras, tracks, events, props, peds, vehicles, lights, high-level scene conversion, `.cuts` script authoring, and `.cut` to `.cuts` export. |
| `GXT2` | Hashed UTF-8 text tables with binary read/write, CodeWalker-style text import/export, mapping-style helpers, and `GameFileCache` loading. |
| `AWC` | Audio wave containers: structural read/write, PCM and WAV extraction, mono and multichannel PCM authoring, and conversion from `.wav`, `.mp3`, `.ogg`, and `.flac` through `miniaudio`. |
| DLC metadata | Declarative `setup2.xml`, `content.xml`, `dlclist.xml`, and `extratitleupdatedata.meta` authoring, including content change sets, DLC pack RPF creation, and `dlc_patch` overlays. |
| `GTXD` metadata | Parent texture dictionary metadata in XML or binary RBF `CMapParentTxds` form, cache loading, parent-chain resolution, and duplicate-safe relationship editing. |
| `RPF` | RPF7 OPEN archives, nested `.rpf`, folder/ZIP conversion, extraction modes, and encrypted standalone RPF opening when keys are available. |

### Partial Or Indexed Support

| Format | Current behavior |
| --- | --- |
| `YFT` | Fragment reading/writing for common, damaged, extra and cloth drawables, including geometry, materials, LOD meshes, bounding sphere metadata, fragment flags, physics LODs, physics groups, physics children, child entity drawables, per-child breaking/inertia data, damping constants, damping archetypes, articulated body metadata, link attachments, group and child event references, editable composite bounds, mass/inertia helpers, glass/cloth/vehicle semantic queries, corpus scanning, validation, declarative physics helpers, geometry summaries and embedded texture dictionaries. |
| `YPT` | Resource texture dictionaries can be discovered/extracted from particle dictionaries, but full particle authoring is not implemented. |
| `REL` | Audio metadata banks can be read/written structurally, opened through `GameFileCache`, and round-tripped with unknown entries preserved. `dat10.rel` modular synth presets/synths, `dat16.rel` curves, `dat22.rel` categories, and common `dat54.rel` sound graph entries have typed models, including simple AWC-backed sounds, wrappers, sequential/multitrack/streaming child lists, randomized variations, modular synth sounds, automation/MIDI sounds, note maps, variable-curve and conditional routing, directional/kinetic routing, variable blocks, math operations, parameter transforms, fluctuators, external streams, sound sets, sound-set lists, and sound-hash lists. Other REL item families currently stay as raw entries. |
| `YED` | Expression dictionaries can be detected, opened through `GameFileCache`, inspected for expressions/tracks/streams/springs/instruction opcodes, edited safely for spring-list cloning, built from scratch for spring dictionaries, and validated before writing. |
| `YMT` | Generic META-backed read/write plus typed helpers for known roots such as `CMapParentTxds`, scenario manifests/regions/groups, ped variations, ped init metadata, and streaming request records. Unknown RBF/PSO/META payloads are preserved conservatively. |
| `RBF` metadata | Generic binary RBF parsing is exposed for metadata containers that use `RBF0`. It is a shared metadata layer, not a standalone GTA asset extension. |
| `YWR`, `YVR` | Recognized/indexed by `GameFileCache` and RPF tooling, but no complete dedicated high-level reader/writer is exposed. |

### Not Implemented Yet

| Format family | Notes |
| --- | --- |
| `YFD`, `YPDB`, `MRF` | Known game file types, currently no dedicated high-level support. |
| Heightmap and watermap resources | Recognized as game concepts, but no complete public reader/writer yet. |
| Vehicle/ped audio REL specializations | REL files can be loaded structurally, but specialized semantic authoring beyond the initial synth/curve/category/sound subset is not currently exposed. |
