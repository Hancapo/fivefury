#pragma once

#include <Python.h>

#include <vector>

#include "bounds_types.h"

namespace fivefury_py {

bool parse_vector3(PyObject* object, fivefury_native::bounds::Vec3& out, const char* argument_name);
bool parse_vertices(PyObject* object, std::vector<fivefury_native::bounds::Vec3>& out, const char* argument_name);
bool parse_triangles(PyObject* object, std::vector<fivefury_native::bounds::Triangle>& out);
bool parse_bvh_items(PyObject* object, std::vector<fivefury_native::bounds::BvhItem>& out);

PyObject* build_vector3(const fivefury_native::bounds::Vec3& value);
PyObject* build_u32_list(const std::vector<std::uint32_t>& values);
PyObject* build_octant_list(const std::array<std::vector<std::uint32_t>, 8>& octants);
PyObject* build_bvh_nodes(const std::vector<fivefury_native::bounds::BvhNodeOutput>& nodes);
PyObject* build_bvh_trees(const std::vector<fivefury_native::bounds::BvhTreeOutput>& trees);
PyObject* build_chunk_list(const std::vector<fivefury_native::bounds::TriangleChunk>& chunks);

}  // namespace fivefury_py
