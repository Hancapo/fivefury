from __future__ import annotations

import struct
from types import SimpleNamespace

import pytest

from fivefury import (
    DlcContentFileArray,
    DlcContentGroup,
    DlcDataFileContents,
    DlcDataFileType,
    DlcExtraTitleUpdateData,
    DlcInstallPartition,
    DlcList,
    DlcLoadingScreenContext,
    DlcPack,
    DlcPatch,
    DlcRpfEncryption,
    DlcSetupData,
    GameTarget,
    RpfArchive,
    Texture,
    TextureFormat,
    TextureUsage,
    ValidationError,
    Ytd,
    build_rsc7,
    create_dlc_folder_metadata,
    read_dlc_content,
    read_dlc_extra_title_update_data,
    read_dlc_list,
    read_dlc_pack,
    read_dlc_setup,
    validate_dlc_asset_targets,
    validate_dlc_folder,
    validate_dlc_pack,
    write_dlc_folder_metadata,
)
from fivefury.texture import total_mip_data_size

SETUP_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<SSetupData>
  <deviceName>dlc_MP2025_02</deviceName>
  <datFile>content.xml</datFile>
  <timeStamp>23/09/2024 12:00:00</timeStamp>
  <nameHash>MP2025_02</nameHash>
  <contentChangeSets />
  <contentChangeSetGroups>
    <Item>
      <NameHash>GROUP_STARTUP</NameHash>
      <ContentChangeSets>
        <Item>MP2025_02_AUTOGEN</Item>
      </ContentChangeSets>
    </Item>
    <Item>
      <NameHash>GROUP_MAP</NameHash>
      <ContentChangeSets>
        <Item>MP2025_02_MAP_UPDATE</Item>
      </ContentChangeSets>
    </Item>
  </contentChangeSetGroups>
  <startupScript />
  <scriptCallstackSize value="0" />
  <type>EXTRACONTENT_COMPAT_PACK</type>
  <order value="54" />
  <minorOrder value="0" />
  <isLevelPack value="false" />
  <dependencyPackHash />
  <requiredVersion />
  <subPackCount value="0" />
</SSetupData>
"""


CONTENT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<CDataFileMgr__ContentsOfDataFileXml>
  <disabledFiles />
  <includedXmlFiles />
  <includedDataFiles />
  <dataFiles>
    <Item>
      <filename>dlc_mp2025_02:/%PLATFORM%/levels/gta5/LODLights.rpf</filename>
      <fileType>RPF_FILE</fileType>
      <overlay value="false" />
      <disabled value="true" />
      <persistent value="true" />
      <contents>CONTENTS_DLC_MAP_DATA</contents>
    </Item>
    <Item>
      <filename>dlc_mp2025_02:/common/data/props.ityp</filename>
      <fileType>DLC_ITYP_REQUEST</fileType>
      <overlay value="false" />
      <disabled value="true" />
      <persistent value="false" />
    </Item>
  </dataFiles>
  <contentChangeSets>
    <Item>
      <changeSetName>MP2025_02_MAP_UPDATE</changeSetName>
      <mapChangeSetData />
      <filesToInvalidate />
      <filesToDisable />
      <filesToEnable>
        <Item>dlc_mp2025_02:/%PLATFORM%/levels/gta5/LODLights.rpf</Item>
        <Item>dlc_mp2025_02:/common/data/props.ityp</Item>
      </filesToEnable>
    </Item>
  </contentChangeSets>
  <patchFiles />
</CDataFileMgr__ContentsOfDataFileXml>
"""


