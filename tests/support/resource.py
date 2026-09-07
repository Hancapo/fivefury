import struct

from fivefury.resource import get_resource_chunks, split_rsc7_sections


class ScatteredResource:
    """Place chunks in reversed allocation order with unmapped gaps."""

    def __init__(self, raw):
        header, system, graphics = split_rsc7_sections(raw)
        chunks = get_resource_chunks(header)
        stride = max(chunk.size for chunk in chunks) + 0x10000
        self.allocations = []
        for index, chunk in enumerate(chunks):
            source = system if chunk.section == "system" else graphics
            self.allocations.append(
                (
                    chunk.address,
                    0x100000000 + (len(chunks) - index) * stride,
                    bytearray(
                        source[chunk.section_offset : chunk.section_offset + chunk.size]
                    ),
                )
            )

    def relocate(self, pointer):
        if not pointer:
            return 0
        for logical, native, data in self.allocations:
            if logical <= pointer < logical + len(data):
                return native + pointer - logical
        raise AssertionError(f"Unmapped resource pointer {pointer:#x}")

    def _region(self, address, size):
        for _, native, data in self.allocations:
            if native <= address < native + len(data):
                offset = address - native
                assert offset + size <= len(data), (
                    "Native access crosses an allocation gap"
                )
                return data, offset
        raise AssertionError(f"Unmapped native pointer {address:#x}")

    def read(self, address, size):
        data, offset = self._region(address, size)
        return bytes(data[offset : offset + size])

    def fixup(self, logical_field):
        data, offset = self._region(self.relocate(logical_field), 8)
        pointer = struct.unpack_from("<Q", data, offset)[0]
        struct.pack_into("<Q", data, offset, self.relocate(pointer))
