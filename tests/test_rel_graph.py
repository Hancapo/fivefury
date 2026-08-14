from __future__ import annotations

from fivefury import (
    Dat54LoopingSound,
    Dat54SimpleSound,
    RelDatFileType,
    RelFile,
    RelSoundIndex,
    jenk_hash,
)


def test_rel_sound_graph_resolves_nested_awc_endpoint() -> None:
    root_hash = jenk_hash("root_sound")
    leaf_hash = jenk_hash("leaf_sound")
    container_hash = jenk_hash("scene_bank")
    stream_hash = jenk_hash("scene_voice")
    rel = RelFile(
        RelDatFileType.DAT54_DATA_ENTRIES,
        items=[
            Dat54LoopingSound(name_hash=root_hash, child_sound=leaf_hash),
            Dat54SimpleSound(
                name_hash=leaf_hash,
                container_name=container_hash,
                file_name=stream_hash,
            ),
        ],
    )

    graph = RelSoundIndex([rel]).resolve(root_hash)

    assert graph.complete
    assert graph.sound_hashes == (root_hash, leaf_hash)
    assert [
        (endpoint.sound_hash, endpoint.container_hash, endpoint.stream_hash)
        for endpoint in graph.endpoints
    ] == [(leaf_hash, container_hash, stream_hash)]
    assert graph.container_hashes == (container_hash,)
    assert graph.stream_hashes == (stream_hash,)


def test_rel_sound_graph_reports_missing_children() -> None:
    root_hash = jenk_hash("root_sound")
    missing_hash = jenk_hash("missing_sound")
    rel = RelFile(
        RelDatFileType.DAT54_DATA_ENTRIES,
        items=[Dat54LoopingSound(name_hash=root_hash, child_sound=missing_hash)],
    )

    graph = RelSoundIndex([rel]).resolve(root_hash)

    assert not graph.complete
    assert graph.sound_hashes == (root_hash,)
    assert graph.unresolved_hashes == (missing_hash,)


def test_rel_sound_graph_handles_cycles_once() -> None:
    first_hash = jenk_hash("first_sound")
    second_hash = jenk_hash("second_sound")
    rel = RelFile(
        RelDatFileType.DAT54_DATA_ENTRIES,
        items=[
            Dat54LoopingSound(name_hash=first_hash, child_sound=second_hash),
            Dat54LoopingSound(name_hash=second_hash, child_sound=first_hash),
        ],
    )

    graph = RelSoundIndex([rel]).resolve(first_hash)

    assert graph.complete
    assert graph.sound_hashes == (first_hash, second_hash)
    assert graph.unresolved_hashes == ()
