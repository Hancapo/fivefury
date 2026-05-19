# Metadata Layers

Shared metadata formats and helpers used by multiple GTA V assets.
FiveFury exposes a few metadata layers directly because several GTA V formats share them internally.

### Read GTXD parent texture dictionaries

```python
from fivefury import read_gtxd

gtxd = read_gtxd("gtxd.ymt")

print(gtxd.source)  # "xml" or "rbf"
print(gtxd.parent_of("custom_asset_txd"))
print(list(gtxd.iter_chain("custom_asset_txd")))
```

`GTXD` data maps child texture dictionaries to parent dictionaries. `GameFileCache` uses it when resolving textures for streamed assets, so a drawable can find textures in its own `YTD`, an explicitly assigned dictionary, or inherited parent dictionaries.

### Inspect known YMT roots

```python
from fivefury import YmtContentType, read_ymt

ymt = read_ymt("peds.ymt")

print(ymt.format)
print(ymt.content_type)

if ymt.content_type is YmtContentType.PED_METADATA:
    for item in ymt.ped_metadata.init_datas:
        print(item.clip_dictionary_name, item.expression_dictionary_name)
```

`YMT` support is intentionally layered: known roots get typed helpers, while unknown META/PSO/RBF data remains available for safe roundtrips instead of being discarded.
