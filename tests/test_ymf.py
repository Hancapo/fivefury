from __future__ import annotations

from fivefury.gamefile import GameFileType
from fivefury.pso import (
    PMAP,
    PSCH,
    PSIG,
    PSIN,
    decode_array_header,
    is_pso,
    parse_pmap,
    parse_psch_enums,
    parse_sections,
)
from fivefury.ymap import EntityDef, MloInstanceDef, Ymap
from fivefury.ymf import (
    YMF_HOURS_ON_OFF_MASK,
    YMF_MAX_ARRAY_ITEMS,
    YMF_MAX_IMAP_DEPENDENCIES,
    YMF_MAX_INTERIOR_BOUNDS,
    YMF_MAX_ITYP_DEPENDENCIES,
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
    build_ymf,
    build_ymf_manifest_for_ymaps,
    create_ymf_for_ymaps,
    iter_ymf_relationships,
    read_ymf,
    read_ymf_xml,
)
from fivefury.ytyp import Archetype, MloArchetypeDef, MloRoomDef, Ytyp, YtypDependency


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
        imap_dependencies_2=[
            ImapDependencies(
                "city_imap", ["city_ityp", "shared_ityp"], ManifestFlags.INTERIOR_DATA
            )
        ],
        ityp_dependencies_2=[
            ItypDependencies(
                "city_ityp", ["interior_ityp"], ManifestFlags.INTERIOR_DATA
            )
        ],
        map_data_groups=[
            MapDataGroup(
                "city_group",
                ["city_bounds"],
                PackFileMetaDataImapGroupType.TIME_DEPENDENT,
            ),
        ],
        interiors=[InteriorBoundsFile("interior_name", ["interior_bounds"])],
        hd_txd_bindings=[
            HdTxdAssetBinding(
                PackFileMetaDataAssetType.AT_TXD, "city_txd", "city_txd_hd"
            )
        ],
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
        imap_dependencies_2=[
            ImapDependencies("city_imap", ["city_ityp"], ManifestFlags.INTERIOR_DATA)
        ],
        map_data_groups=[
            MapDataGroup(
                "city_group",
                ["city_bounds"],
                PackFileMetaDataImapGroupType.TIME_DEPENDENT
                | PackFileMetaDataImapGroupType.WEATHER_DEPENDENT,
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
        PackFileMetaDataImapGroupType.TIME_DEPENDENT
        | PackFileMetaDataImapGroupType.WEATHER_DEPENDENT
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

    assert [item.kind for item in relationships] == [
        YmfRelationshipType.IMAP_TO_ITYP,
        YmfRelationshipType.ITYP_TO_ITYP,
    ]
    assert int(relationships[0].source) == int(
        manifest.imap_dependencies_2[0].imap_name
    )
    assert int(relationships[0].target) == int(
        manifest.imap_dependencies_2[0].ityp_dependencies[0]
    )


def test_ymf_writer_uses_runtime_pso_layout() -> None:
    manifest = PackFileMetaData(
        imap_dependencies_2=[
            ImapDependencies(0x77C7848A, [0xE8D5FCC4], ManifestFlags.INTERIOR_DATA)
        ],
        ityp_dependencies_2=[
            ItypDependencies(
                0xE8D5FCC4,
                [
                    0xA3855B81,
                    0x4396D8B2,
                    0x1C63944D,
                    0xE07309C7,
                    0x7E286CC2,
                    0xF83E79BC,
                ],
                ManifestFlags.INTERIOR_DATA,
            )
        ],
        interiors=[InteriorBoundsFile(0xE8D5FCC4, [0xE8D5FCC4])],
    )

    sections = parse_sections(build_ymf(manifest).to_bytes())
    blocks, root_block_id = parse_pmap(sections[PMAP])

    assert list(sections) == [PSIN, PMAP, PSCH]
    assert PSIG not in sections
    assert sections[PSIN][8:16] == b"\x00" * 8
    assert len(sections[PSIN]) == 216
    assert len(sections[PMAP]) == 96
    assert len(sections[PSCH]) == 412
    assert [
        (block.name_hash, block.offset, block.length) for block in blocks.values()
    ] == [
        (6, 16, 32),
        (0xC11F3EE1, 48, 24),
        (0x5A564E50, 72, 24),
        (0x2C325290, 96, 24),
        (0x93A68A2F, 120, 96),
    ]
    assert root_block_id == 5
    assert decode_array_header(sections[PSIN], blocks[2].offset + 8).pointer.offset == 0
    assert decode_array_header(sections[PSIN], blocks[3].offset + 8).pointer.offset == 4
    assert (
        decode_array_header(sections[PSIN], blocks[4].offset + 8).pointer.offset == 28
    )
    assert list(parse_psch_enums(sections[PSCH])) == [0x6452A05B]


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
    assert [
        str(item) for item in manifest.imap_dependencies_2[0].ityp_dependencies
    ] == ["city_ityp"]
    assert len(manifest.ityp_dependencies_2) == 1
    assert str(manifest.ityp_dependencies_2[0].ityp_name) == "city_ityp"
    assert [
        str(item) for item in manifest.ityp_dependencies_2[0].ityp_dependencies
    ] == ["shared_ityp"]


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
    assert [
        str(item) for item in manifest.imap_dependencies_2[0].ityp_dependencies
    ] == ["interior_ityp"]
    assert manifest.imap_dependencies_2[0].flags is ManifestFlags.INTERIOR_DATA


def test_build_ymf_manifest_for_ymaps_accepts_explicit_custom_dependencies_without_cache() -> (
    None
):
    ymap = Ymap(name="custom_imap")

    manifest = build_ymf_manifest_for_ymaps(
        [ymap],
        dependencies={"custom_imap": ["custom_ityp"]},
    )

    assert str(manifest.imap_dependencies_2[0].imap_name) == "custom_imap"
    assert [
        str(item) for item in manifest.imap_dependencies_2[0].ityp_dependencies
    ] == ["custom_ityp"]


def test_build_ymf_manifest_marks_the_ytyp_holding_an_mlo_as_an_interior_type() -> None:
    mlo = MloArchetypeDef(name="custom_mlo", rooms=[MloRoomDef(name="limbo")])
    ytyp = Ytyp(name="custom_ityp", archetypes=[mlo])
    ymap = Ymap(
        name="custom_imap", entities=[MloInstanceDef(archetype_name="custom_mlo")]
    )

    manifest = build_ymf_manifest_for_ymaps([ymap], ytyps=[ytyp])

    interior_types = [
        entry
        for entry in manifest.ityp_dependencies_2
        if entry.flags is ManifestFlags.INTERIOR_DATA
    ]
    assert [str(entry.ityp_name) for entry in interior_types] == ["custom_ityp"]
    assert list(interior_types[0].ityp_dependencies) == []
    assert manifest.validate() == []


def test_build_ymf_manifest_leaves_plain_ytyps_unflagged() -> None:
    ytyp = Ytyp(name="plain_ityp", archetypes=[Archetype(name="prop")])
    ymap = Ymap(name="plain_imap", entities=[EntityDef(archetype_name="prop")])

    manifest = build_ymf_manifest_for_ymaps([ymap], ytyps=[ytyp])

    assert all(
        entry.flags is not ManifestFlags.INTERIOR_DATA
        for entry in manifest.ityp_dependencies_2
    )


def test_build_ymf_manifest_registers_mlo_static_bounds_when_ybn_is_packaged() -> None:
    mlo = MloArchetypeDef(
        name="custom_mlo",
        physics_dictionary="custom_collision_group",
        rooms=[MloRoomDef(name="limbo")],
    )
    ytyp = Ytyp(name="custom_ityp", archetypes=[mlo])
    ymap = Ymap(
        name="custom_imap", entities=[MloInstanceDef(archetype_name="custom_mlo")]
    )

    manifest = build_ymf_manifest_for_ymaps(
        [ymap],
        ytyps=[ytyp],
        ybns={"custom_mlo": object()},
    )

    assert len(manifest.interiors) == 1
    assert int(manifest.interiors[0].name) == int(mlo.name)
    assert [int(bound) for bound in manifest.interiors[0].bounds] == [int(mlo.name)]
    assert manifest.validate() == []


def test_build_ymf_manifest_registers_standalone_mlo_rpf_without_ymap() -> None:
    mlo = MloArchetypeDef(name="custom_mlo", rooms=[MloRoomDef(name="limbo")])
    ytyp = Ytyp(name="custom_ityp", archetypes=[mlo])

    manifest = build_ymf_manifest_for_ymaps(
        [],
        ytyps=[ytyp],
        ybns={"custom_mlo": object()},
    )

    assert [
        (int(item.name), [int(bound) for bound in item.bounds])
        for item in manifest.interiors
    ] == [(int(mlo.name), [int(mlo.name)])]


def test_ymf_runtime_limit_constants_match_serialized_contracts() -> None:
    assert YMF_MAX_IMAP_DEPENDENCIES == 6
    assert YMF_MAX_ITYP_DEPENDENCIES == 8
    assert YMF_MAX_INTERIOR_BOUNDS == 2
    assert YMF_HOURS_ON_OFF_MASK == 0x00FFFFFF
    assert YMF_MAX_ARRAY_ITEMS == 0xFFFE


def test_ymf_validation_counts_unique_imap_dependencies_across_entries() -> None:
    manifest = PackFileMetaData(
        imap_dependencies=[ImapDependency("city_imap", "parent_0")],
        imap_dependencies_2=[
            ImapDependencies("city_imap", [f"parent_{index}" for index in range(1, 5)]),
            ImapDependencies("city_imap", ["parent_4", "parent_5", "parent_6"]),
        ],
    )

    issues = manifest.validate()

    assert any(
        "7 dynamic YTYP dependencies" in issue and "at most 6" in issue
        for issue in issues
    )


def test_ymf_validation_does_not_count_duplicate_or_permanent_imap_dependencies() -> (
    None
):
    manifest = PackFileMetaData(
        imap_dependencies_2=[
            ImapDependencies("city_imap", [f"parent_{index}" for index in range(7)]),
            ImapDependencies("city_imap", ["parent_0", "parent_1"]),
        ],
    )

    assert manifest.validate(permanent_ytyps=["parent_6"]) == []
    assert build_ymf(manifest, permanent_ytyps=["parent_6"]).to_bytes()


def test_ymf_validation_counts_unique_ityp_parents_across_entries() -> None:
    manifest = PackFileMetaData(
        ityp_dependencies_2=[
            ItypDependencies("child_ityp", [f"parent_{index}" for index in range(5)]),
            ItypDependencies(
                "child_ityp", [f"parent_{index}" for index in range(4, 9)]
            ),
        ],
    )

    issues = manifest.validate()

    assert any(
        "9 dynamic parent YTYPs" in issue and "at most 8" in issue for issue in issues
    )


def test_ymf_writer_rejects_runtime_dependency_overflow() -> None:
    manifest = PackFileMetaData(
        imap_dependencies_2=[
            ImapDependencies("city_imap", [f"parent_{index}" for index in range(7)]),
        ],
    )

    try:
        build_ymf(manifest).to_bytes()
    except ValueError as exc:
        assert "runtime supports at most 6" in str(exc)
    else:
        raise AssertionError("invalid YMF dependency count was serialized")


def test_ymf_validation_rejects_non_hour_bits_and_oversized_arrays() -> None:
    invalid_hours = MapDataGroup("timed_group", hours_on_off=1 << 24)
    oversized = MapDataGroup("large_group", bounds=[0] * (YMF_MAX_ARRAY_ITEMS + 1))

    assert any("hours 0 through 23" in issue for issue in invalid_hours.validate())
    assert any("support at most 65534" in issue for issue in oversized.validate())


def test_ymf_validation_rejects_duplicate_map_data_groups() -> None:
    manifest = PackFileMetaData(
        map_data_groups=[MapDataGroup("managed_group"), MapDataGroup("managed_group")],
    )

    assert any(
        "repeats map data group managed_group" in issue for issue in manifest.validate()
    )