COMPLETE_CONTENT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<CDataFileMgr__ContentsOfDataFileXml>
  <disabledFiles><Item>platform:/disabled.meta</Item></disabledFiles>
  <includedXmlFiles>
    <Item>
      <dataFiles>
        <Item platform="ps5|xbsx">
          <filename>dlc_test:/common/data/included.meta</filename>
          <fileType>EXTRA_TITLE_UPDATE_DATA</fileType>
          <registerAs>included</registerAs>
          <locked value="true" />
          <loadCompletely value="true" />
          <overlay value="false" />
          <patchFile value="true" />
          <disabled value="false" />
          <persistent value="true" />
          <enforceLsnSorting value="false" />
          <contents>CONTENTS_DEFAULT</contents>
          <installPartition>PARTITION_1</installPartition>
        </Item>
      </dataFiles>
    </Item>
  </includedXmlFiles>
  <includedDataFiles><Item>common:/data/base.meta</Item></includedDataFiles>
  <dataFiles>
    <Item>
      <filename>dlc_test:/x64/levels/gta5/navmeshes.rpf</filename>
      <fileType>RPF_FILE</fileType>
      <disabled value="true" />
      <persistent value="true" />
    </Item>
  </dataFiles>
  <contentChangeSets>
    <Item>
      <changeSetName>TEST_MAP</changeSetName>
      <mapChangeSetData>
        <Item>
          <associatedMap>MO_JIM_L11</associatedMap>
          <filesToInvalidate><Item>platform:/old.rpf</Item></filesToInvalidate>
          <filesToDisable />
          <filesToEnable><Item>dlc_test:/x64/levels/gta5/navmeshes.rpf</Item></filesToEnable>
          <txdToLoad><Item>test_txd</Item></txdToLoad>
          <txdToUnload />
          <residentResources>
            <Item><AssetName>test_asset</AssetName><Extension>ydr</Extension></Item>
          </residentResources>
          <unregisterResources />
          <dataFilesToLoad><Item>test_data</Item></dataFilesToLoad>
        </Item>
      </mapChangeSetData>
      <filesToInvalidate />
      <filesToDisable />
      <filesToEnable />
      <txdToLoad><Item>global_txd</Item></txdToLoad>
      <txdToUnload />
      <residentResources />
      <unregisterResources>
        <Item><AssetName>old_asset</AssetName><Extension>ydd</Extension></Item>
      </unregisterResources>
      <dataFilesToLoad><Item>global_data</Item></dataFilesToLoad>
      <requiresLoadingScreen value="true" />
      <loadingScreenContext>LOADINGSCREEN_CONTEXT_LAST_FRAME</loadingScreenContext>
      <executionConditions>
        <activeChangesetConditions>
          <Item><name>BASE_MAP</name><condition value="true" /></Item>
        </activeChangesetConditions>
        <genericConditions>$level=MO_JIM_L11</genericConditions>
      </executionConditions>
      <useCacheLoader value="true" />
    </Item>
  </contentChangeSets>
  <patchFiles><Item>update:/patch.rpf</Item></patchFiles>
  <allowedFolders><Item>dlc_test:/</Item></allowedFolders>
