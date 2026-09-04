from __future__ import annotations

from fivefury import (
    YED_FACIAL_ROOT_BONE_ID,
    AssetSet,
    Awc,
    AwcChunk,
    AwcChunkType,
    AwcFormat,
    AwcStream,
    BuildContext,
    CutCameraCutPayload,
    CutFacialAnimationMode,
    CutLoadScenePayload,
    CutScene,
    CutsceneAssets,
    Dat54SimpleSound,
    MetaHash,
    PedExpressionSetMetadata,
    RelDatFileType,
    RelFile,
    Ydd,
    Ydr,
    YdrSkeleton,
    YedExpression,
    Ymt,
    YmtPedInitData,
    YmtPedMetadata,
    Ytyp,
    create_yed,
    read_ped_expression_sets,
)
from fivefury.cut.audio_references import cut_audio_sound_hashes
from fivefury.hashing import jenk_hash


def _playable_scene(name: str) -> tuple[CutScene, object]:
    scene = CutScene.create(scene_name=name, duration=2.0)
    asset_manager = scene.asset_manager()
    camera = scene.camera("camera")
    scene.load_scene(0.0, CutLoadScenePayload(name), target=asset_manager)
    scene.camera_cut(0.0, camera, CutCameraCutPayload("camera"))
    return scene, asset_manager


def _audio_context(
    *,
    stream_name: str = "scene_voice",
    container_name: str | int = "scene_bank",
    awc_path: str = "audio/scene_bank.awc",
) -> BuildContext:
    root_hash = cut_audio_sound_hashes("intro.wav")[0]
    rel = RelFile(
        RelDatFileType.DAT54_DATA_ENTRIES,
        items=[
            Dat54SimpleSound(
                name_hash=root_hash,
                container_name=container_name,
                file_name="scene_voice",
            )
        ],
    )
    assets = AssetSet()
    assets["audio/cutscene_sounds.rel"] = rel
    assets[awc_path] = Awc(
        [
            AwcStream(
                stream_name,
                [
                    AwcChunk(
                        AwcChunkType.FORMAT,
                        format=AwcFormat(samples=2, sample_rate=48000),
                    ),
                    AwcChunk(AwcChunkType.DATA, data=b"\0\0\0\0"),
                ],
            )
        ]
    )
    return BuildContext(assets=assets)


def _audio_cutscene() -> CutsceneAssets:
    scene, _asset_manager = _playable_scene("audio_scene")
    audio = scene.audio("intro.wav")
    scene.load_audio(0.0, "event_label_is_not_the_sound", target=audio)
    scene.play_audio(0.0, audio, "event_label_is_not_the_sound")
    return CutsceneAssets(scene)


def test_cutscene_context_validates_rel_to_awc_sound_graph() -> None:
    report = _audio_cutscene().validate(context=_audio_context())

    assert report.valid


def test_cutscene_context_reports_missing_rel_awc_stream() -> None:
    report = _audio_cutscene().validate(
        context=_audio_context(stream_name="another_stream")
    )

    assert any(issue.code == "cut.audio.stream.unresolved" for issue in report.errors)


def test_cutscene_context_treats_rel_bank_name_as_metadata_reference() -> None:
    report = _audio_cutscene().validate(
        context=_audio_context(
            container_name=0x91ECFC6A,
            awc_path="audio/intro_mastered_only.awc",
        )
    )

    assert report.valid


def _expression_sets() -> PedExpressionSetMetadata:
    return read_ped_expression_sets(
        """\
<fwExpressionSetManager>
  <expressionSets>
    <Item type="fwExpressionSet" key="ped_face_set">
      <dictionaryName>ped_face_expressions</dictionaryName>
      <expressions><Item>facial</Item></expressions>
    </Item>
  </expressionSets>
</fwExpressionSetManager>
"""
    )


def _facial_cutscene() -> CutsceneAssets:
    scene, asset_manager = _playable_scene("facial_scene")
    ped = scene.ped(
        "ped_face",
        model_name="ped_face",
        ytyp_name="ped_pack",
        animation_clip_base="ped_face",
        facial_animation=CutFacialAnimationMode.MERGED,
    )
    scene.load_models(0.0, [ped.object_id], target=asset_manager)
    return CutsceneAssets(scene)


def _facial_context(*, expression_name: str = "facial") -> BuildContext:
    skeleton = YdrSkeleton()
    skeleton.bone("facial_root", tag=YED_FACIAL_ROOT_BONE_ID)
    drawable = Ydr(version=165, skeleton=skeleton)
    ydd = Ydd.from_drawables({"ped_face": drawable}, name="ped_components")
    ytyp = Ytyp(name="ped_pack")
    ytyp.archetype("ped_face")
    ymt = Ymt(
        content=YmtPedMetadata(
            init_datas=[
                YmtPedInitData(
                    name=MetaHash("ped_face"),
                    expression_set_name=MetaHash("ped_face_set"),
                )
            ]
        )
    )
    assets = AssetSet()
    assets["stream/ped_components.ydd"] = ydd
    assets["stream/ped_pack.ytyp"] = ytyp
    assets["data/peds.ymt"] = ymt
    assets["data/expression_sets.xml"] = _expression_sets()
    assets["anim/ped_face_expressions.yed"] = create_yed(
        YedExpression.create(expression_name)
    )
    return BuildContext(assets=assets)


def test_cutscene_context_validates_ped_expression_assets() -> None:
    report = _facial_cutscene().validate(context=_facial_context())

    assert report.valid


def test_cutscene_context_reports_missing_yed_expression() -> None:
    report = _facial_cutscene().validate(
        context=_facial_context(expression_name="another_expression")
    )

    assert any(
        issue.code == "cut.binding.yed.expression_unresolved"
        for issue in report.errors
    )


def test_cutscene_audio_runtime_hash_uses_audio_object_name() -> None:
    candidates = cut_audio_sound_hashes("intro.wav")

    assert candidates[0] == jenk_hash("CUTSCENES_INTRO")
