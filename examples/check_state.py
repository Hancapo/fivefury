from fivefury import Archetype, Entity, GameFileCache, Ymap, Ytyp, create_rpf  # noqa: E402,F401

from pathlib import Path


GAME_PATH: Path = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V")
gfc = GameFileCache(GAME_PATH, dlc_level="mp2025_02_g9ec", verbose=True)
gfc.scan(use_index_cache=False)