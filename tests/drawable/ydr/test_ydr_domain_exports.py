from __future__ import annotations

import importlib
import inspect
import pickle
import subprocess
import sys
from pathlib import Path
from typing import get_type_hints

import pytest

import fivefury
from fivefury import ydr
from fivefury.drawable.model import NumericParameterValue
from fivefury.matrix import Matrix4
from fivefury.ydr import model, prepare
from fivefury.ydr.prepare.material import MaterialPreparer


@pytest.mark.parametrize("name", model.__all__)
def test_model_exports_are_direct_domain_objects(name: str) -> None:
    value = getattr(model, name)
    if name in (
        "Matrix4",
        "NumericParameterValue",
        "Color4",
        "YDR_BONE_ANIMATABLE_FLAGS",
    ):
        return
    owner = importlib.import_module(value.__module__)
    assert getattr(owner, name) is value
    assert getattr(ydr, name) is value
    assert getattr(fivefury, name) is value


def test_shared_type_aliases_have_one_owner() -> None:
    assert model.Matrix4 is Matrix4
    assert model.NumericParameterValue is NumericParameterValue
    assert get_type_hints(model.YdrBone)["inverse_bind_transform"] == Matrix4 | None
    assert (
        get_type_hints(model.YdrMaterialParameterRef)["value"]
        == NumericParameterValue | None
    )


@pytest.mark.parametrize("name", prepare.__all__)
def test_preparation_exports_are_direct_domain_objects(name: str) -> None:
    value = getattr(prepare, name)
    if name == "PreparedLods":
        from fivefury.ydr.prepare.build import PreparedLods

        assert value is PreparedLods
        return
    owner = importlib.import_module(value.__module__)
    assert owner.__name__.startswith("fivefury.ydr.prepare.")
    assert getattr(owner, name) is value
    if inspect.isfunction(value):
        assert all(
            parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
            for parameter in inspect.signature(value).parameters.values()
        )


@pytest.mark.parametrize("module", [model, prepare])
def test_public_annotations_resolve_without_injected_namespaces(module) -> None:
    for name in module.__all__:
        value = getattr(module, name)
        if inspect.isclass(value) or inspect.isfunction(value):
            get_type_hints(value)
        if inspect.isclass(value):
            for member_name, member in vars(value).items():
                if member_name.startswith("_"):
                    continue
                if isinstance(member, property):
                    get_type_hints(member.fget)
                elif inspect.isfunction(member) or isinstance(
                    member, (classmethod, staticmethod)
                ):
                    get_type_hints(getattr(value, member_name))
    get_type_hints(MaterialPreparer.__call__)


def test_canonical_preparation_api_has_no_obsolete_aliases() -> None:
    from fivefury.ydr import builder

    assert "resolve_shader" not in vars(prepare)
    assert "_prepare_meshes" not in vars(prepare)
    assert "_select_layout" not in vars(builder)
    assert "_normalize_materials" not in vars(builder)


@pytest.mark.parametrize(
    "name", ["Ydr", "YdrBone", "YdrSkeleton", "YdrMaterial", "YdrMesh"]
)
def test_public_pickle_global_path_still_resolves(name: str) -> None:
    reference = f"cfivefury.ydr.model\n{name}\n.".encode("ascii")
    assert pickle.loads(reference) is getattr(model, name)


@pytest.mark.parametrize(
    "first",
    [
        "fivefury.ydr.model.skeleton.lookups",
        "fivefury.ydr.prepare.channels",
        "fivefury.ydr.reader",
        "fivefury.ydd.writer",
        "fivefury.yft.writer",
        "fivefury.cdr",
    ],
)
def test_fresh_imports_use_the_parent_installation(first: str, tmp_path: Path) -> None:
    package_root = str(Path(fivefury.__file__).resolve().parent.parent)
    script = """
import importlib, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
importlib.import_module(sys.argv[2])
import fivefury
from fivefury.ydr import YdrSkeleton, model, prepare
assert Path(fivefury.__file__).resolve().parent.parent == Path(sys.argv[1])
assert YdrSkeleton is model.YdrSkeleton
assert prepare.prepare_meshes.__module__ == 'fivefury.ydr.prepare.mesh'
"""
    subprocess.run(
        [sys.executable, "-I", "-c", script, package_root, first],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
