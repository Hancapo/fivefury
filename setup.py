from __future__ import annotations

import os

from setuptools import Extension, setup

ext_modules = [
    Extension(
        "fivefury._native_abi3",
        [
            "native/py_bindings.cpp",
            "native/py_index.cpp",
            "native/py_crypto.cpp",
            "native/py_rpf.cpp",
            "native/py_module.cpp",
            "native/rpf_index.cpp",
            "native/rpf_scan.cpp",
        ],
        include_dirs=["native"],
        define_macros=[("Py_LIMITED_API", "0x030B0000")],
        py_limited_api=True,
        language="c++",
        extra_compile_args=["/std:c++20"] if os.name == "nt" else ["-std=c++20"],
        libraries=["bcrypt"] if os.name == "nt" else [],
    )
]


setup(
    ext_modules=ext_modules,
    options={"bdist_wheel": {"py_limited_api": "cp311"}},
)
