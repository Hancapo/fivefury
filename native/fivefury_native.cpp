#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstring>
#include <string>
#include <vector>

#include "rpf_index.h"
#include "rpf_scan.h"

namespace py = pybind11;
using namespace fivefury_native;

namespace {

py::dict export_state(const CompactIndex& index) {
    const auto kinds = index.export_kinds();
    const auto sizes = index.export_sizes();
    const auto uncompressed_sizes = index.export_uncompressed_sizes();
    const auto flags = index.export_flags();
    const auto archive_encryptions = index.export_archive_encryptions();
    const auto name_hashes = index.export_name_hashes();
    const auto short_hashes = index.export_short_hashes();
    py::dict state;
    state["paths"] = index.export_paths();
    state["kinds"] = py::bytes(
        reinterpret_cast<const char*>(kinds.data()),
        static_cast<py::ssize_t>(kinds.size() * sizeof(std::int32_t))
    );
    state["sizes"] = py::bytes(
        reinterpret_cast<const char*>(sizes.data()),
        static_cast<py::ssize_t>(sizes.size() * sizeof(std::uint64_t))
    );
    state["uncompressed_sizes"] = py::bytes(
        reinterpret_cast<const char*>(uncompressed_sizes.data()),
        static_cast<py::ssize_t>(uncompressed_sizes.size() * sizeof(std::uint64_t))
    );
    state["flags"] = py::bytes(
        reinterpret_cast<const char*>(flags.data()),
        static_cast<py::ssize_t>(flags.size() * sizeof(std::uint8_t))
    );
    state["archive_encryptions"] = py::bytes(
        reinterpret_cast<const char*>(archive_encryptions.data()),
        static_cast<py::ssize_t>(archive_encryptions.size() * sizeof(std::uint32_t))
    );
    state["name_hashes"] = py::bytes(
        reinterpret_cast<const char*>(name_hashes.data()),
        static_cast<py::ssize_t>(name_hashes.size() * sizeof(std::uint32_t))
    );
    state["short_hashes"] = py::bytes(
        reinterpret_cast<const char*>(short_hashes.data()),
        static_cast<py::ssize_t>(short_hashes.size() * sizeof(std::uint32_t))
    );
    return state;
}

template <typename T>
std::vector<T> vector_from_bytes(const py::bytes& payload) {
    const std::string data = payload;
    if (data.size() % sizeof(T) != 0) {
        throw std::invalid_argument("invalid byte length for native vector");
    }
    std::vector<T> result(data.size() / sizeof(T));
    if (!result.empty()) {
        std::memcpy(result.data(), data.data(), data.size());
    }
    return result;
}

std::vector<std::uint8_t> byte_vector_from_pybytes(const py::bytes& payload) {
    const std::string data = payload;
    return std::vector<std::uint8_t>(data.begin(), data.end());
}

void import_state(CompactIndex& index, const py::dict& state) {
    index.import_columns(
        state["paths"].cast<std::vector<std::string>>(),
        vector_from_bytes<std::int32_t>(state["kinds"].cast<py::bytes>()),
        vector_from_bytes<std::uint64_t>(state["sizes"].cast<py::bytes>()),
        vector_from_bytes<std::uint64_t>(state["uncompressed_sizes"].cast<py::bytes>()),
        vector_from_bytes<std::uint8_t>(state["flags"].cast<py::bytes>()),
        vector_from_bytes<std::uint32_t>(state["archive_encryptions"].cast<py::bytes>()),
        vector_from_bytes<std::uint32_t>(state["name_hashes"].cast<py::bytes>()),
        vector_from_bytes<std::uint32_t>(state["short_hashes"].cast<py::bytes>())
    );
}

}  // namespace

PYBIND11_MODULE(_native, module) {
    module.doc() = "Native backend for fivefury";

    py::class_<AssetRecordData>(module, "NativeAssetRecord")
        .def_readonly("path", &AssetRecordData::path)
        .def_readonly("kind", &AssetRecordData::kind)
        .def_readonly("size", &AssetRecordData::size)
        .def_readonly("uncompressed_size", &AssetRecordData::uncompressed_size)
        .def_readonly("flags", &AssetRecordData::flags)
        .def_readonly("archive_encryption", &AssetRecordData::archive_encryption)
        .def_readonly("name_hash", &AssetRecordData::name_hash)
        .def_readonly("short_hash", &AssetRecordData::short_hash);

    py::class_<CompactIndex>(module, "CompactIndex")
        .def(py::init<>())
        .def("__len__", &CompactIndex::count)
        .def("clear", &CompactIndex::clear)
        .def(
            "add",
            &CompactIndex::add,
            py::arg("path"),
            py::arg("kind"),
            py::arg("size"),
            py::arg("uncompressed_size"),
            py::arg("flags") = 0,
            py::arg("archive_encryption") = 0,
            py::arg("name_hash") = 0,
            py::arg("short_hash") = 0
        )
        .def("find_path_id", &CompactIndex::find_path_id)
        .def("find_hash_ids", &CompactIndex::find_hash_ids)
        .def("find_kind_ids", &CompactIndex::find_kind_ids)
        .def("get_path", &CompactIndex::get_path)
        .def("get_kind", &CompactIndex::get_kind)
        .def("get_size", &CompactIndex::get_size)
        .def("get_uncompressed_size", &CompactIndex::get_uncompressed_size)
        .def("get_flags", &CompactIndex::get_flags)
        .def("get_archive_encryption", &CompactIndex::get_archive_encryption)
        .def("get_name_hash", &CompactIndex::get_name_hash)
        .def("get_short_hash", &CompactIndex::get_short_hash)
        .def("get_record", &CompactIndex::get_record)
        .def("export_state", &export_state)
        .def("import_state", &import_state);

    py::class_<NativeCryptoContext>(module, "NativeCryptoContext")
        .def(
            py::init([](const py::bytes& aes_key, const py::bytes& ng_blob) {
                return NativeCryptoContext(byte_vector_from_pybytes(aes_key), byte_vector_from_pybytes(ng_blob));
            }),
            py::arg("aes_key"),
            py::arg("ng_blob")
        )
        .def("can_decrypt", &NativeCryptoContext::can_decrypt);

    module.def(
        "scan_rpf_into_index",
        [](CompactIndex& index,
           const std::string& path,
           const std::string& source_prefix,
           const py::bytes& hash_lut,
           const NativeCryptoContext* crypto) {
            const std::string lut = hash_lut;
            py::gil_scoped_release release;
            return scan_rpf_into_index(index, path, source_prefix, lut, crypto);
        },
        py::arg("index"),
        py::arg("path"),
        py::arg("source_prefix"),
        py::arg("hash_lut"),
        py::arg("crypto") = nullptr
    );
}
