from __future__ import annotations

import os

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class NativeBuildExt(build_ext):
    def finalize_options(self) -> None:
        super().finalize_options()
        self.force = True

ext_modules = [
    Extension(
        "fivefury._native_abi3",
        [
            "native/py_bindings.cpp",
            "native/py_awc.cpp",
            "native/py_yed.cpp",
            "native/py_ycd.cpp",
            "native/yed_vm.cpp",
            "native/py_bounds.cpp",
            "native/py_resource.cpp",
            "native/bounds_algorithms.cpp",
            "native/bounds_python.cpp",
            "native/crypto_magic.cpp",
            "native/resource_layout.cpp",
            "native/py_index.cpp",
            "native/py_crypto.cpp",
            "native/py_rpf.cpp",
            "native/py_vertex.cpp",
            "native/py_module.cpp",
            "native/rpf_archive.cpp",
            "native/rpf_crypto.cpp",
            "native/rpf_index.cpp",
            "native/rpf_read.cpp",
            "native/rpf_scan.cpp",
        ],
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