</CDataFileMgr__ContentsOfDataFileXml>
"""


def test_dlc_setup_parses_and_writes_change_set_groups() -> None:
    setup = read_dlc_setup(SETUP_XML)

    assert setup.device_name == "dlc_MP2025_02"
    assert setup.device_path == "dlc_MP2025_02:/"
    assert setup.order == 54
    assert setup.content_change_set_groups[1].name == "GROUP_MAP"
    assert setup.content_change_set_groups[1].change_sets == ["MP2025_02_MAP_UPDATE"]

    setup.map("MP2025_02_GTA5_LODLIGHTS")
    reparsed = read_dlc_setup(setup.to_xml_bytes())

    assert "MP2025_02_GTA5_LODLIGHTS" in reparsed.content_change_set_groups[1].change_sets


def test_dlc_content_parses_and_writes_files_and_change_sets() -> None:
    content = read_dlc_content(CONTENT_XML)

    assert content.data_files[0].file_type == "RPF_FILE"
    assert content.data_files[0].contents == "CONTENTS_DLC_MAP_DATA"
    assert content.content_change_sets[0].files_to_enable[1].endswith("props.ityp")

    content.content_change_sets[0].enable("dlc_mp2025_02:/common/data/extra.meta")
    reparsed = read_dlc_content(content.to_xml_bytes())

    assert reparsed.data_files[1].file_type == "DLC_ITYP_REQUEST"
    assert reparsed.content_change_sets[0].files_to_enable[-1].endswith("extra.meta")


def test_dlc_content_preserves_complete_runtime_metadata() -> None:
    content = read_dlc_content(COMPLETE_CONTENT_XML)

    assert content.disabled_files == ["platform:/disabled.meta"]
    assert content.allowed_folders == ["dlc_test:/"]
    assert isinstance(content.included_xml_files[0], DlcContentFileArray)
    included = content.included_xml_files[0].data_files[0]
    assert included.platform == "ps5|xbsx"
    assert included.locked is True
    assert included.patch_file is True
    assert included.install_partition == DlcInstallPartition.PARTITION_1

    change_set = content.content_change_sets[0]
    assert change_set.map_change_set_data[0].associated_map == "MO_JIM_L11"
    assert change_set.map_change_set_data[0].resident_resources[0].asset_name == "test_asset"
    assert change_set.data_files_to_load == ["global_data"]
    assert change_set.loading_screen_context == DlcLoadingScreenContext.LAST_FRAME
    assert change_set.execution_conditions is not None
    assert change_set.execution_conditions.generic_conditions == "$level=MO_JIM_L11"

    assert read_dlc_content(content.to_xml_bytes()) == content


def test_dlc_content_preserves_absent_optional_file_fields() -> None:
    content = read_dlc_content(
        b"""<CDataFileMgr__ContentsOfDataFileXml><dataFiles><Item>
        <filename>dlc_test:/minimal.meta</filename><fileType>EXTRA_TITLE_UPDATE_DATA</fileType>
        </Item></dataFiles></CDataFileMgr__ContentsOfDataFileXml>"""
    )

    data_file = content.data_files[0]
    assert data_file.overlay is None
    assert data_file.disabled is None
    assert data_file.persistent is None
    serialized = data_file.to_xml_element()
    assert serialized.find("overlay") is None
    assert serialized.find("disabled") is None
    assert serialized.find("persistent") is None


def test_dlc_list_and_extra_title_update_data_roundtrip() -> None:
    dlc_list = DlcList().include("my_pack")
    assert read_dlc_list(dlc_list.to_xml_bytes()).paths == ["dlcpacks:/my_pack/"]

    patches = DlcExtraTitleUpdateData()
    patches.mount("my_pack")
    parsed = read_dlc_extra_title_update_data(patches.to_xml_bytes())

    assert parsed.mounts[0].device_name == "dlc_my_pack:/"
    assert parsed.mounts[0].path == "update:/dlc_patch/my_pack/"


def test_declarative_dlc_pack_builds_dlc_rpf() -> None:
    pack = DlcPack("my_pack", setup=DlcSetupData.compat_pack("my_pack", order=60))
    nested = RpfArchive.empty("props.rpf")
    nested.file("my_prop.bin", b"fake")

    pack.rpf("x64/levels/gta5/props/props.rpf", nested, map_data=True)
    pack.ityp("x64/levels/gta5/props/my_pack.ityp")
    pack.change_set("MY_PACK_AUTOGEN", group=DlcContentGroup.STARTUP)

    archive = pack.to_rpf()
    setup_entry = next(entry for entry in archive.iter_entries() if entry.path == "setup2.xml")
    content_entry = next(entry for entry in archive.iter_entries() if entry.path == "content.xml")

    setup = read_dlc_setup(archive.read_entry_bytes(setup_entry, logical=True))
    content = read_dlc_content(archive.read_entry_bytes(content_entry, logical=True))

    assert setup.name_hash == "my_pack"
    assert setup.content_change_set_groups[0].change_sets == ["MY_PACK_AUTOGEN"]
    assert content.data_files[0].file_type == DlcDataFileType.RPF.value
    assert content.data_files[0].contents == DlcDataFileContents.DLC_MAP_DATA.value
    assert len(content.content_change_sets[0].files_to_enable) == 2


def test_dlc_patch_builds_update_overlay_with_mount_manifest() -> None:
    patch = DlcPatch("my_pack")
    patch.content.rpf("dlc_my_pack:/x64/levels/gta5/LODLights.rpf", map_data=True)
    patch.change_set("MY_PACK_PATCH_MAP", group=DlcContentGroup.MAP)
    patch.file("x64/levels/gta5/LODLights.rpf", RpfArchive.empty("LODLights.rpf"))

    update = patch.to_update_rpf()
    paths = {entry.path for entry in update.iter_entries()}

    assert "common/data/extratitleupdatedata.meta" in paths
    assert "dlc_patch/my_pack/setup2.xml" in paths
    assert "dlc_patch/my_pack/content.xml" in paths
    assert "dlc_patch/my_pack/x64/levels/gta5/LODLights.rpf" in paths


def test_folder_metadata_inference_writes_setup_and_content(tmp_path) -> None:
    folder = tmp_path / "my_pack"
    map_rpf = folder / "x64" / "levels" / "gta5" / "my_pack_metadata" / "my_pack_metadata.rpf"
    ityp = folder / "x64" / "levels" / "gta5" / "props" / "my_pack.ityp"
    dot_file = folder / ".cache" / "ignored.rpf"
    map_rpf.parent.mkdir(parents=True)
    ityp.parent.mkdir(parents=True)
    dot_file.parent.mkdir(parents=True)
    map_rpf.write_bytes(RpfArchive.empty("my_pack_metadata.rpf").to_bytes())
    ityp.write_bytes(b"fake-ityp")
    dot_file.write_bytes(b"ignored")

    metadata = write_dlc_folder_metadata(folder, order=61)

    assert (folder / "setup2.xml").exists()
    assert (folder / "content.xml").exists()
    assert metadata.setup.order == 61
    assert metadata.content.data_files[0].filename.startswith("dlc_my_pack:/")
    assert {item.file_type for item in metadata.content.data_files} == {
        DlcDataFileType.RPF,
        DlcDataFileType.DLC_ITYP_REQUEST,
    }
    assert len(metadata.content.content_change_sets[0].files_to_enable) == 2


def test_folder_metadata_can_use_custom_dat_file_name(tmp_path) -> None:
    folder = tmp_path / "my_pack"
    folder.mkdir()

    metadata = create_dlc_folder_metadata("my_pack", folder, dat_file="context.xml")
    metadata.write(folder)

    assert metadata.setup.dat_file == "context.xml"
    assert (folder / "context.xml").exists()
    assert read_dlc_setup((folder / "setup2.xml").read_bytes()).dat_file == "context.xml"


def test_folder_metadata_rejects_wrong_target_before_writing(tmp_path) -> None:
    folder = tmp_path / "enhanced_pack"
    folder.mkdir()
    (folder / "legacy.ydr").write_bytes(build_rsc7(b"\0" * 16, version=165))

    with pytest.raises(ValidationError, match="asset targets gta5"):
        write_dlc_folder_metadata(folder, game=GameTarget.GTA5_ENHANCED)

    assert not (folder / "setup2.xml").exists()
    assert not (folder / "content.xml").exists()


def test_folder_metadata_validates_loose_enhanced_assets(tmp_path) -> None:
    folder = tmp_path / "enhanced_pack"
    folder.mkdir()
    (folder / "enhanced.ydr").write_bytes(build_rsc7(b"\0" * 16, version=159))

    metadata = write_dlc_folder_metadata(folder, game=GameTarget.GTA5_ENHANCED)
    issues = validate_dlc_folder(folder, game=GameTarget.GTA5_ENHANCED)

    assert metadata.game is GameTarget.GTA5_ENHANCED
    assert issues.valid


def test_folder_asset_validation_ignores_dot_directories(tmp_path) -> None:
    folder = tmp_path / "enhanced_pack"
    hidden = folder / ".cache"
    hidden.mkdir(parents=True)
    (hidden / "legacy.ydr").write_bytes(build_rsc7(b"\0" * 16, version=165))

    write_dlc_folder_metadata(folder, game=GameTarget.GTA5_ENHANCED)

    assert (folder / "setup2.xml").exists()


def test_folder_asset_validation_checks_nested_rpfs(tmp_path) -> None:
    folder = tmp_path / "enhanced_pack"
    folder.mkdir()
    archive = RpfArchive.empty("models.rpf")
    archive.file("legacy.ydr", build_rsc7(b"\0" * 16, version=165))
    archive.save(folder / "models.rpf")

    with pytest.raises(ValidationError, match="models.rpf/legacy.ydr"):
        write_dlc_folder_metadata(folder, game=GameTarget.GTA5_ENHANCED)


def test_folder_asset_validation_rejects_unreadable_rpfs(tmp_path) -> None:
    folder = tmp_path / "enhanced_pack"
    folder.mkdir()
    (folder / "broken.rpf").write_bytes(b"not an rpf")

    with pytest.raises(ValidationError, match="broken.rpf"):
        write_dlc_folder_metadata(folder, game=GameTarget.GTA5_ENHANCED)


def test_folder_asset_validation_rejects_unreadable_nested_rpfs(tmp_path) -> None:
    folder = tmp_path / "enhanced_pack"
    folder.mkdir()
    archive = RpfArchive.empty("outer.rpf")
    archive.file("broken.rpf", b"not an rpf")
    archive.save(folder / "outer.rpf")

    with pytest.raises(ValidationError, match="outer.rpf/broken.rpf"):
        write_dlc_folder_metadata(folder, game=GameTarget.GTA5_ENHANCED)


def test_folder_asset_validation_requires_explicit_target(tmp_path) -> None:
    folder = tmp_path / "pack"
    folder.mkdir()
    metadata = create_dlc_folder_metadata("pack", folder)

    with pytest.raises(ValidationError, match="explicit game target"):
        metadata.write(folder, validate_assets=True)


def test_read_dlc_pack_uses_setup_dat_file_and_validation_reports_missing_references() -> None:
    pack = DlcPack("my_pack", setup=DlcSetupData.compat_pack("my_pack"))
    pack.setup.dat_file = "context.xml"
    pack.content.rpf("dlc_my_pack:/x64/levels/gta5/metadata.rpf", map_data=True)
    pack.content.change_set("BROKEN", enable_all=False).enable("dlc_my_pack:/missing.rpf")
    pack.setup.group(DlcContentGroup.STARTUP, "BROKEN")

    archive = RpfArchive.empty("dlc.rpf")
    archive.file("setup2.xml", pack.setup.to_xml_bytes())
    archive.file("context.xml", pack.content.to_xml_bytes())

    parsed = read_dlc_pack(archive)
    issues = validate_dlc_pack(parsed)

    assert parsed.setup.dat_file == "context.xml"
    assert any(issue.code == "content.change_set.unknown_file" for issue in issues)


def test_dlc_setup_allows_external_change_sets_unless_local_resolution_is_required() -> None:
    setup = DlcSetupData.compat_pack("my_pack")
    setup.startup("BASE_GAME_CHANGE_SET")
    pack = DlcPack("my_pack", setup=setup)

    assert not any(issue.code == "setup.group.missing_change_set" for issue in pack.validate())
    strict = pack.validate(require_local_change_sets=True)
    assert any(issue.code == "setup.group.missing_change_set" for issue in strict)

    resolved = validate_dlc_pack(
        pack,
        require_local_change_sets=True,
        external_change_sets={"BASE_GAME_CHANGE_SET"},
    )
    assert not any(issue.code == "setup.group.missing_change_set" for issue in resolved)


def test_dlc_pack_rejects_resource_target_mismatches_before_writing() -> None:
    legacy_ydr = build_rsc7(b"\0" * 16, version=165)
    pack = DlcPack("enhanced_pack", game=GameTarget.GTA5_ENHANCED)
    pack.file("x64/models/legacy.ydr", legacy_ydr)

    with pytest.raises(ValidationError, match="asset targets gta5"):
        pack.to_rpf()


def test_enhanced_dlc_accepts_legacy_ycd_layouts() -> None:
    pack = DlcPack("enhanced_pack")
    pack.file("x64/anim/legacy.ycd", SimpleNamespace(game=GameTarget.GTA5))

    assert validate_dlc_asset_targets(pack, GameTarget.GTA5_ENHANCED).valid


def test_dlc_pack_writes_target_compatible_assets_with_explicit_open_encryption() -> None:
    enhanced_ydr = build_rsc7(b"\0" * 16, version=159)
    pack = DlcPack(
        "enhanced_pack",
        game=GameTarget.GTA5_ENHANCED,
        rpf_encryption=DlcRpfEncryption.OPEN,
    )
    pack.file("x64/models/enhanced.ydr", enhanced_ydr)

    archive = pack.to_rpf()
    raw = archive.to_bytes()

    assert archive.encryption == DlcRpfEncryption.OPEN
    assert struct.unpack_from("<I", raw, 12)[0] == DlcRpfEncryption.OPEN


def test_read_dlc_pack_preserves_non_metadata_payloads() -> None:
    pack = DlcPack("my_pack")
    pack.file("common/data/custom.meta", b"payload")

    parsed = read_dlc_pack(pack.to_rpf(), load_files=True)

    assert parsed.files == {"common/data/custom.meta": b"payload"}


def test_read_dlc_pack_closes_path_source(tmp_path) -> None:
    source = tmp_path / "dlc.rpf"
    destination = tmp_path / "moved.rpf"
    DlcPack("my_pack").to_rpf().save(source)

    parsed = read_dlc_pack(source)
    source.rename(destination)

    assert parsed.name == "my_pack"
    assert destination.is_file()


def _enhanced_multimip_ytd() -> Ytd:
    size = total_mip_data_size(512, 512, TextureFormat.BC1, 8)
    texture = Texture.from_raw(
        bytes((index * 29) & 0xFF for index in range(size)),
        512,
        512,
        TextureFormat.BC1,
        8,
        name="head_diff_000_a_whi",
        usage=TextureUsage.DIFFUSE,
    )
    return Ytd([texture], game=GameTarget.GTA5_ENHANCED)


def test_ytd_rejects_invalid_mip_payload_before_replacing_destination(tmp_path) -> None:
    ytd = _enhanced_multimip_ytd()
    ytd.textures[0].data = ytd.textures[0].data[:-8]
    destination = tmp_path / "head.ytd"
    destination.write_bytes(b"existing")

    with pytest.raises(ValidationError, match="ytd.texture.data.size.invalid"):
        ytd.save(destination)

    assert destination.read_bytes() == b"existing"


def test_ytd_rejects_noncanonical_mip_offsets() -> None:
    ytd = _enhanced_multimip_ytd()
    ytd.textures[0].mip_offsets = (0,) * 8

    with pytest.raises(ValidationError, match="ytd.texture.mips.offsets.invalid"):
        ytd.to_bytes()


def test_enhanced_multimip_ytd_packages_in_streamed_and_dlc_rpfs() -> None:
    ytd_payload = _enhanced_multimip_ytd().to_bytes()
    streamed = RpfArchive.empty("streamedpeds.rpf")
    streamed.file("head_diff_000_a_whi.ytd", ytd_payload)

    streamed_copy = RpfArchive.from_bytes(streamed.to_bytes(), name="streamedpeds.rpf")
    streamed_entry = streamed_copy.find_entry("head_diff_000_a_whi.ytd")
    assert streamed_entry is not None
    assert streamed_copy.read_entry_standalone(streamed_entry) == ytd_payload

    dlc = DlcPack("ped_textures", game=GameTarget.GTA5_ENHANCED)
    dlc.file("x64/models/cdimages/streamedpeds.rpf", streamed.to_bytes())
    dlc_copy = RpfArchive.from_bytes(dlc.to_rpf().to_bytes(), name="dlc.rpf", load_nested=True)
    nested_entry = dlc_copy.find_entry(
        "x64/models/cdimages/streamedpeds.rpf/head_diff_000_a_whi.ytd"
    )
    assert nested_entry is not None
    assert dlc_copy.children[0].read_entry_standalone(nested_entry) == ytd_payload
