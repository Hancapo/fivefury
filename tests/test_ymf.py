from __future__ import annotations

from fivefury.ymf import (
    HdTxdAssetBinding,
    ImapDependencies,
    ImapDependency,
    InteriorBoundsFile,
    ItypDependencies,
    ManifestFlags,
    MapDataGroup,
    PackFileMetaData,
    PackFileMetaDataAssetType,
    PackFileMetaDataImapGroupType,
    YmfRelationshipType,
    build_ymf_manifest_for_ymaps,
    build_ymf,
    create_ymf_for_ymaps,
    iter_ymf_relationships,
    read_ymf,
    read_ymf_xml,
)
from fivefury.gamefile import GameFileType
from fivefury.pso import is_pso
from fivefury.ymap import EntityDef, MloInstanceDef, Ymap
from fivefury.ytyp import Archetype, Ytyp, YtypDependency


class _FakeAsset:
    def __init__(self, stem: str, kind: GameFileType) -> None:
        self.stem = stem
        self.kind = kind
        self.path = f"{stem}{kind.extension if hasattr(kind, 'extension') else ''}"


class _FakeGameFile:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed


class _FakeCache:
    def __init__(self, entries: list[tuple[_FakeAsset, object]]) -> None:
        self.entries = entries

    def iter_assets(self, kind: GameFileType | None = None):
        for asset, _ in self.entries:
            if kind is None or asset.kind is kind:
                yield asset

    def get_file(self, asset: _FakeAsset) -> _FakeGameFile:
        for candidate, parsed in self.entries:
            if candidate is asset:
                return _FakeGameFile(parsed)
        raise KeyError(asset)


def test_ymf_manifest_relationships_cover_map_dependencies() -> None:
    manifest = PackFileMetaData(
        imap_dependencies=[ImapDependency("old_imap", "old_ityp")],
        imap_dependencies_2=[ImapDependencies("city_imap", ["city_ityp", "shared_ityp"], ManifestFlags.INTERIOR_DATA)],
        ityp_dependencies_2=[ItypDependencies("city_ityp", ["interior_ityp"], ManifestFlags.INTERIOR_DATA)],
        map_data_groups=[
            MapDataGroup("city_group", ["city_bounds"], PackFileMetaDataImapGroupType.TIME_DEPENDENT),
        ],
        interiors=[InteriorBoundsFile("interior_name", ["interior_bounds"])],
        hd_txd_bindings=[HdTxdAssetBinding(PackFileMetaDataAssetType.AT_TXD, "city_txd", "city_txd_hd")],
    )

    relationships = manifest.iter_relationships()

    assert [item.kind for item in relationships] == [
        YmfRelationshipType.LEGACY_IMAP_TO_ITYP,
        YmfRelationshipType.IMAP_TO_ITYP,
        YmfRelationshipType.IMAP_TO_ITYP,
        YmfRelationshipType.ITYP_TO_ITYP,
        YmfRelationshipType.IMAP_GROUP_TO_BOUND,
        YmfRelationshipType.INTERIOR_TO_BOUND,
        YmfRelationshipType.HD_TXD_BINDING,
    ]
    assert relationships[1].flags is ManifestFlags.INTERIOR_DATA
    assert str(relationships[-1].source) == "city_txd"
    assert str(relationships[-1].target) == "city_txd_hd"


def test_ymf_xml_roundtrip_uses_pack_file_metadata_shape() -> None:
    manifest = PackFileMetaData(
        imap_dependencies_2=[ImapDependencies("city_imap", ["city_ityp"], ManifestFlags.INTERIOR_DATA)],
        map_data_groups=[
            MapDataGroup(
                "city_group",
                ["city_bounds"],
                PackFileMetaDataImapGroupType.TIME_DEPENDENT | PackFileMetaDataImapGroupType.WEATHER_DEPENDENT,
                ["RAIN"],
                0x00FF00FF,
            )
        ],
    )

    parsed = read_ymf_xml(manifest.to_xml_bytes())

    assert str(parsed.imap_dependencies_2[0].imap_name) == "city_imap"
    assert str(parsed.imap_dependencies_2[0].ityp_dependencies[0]) == "city_ityp"
    assert parsed.imap_dependencies_2[0].flags is ManifestFlags.INTERIOR_DATA
    assert parsed.map_data_groups[0].flags == (
        PackFileMetaDataImapGroupType.TIME_DEPENDENT | PackFileMetaDataImapGroupType.WEATHER_DEPENDENT
    )
    assert parsed.map_data_groups[0].hours_on_off == 0x00FF00FF


