# Asset source provenance

`AssetRecord.source_tier` identifies the semantic source using `AssetSourceTier`:

| Tier | Source |
| --- | --- |
| `BASE` | Base installation content. |
| `UPDATE` | Update content outside DLC packs. |
| `DLC` | Content under a DLC pack path. |
| `MODS` | Installation content under `mods/`. |
| `OVERLAY` | Assets owned by a scoped `GameFileOverlay`. |

Fallback records retain their installation tier. Overlay provenance applies to
both loose files and entries inside the overlay's RPFs. A standalone loose cache
uses its installation-relative paths; being a loose file alone does not make an
asset an overlay.

Provenance is not a sorting key. `source_priority` is a separate ordering value:
an overlay's fallback BASE record can have priority 7 and still have tier `BASE`.
Never construct an enum from a sorting priority or use enum values to compare
overlay and installation precedence.

Vehicle appearance sources use this same enum, replacing the former
`VehicleAppearanceSourceTier`. Import `AssetSourceTier` from `fivefury` or
`fivefury.cache`.

```python
from fivefury import AssetSourceTier, GameFileOverlay

with GameFileOverlay(export_directory, fallback=installation) as overlay:
    appearance = overlay.resolve_vehicle_appearance("example_car")
    for source in appearance.sources:
        print(source.path, source.tier.name)
        if source.tier is AssetSourceTier.OVERLAY:
            print("Definition supplied by the export")
```

Variations and color definitions resolve independently. An installation-only
variation can therefore use colors overridden by the overlay, and both sources
remain visible in the result. Closing the overlay does not close its borrowed
installation cache. Remount after modifying export files.
Rescanning the borrowed installation invalidates the overlay's appearance index
before the next appearance query, including when the asset count is unchanged.
