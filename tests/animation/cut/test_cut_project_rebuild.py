from fivefury import CutsceneProject, Quaternion, Vector3


def test_project_rebuild_includes_new_actors_without_duplicate_cleanup():
    project = CutsceneProject.create("rebuild", duration=2)
    project.camera(position=Vector3(), rotation=Quaternion())
    project.build()
    actor = project.scene.prop("actor", model_name="actor", ytyp_name="actors")
    project.animate(actor, mover_position=Vector3(), mover_rotation=Quaternion())
    first = project.build().build_files()
    second = project.build().build_files()
    assert first == second
    clears = [
        event for event in project.scene.timeline if event.event_name == "clear_anim"
    ]
    assert len(clears) == 2
    assert actor.object_id in {event.payload["iObjectId"] for event in clears}


def test_project_rebuild_refreshes_timing_and_reference_preserving_manual_events():
    project = CutsceneProject.create("rebuild", duration=3)
    camera = project.camera(position=Vector3(), rotation=Quaternion())
    project.build()
    manual = project.scene.clear_anim(0.5, camera, target=project.animation_manager)
    project.scene.set_anim(1, camera, target=project.animation_manager)
    project.scene.duration = 2
    project.scene.camera_cut_list = [1]
    project.scene.animation_dictionary.reference = "new_dict"
    assets = project.build()
    assert any(event is manual for event in assets.scene.timeline)
    assert assets.validate().valid
    assert len(assets.scene.animation_dictionary.sections) == 2
    clears = [
        event.start
        for event in assets.scene.timeline
        if event.event_name == "clear_anim"
    ]
    assert clears == [0.5, 2]
    dictionary_events = [
        event
        for event in assets.scene.timeline
        if event.event_name in {"load_anim_dict", "unload_anim_dict"}
    ]
    assert [event.label for event in dictionary_events] == ["new_dict", "new_dict"]
    assert assets.build_files()["rebuild.cut"]
