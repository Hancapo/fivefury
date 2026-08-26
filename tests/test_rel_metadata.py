from __future__ import annotations

import pytest

from fivefury import BuildContext, DlcDataFileType, DlcPack, GameTarget, RpfArchive
from fivefury.rel import (
    Dat54SimpleSound,
    Dat54StreamingSound,
    RelDatFileType,
    RelExternalNameTable,
    RelFile,
    RelMetadataChunk,
    RelSoundIndex,
    read_rel,
    rel_hash,
)


def _rel() -> RelFile:
    child_name = "CUTSCENES_EXAMPLE_STREAM_1"
    root_name = "CUTSCENES_EXAMPLE_MASTERED_ONLY"
    return RelFile(
        RelDatFileType.DAT54_DATA_ENTRIES,
        items=[
            Dat54StreamingSound(
                name_hash=rel_hash(root_name),
                name=root_name,
                child_sounds=[rel_hash(child_name)],
                duration=1000,
            ),
            Dat54SimpleSound(
                name_hash=rel_hash(child_name),
                name=child_name,
                container_name="example_audio/example",
                file_name="example_stream",
            ),
        ],
        name_table=["example_audio/example"],
    )


@pytest.mark.parametrize("game", (GameTarget.GTA5, GameTarget.GTA5_ENHANCED))
def test_rel_metadata_chunk_builds_complete_dat54_family(game: GameTarget) -> None:
    chunk = RelMetadataChunk.from_rel(
        "example_sounds.dat",
        _rel(),
        context=BuildContext(game=game),
    )

    assert chunk.runtime_name == "example_sounds.dat54"
    assert chunk.release_name == "example_sounds.dat54.rel"
    assert chunk.name_table_name == "example_sounds.dat54.nametable"
    assert set(chunk.payloads) == {
        chunk.runtime_name,
        chunk.release_name,
        chunk.name_table_name,
    }
    assert chunk.validate(context=BuildContext(game=game)).valid
    assert read_rel(chunk.release_payload).to_bytes() == chunk.release_payload
    assert (
        RelExternalNameTable.from_bytes(chunk.name_table.to_bytes()) == chunk.name_table
    )

    graph = RelSoundIndex((read_rel(chunk.release_payload),)).resolve(
        "CUTSCENES_EXAMPLE_MASTERED_ONLY"
    )
    assert graph.complete
    assert graph.container_hashes == (rel_hash("example_audio/example"),)


def test_rel_metadata_chunk_rejects_missing_or_incorrect_object_names() -> None:
    rel = _rel()
    rel.items[0].name = None
    with pytest.raises(ValueError, match="requires an external object name"):
        RelMetadataChunk.from_rel(
            "example_sounds.dat",
            rel,
            context=BuildContext(),
        )

    rel = _rel()
    rel.items[0].name = "WRONG_NAME"
    with pytest.raises(ValueError, match="does not match hash"):
        RelMetadataChunk.from_rel(
            "example_sounds.dat",
            rel,
            context=BuildContext(),
        )


def test_rel_metadata_validation_detects_sidecar_and_runtime_corruption() -> None:
    chunk = RelMetadataChunk.from_rel(
        "example_sounds.dat",
        _rel(),
        context=BuildContext(),
    )
    wrong_names = RelMetadataChunk(
        chunk.logical_name,
        chunk.schema,
        chunk.runtime_payload,
        chunk.release_payload,
        RelExternalNameTable(("WRONG", *chunk.name_table.names[1:])),
    )
    wrong_runtime = RelMetadataChunk(
        chunk.logical_name,
        chunk.schema,
        chunk.runtime_payload[:-1],
        chunk.release_payload,
        chunk.name_table,
    )

    assert "rel.metadata.names.hash_mismatch" in {
        issue.code for issue in wrong_names.validate().errors
    }
    assert "rel.metadata.runtime.invalid" in {
        issue.code for issue in wrong_runtime.validate().errors
    }


def test_rel_external_name_table_rejects_invalid_encoding() -> None:
    with pytest.raises(ValueError, match="NUL-terminated"):
        RelExternalNameTable.from_bytes(b"NOT_TERMINATED")
    with pytest.raises(ValueError, match="non-ASCII"):
        RelExternalNameTable.from_bytes(b"\xff\x00")


@pytest.mark.parametrize("game", (GameTarget.GTA5, GameTarget.GTA5_ENHANCED))
def test_dlc_mounts_rel_metadata_without_cutscene(
    game: GameTarget,
) -> None:
    chunk = RelMetadataChunk.from_rel(
        "ambient_sounds.dat",
        _rel(),
        context=BuildContext(game=game),
    )
    pack = DlcPack("ambient_audio", game=game)
    registration = pack.mount_sounddata(chunk)

    assert not pack.cutscenes
    assert registration.logical_registration == (
        "dlc_ambient_audio:/%PLATFORM%/audio/ambient_sounds.dat"
    )
    content_file = next(
        item
        for item in pack.content.data_files
        if item.filename == registration.logical_registration
    )
    assert content_file.file_type == DlcDataFileType.AUDIO_SOUNDDATA.value

    rebuilt = RpfArchive.from_bytes(pack.to_bytes(), load_nested=True)
    assert all(
        rebuilt.find_entry(path) is not None for path in registration.payload_paths
    )
    rebuilt.close()
