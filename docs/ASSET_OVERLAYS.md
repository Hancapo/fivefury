# Loose asset overlays

`GameFileOverlay` resolves a scoped export before consulting an existing
`GameFileCache`. It reads loose files and nested RPFs without copying the
installation index or rescanning the game directory.

```python
from fivefury import (
    AssetRegistration,
    DlcDataFileType,
    GameFileOverlay,
    GameTarget,
)

registrations = [
    AssetRegistration(
        "common/data/peds/custom_actor.meta",
        DlcDataFileType.PED_METADATA,
    ),
]

with GameFileOverlay(
    "export/loose",
    fallback=installation_cache,  # Already scanned; optional.
    registrations=registrations,
    game=GameTarget.GTA5_ENHANCED,
) as assets:
    bundle = assets.resolve_cutscene("scene.cut")
    for binding in bundle.bindings.values():
        if binding.ped_init_data is not None:
            print(binding.ped_init_data.name)
            print(binding.ped_metadata_asset.path)
            print(binding.expression_dictionary)
    for issue in bundle.diagnostics:
        print(issue.code, issue.message)
```

## Registrations

An inventory path alone is not a content registration. Persist each registration's
`path` and `file_type.value` alongside an export and reconstruct `AssetRegistration`
when mounting it. Paths are relative to the loose root; archive-entry paths may
include nested `.rpf` components.

| Registration | Decoded content |
| --- | --- |
| `DlcDataFileType.PED_METADATA` | `YmtPedMetadata`, including exact model/expression references |
| `DlcDataFileType.EXPRESSION_SETS` | `PedExpressionSetMetadata` |

These are the supported explicit metadata registrations. RPFs and ordinary
resource files are indexed normally and need no metadata registration here.
The conventional `peds.meta` filename is recognized automatically. Arbitrary
`.meta` filenames are not guessed from their name or XML content. For direct
reading, `read_ped_metadata(source)` accepts XML or binary ped-init YMT.
A component YMT is not ped-init metadata.

For a standalone cache, `cache.register_metadata(registration)` applies the type
to an already indexed file. Registration requires that the path exists in that
cache and invalidates its derived in-memory views.

## Precedence and lifetime

- The loose layer precedes every installation source, including installation mods.
- Within a layer, normal source precedence applies. Identical init records agree;
  conflicting records in the same tier remain unresolved with diagnostics.
- Ped-init selection uses the record's model identity, not its containing filename.
- Lookups return overlay-local IDs; reading always routes to the original source.
  Never persist these IDs or insert them into an installation index.
- Closing the context releases its loose resources, not the borrowed installation.
- Neither metadata resolution nor overlay mounting loads unrelated YMAP/YBN assets.

## Changed exports and cancellation

```python
from fivefury import CutsceneResolutionCancellation

cancellation = CutsceneResolutionCancellation()
assets.remount(
    "export/loose",
    registrations=registrations,
    cancellation=cancellation,
)
bundle = assets.resolve_cutscene("scene.cut", cancellation=cancellation)
```

Remount after changing export files, passing the current registrations again.
The replacement becomes active only after indexing and registration succeed.
A missing registration, unreadable archive or cancellation leaves the prior mount
active. Cancellation is checked before and after indexing and between registrations;
an individual archive-indexing call is not interrupted midway.

Remounting discards derived expression/outfit state. Resolve a new bundle/catalog;
do not reuse assets from the old loose mount. They are rejected by the new mount.
Concurrent remount and resolution on the same overlay are not supported.

Malformed metadata produces decode/resolution diagnostics rather than a fake init
record. Successful CPU resolution or expression evaluation does not certify
in-game playback, rendering or DLC mounting.
