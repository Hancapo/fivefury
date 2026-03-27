from __future__ import annotations

from pybind11 import get_include
from setuptools import Extension, setup

ext_modules = [
    Extension(
        "fivefury._native",
        [
            "native/fivefury_native.cpp",
            "native/rpf_index.cpp",
            "native/rpf_scan.cpp",
        ],
        include_dirs=["native", get_include()],
        language="c++",
        extra_compile_args=["/std:c++20"] if __import__("os").name == "nt" else ["-std=c++20"],
        libraries=["bcrypt"] if __import__("os").name == "nt" else [],
    )
]


setup(
    ext_modules=ext_modules,
)