def test_ymf_binary_roundtrip_preserves_manifest_relationships() -> None:
    manifest = PackFileMetaData(
        imap_dependencies_2=[ImapDependencies("city_imap", ["city_ityp"])],
        ityp_dependencies_2=[ItypDependencies("city_ityp", ["shared_ityp"])],
    )
    ymf = build_ymf(manifest, name="pack_manifest")
    data = ymf.to_bytes()

    assert is_pso(data)
    parsed = read_ymf(data)
    relationships = iter_ymf_relationships(parsed)

    assert [item.kind for item in relationships] == [YmfRelationshipType.IMAP_TO_ITYP, YmfRelationshipType.ITYP_TO_ITYP]
    assert int(relationships[0].source) == int(manifest.imap_dependencies_2[0].imap_name)
    assert int(relationships[0].target) == int(manifest.imap_dependencies_2[0].ityp_dependencies[0])


def test_build_ymf_manifest_for_ymaps_resolves_archetypes_from_cache() -> None:
    ymap = Ymap(name="city_imap")
    ymap.add_entity(EntityDef(archetype_name="prop_a"))
    ymap.add_entity(EntityDef(archetype_name="prop_b"))
    ytyp = Ytyp(
        name="city_ityp",
        archetypes=[Archetype(name="prop_a"), Archetype(name="prop_b")],
        dependencies=[YtypDependency("shared_ityp")],
    )
    cache = _FakeCache([(_FakeAsset("city_ityp", GameFileType.YTYP), ytyp)])

    manifest = build_ymf_manifest_for_ymaps([ymap], cache=cache)

    assert len(manifest.imap_dependencies_2) == 1
    assert str(manifest.imap_dependencies_2[0].imap_name) == "city_imap"
    assert [str(item) for item in manifest.imap_dependencies_2[0].ityp_dependencies] == ["city_ityp"]
    assert len(manifest.ityp_dependencies_2) == 1
    assert str(manifest.ityp_dependencies_2[0].ityp_name) == "city_ityp"
    assert [str(item) for item in manifest.ityp_dependencies_2[0].ityp_dependencies] == ["shared_ityp"]


def test_create_ymf_for_ymaps_can_use_cached_ymaps_and_marks_interiors() -> None:
    ymap = Ymap(name=0)
    ymap.add_entity(MloInstanceDef(archetype_name="mlo_arch"))
    ytyp = Ytyp(name=0, archetypes=[Archetype(name="mlo_arch")])
    ymap_asset = _FakeAsset("interior_imap", GameFileType.YMAP)
    ytyp_asset = _FakeAsset("interior_ityp", GameFileType.YTYP)
    cache = _FakeCache([(ymap_asset, ymap), (ytyp_asset, ytyp)])

    ymf = create_ymf_for_ymaps(cache=cache)
    manifest = ymf.manifest

    assert ymf.name == "_manifest"
    assert ymf.suggested_path() == "_manifest.ymf"
    assert manifest is not None
    assert str(manifest.imap_dependencies_2[0].imap_name) == "interior_imap"
    assert [str(item) for item in manifest.imap_dependencies_2[0].ityp_dependencies] == ["interior_ityp"]
    assert manifest.imap_dependencies_2[0].flags is ManifestFlags.INTERIOR_DATA


def test_build_ymf_manifest_for_ymaps_accepts_explicit_custom_dependencies_without_cache() -> None:
    ymap = Ymap(name="custom_imap")

    manifest = build_ymf_manifest_for_ymaps(
        [ymap],
        dependencies={"custom_imap": ["custom_ityp"]},
    )

    assert str(manifest.imap_dependencies_2[0].imap_name) == "custom_imap"
    assert [str(item) for item in manifest.imap_dependencies_2[0].ityp_dependencies] == ["custom_ityp"]
