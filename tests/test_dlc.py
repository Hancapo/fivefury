from __future__ import annotations

from fivefury import (
    DlcContentGroup,
    DlcDataFileContents,
    DlcDataFileType,
    DlcExtraTitleUpdateData,
    DlcList,
    DlcPack,
    DlcPatch,
    DlcSetupData,
    RpfArchive,
    create_dlc_folder_metadata,
    read_dlc_pack,
    read_dlc_content,
    read_dlc_extra_title_update_data,
    read_dlc_list,
    read_dlc_setup,
    validate_dlc_pack,
    write_dlc_folder_metadata,
)


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
    nested.add_file("my_prop.ydr", b"fake")

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


def test_read_dlc_pack_uses_setup_dat_file_and_validation_reports_missing_references() -> None:
    pack = DlcPack("my_pack", setup=DlcSetupData.compat_pack("my_pack"))
    pack.setup.dat_file = "context.xml"
    pack.content.rpf("dlc_my_pack:/x64/levels/gta5/metadata.rpf", map_data=True)
    pack.content.change_set("BROKEN", enable_all=False).enable("dlc_my_pack:/missing.rpf")
    pack.setup.group(DlcContentGroup.STARTUP, "BROKEN")

    archive = RpfArchive.empty("dlc.rpf")
    archive.add_file("setup2.xml", pack.setup.to_xml_bytes())
    archive.add_file("context.xml", pack.content.to_xml_bytes())

    parsed = read_dlc_pack(archive)
    issues = validate_dlc_pack(parsed)

    assert parsed.setup.dat_file == "context.xml"
    assert any(issue.code == "content.change_set.unknown_file" for issue in issues)
