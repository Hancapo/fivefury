from unittest.mock import patch

import pytest

import fivefury.resource as resource
from fivefury import GameFileCache, RpfArchive, Vector2, Vector3, YdrMeshInput, create_ydr


@pytest.mark.parametrize("native", (False, True))
def test_cached_ydr_decompresses_once(tmp_path, native):
    mesh = YdrMeshInput(
        positions=[Vector3(), Vector3(1, 0, 0), Vector3(0, 1, 0)],
        indices=[0, 1, 2], material="default",
        texcoords=[[Vector2(), Vector2(1, 0), Vector2(0, 1)]],
    )
    drawable = create_ydr(meshes=[mesh], material_textures={"DiffuseSampler": "diffuse"}, name="triangle")
    source = tmp_path / "triangle.ydr"
    drawable.save(source)
    archive = RpfArchive.empty("assets.rpf")
    archive.file("triangle.ydr", source.read_bytes())
    archive.save(tmp_path / "assets.rpf")
    with GameFileCache(use_index_cache=False) as cache:
        cache.scan(tmp_path, load_keys=False)
        with patch.object(resource, "decompress_resource_stream", wraps=resource.decompress_resource_stream) as decode:
            if native:
                file = cache.get_file("assets.rpf/triangle.ydr")
            else:
                with patch.object(GameFileCache, "_read_archive_asset_native_variants", return_value=None):
                    file = cache.get_file("assets.rpf/triangle.ydr")
            assert len(file.parsed.meshes[0].positions) == 3
            assert decode.call_count == 1
