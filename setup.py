from __future__ import annotations

import os
from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class NativeBuildExt(build_ext):
    def finalize_options(self) -> None:
        super().finalize_options()
        self.force = True


NATIVE_SOURCE_GROUPS = {
    "python": ("bridge.cpp", "module.cpp"),
    "audio": ("bindings.cpp",),
    "animation": (
        "ycd_bindings.cpp",
        "ycd_sampling.cpp",
        "ycd_precision.cpp",
        "yed_bindings.cpp",
        "yed_vm.cpp",
    ),
    "bounds": (
        "algorithms.cpp",
        "bindings.cpp",
        "python_conversions.cpp",
    ),
    "crypto": ("bindings.cpp", "magic.cpp"),
    "drawable": (
        "skinning.cpp",
        "vector_bindings.cpp",
        "vertex_bindings.cpp",
        "vertex_decode.cpp",
    ),
    "indexing": (
        "compact_index.cpp",
        "hash.cpp",
        "index_bindings.cpp",
        "meta_bindings.cpp",
        "texture_bindings.cpp",
        "texture_index.cpp",
    ),
    "resource": ("binary_document.cpp", "bindings.cpp", "layout.cpp"),
    "rpf": ("archive.cpp", "bindings.cpp", "crypto.cpp", "read.cpp", "read_session.cpp", "scan.cpp"),
    "spatial": ("bindings.cpp",),
}

NATIVE_SOURCES = [
    str(Path("native", domain, source))
    for domain, sources in NATIVE_SOURCE_GROUPS.items()
    for source in sources
]


ext_modules = [
    Extension(
        "fivefury._native_abi3",
        NATIVE_SOURCES,
        include_dirs=["native"],
        define_macros=[
            ("PY_SSIZE_T_CLEAN", None),
            ("Py_LIMITED_API", "0x030B0000"),
        ],
        py_limited_api=True,
        language="c++",
        extra_compile_args=["/std:c++20"] if os.name == "nt" else ["-std=c++20"],
        libraries=["bcrypt"] if os.name == "nt" else [],
    )
]


setup(
    cmdclass={"build_ext": NativeBuildExt},
    ext_modules=ext_modules,
    options={"bdist_wheel": {"py_limited_api": "cp311"}},
)
