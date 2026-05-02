from __future__ import annotations

import dataclasses
import enum
import hashlib
from pathlib import Path

from ..colors import parse_css_rgb

RGB = tuple[int, int, int]

_DEFAULT_BOUND_MATERIAL_NAMES = (
    'DEFAULT', 'CONCRETE', 'CONCRETE_POTHOLE', 'CONCRETE_DUSTY', 'TARMAC', 'TARMAC_PAINTED',
    'TARMAC_POTHOLE', 'RUMBLE_STRIP', 'BREEZE_BLOCK', 'ROCK', 'ROCK_MOSSY', 'STONE',
    'COBBLESTONE', 'BRICK', 'MARBLE', 'PAVING_SLAB', 'SANDSTONE_SOLID', 'SANDSTONE_BRITTLE',
    'SAND_LOOSE', 'SAND_COMPACT', 'SAND_WET', 'SAND_TRACK', 'SAND_UNDERWATER', 'SAND_DRY_DEEP',
    'SAND_WET_DEEP', 'ICE', 'ICE_TARMAC', 'SNOW_LOOSE', 'SNOW_COMPACT', 'SNOW_DEEP',
    'SNOW_TARMAC', 'GRAVEL_SMALL', 'GRAVEL_LARGE', 'GRAVEL_DEEP', 'GRAVEL_TRAIN_TRACK',
    'DIRT_TRACK', 'MUD_HARD', 'MUD_POTHOLE', 'MUD_SOFT', 'MUD_UNDERWATER', 'MUD_DEEP', 'MARSH',
    'MARSH_DEEP', 'SOIL', 'CLAY_HARD', 'CLAY_SOFT', 'GRASS_LONG', 'GRASS', 'GRASS_SHORT', 'HAY',
    'BUSHES', 'TWIGS', 'LEAVES', 'WOODCHIPS', 'TREE_BARK', 'METAL_SOLID_SMALL',
    'METAL_SOLID_MEDIUM', 'METAL_SOLID_LARGE', 'METAL_HOLLOW_SMALL', 'METAL_HOLLOW_MEDIUM',
    'METAL_HOLLOW_LARGE', 'METAL_CHAINLINK_SMALL', 'METAL_CHAINLINK_LARGE',
    'METAL_CORRUGATED_IRON', 'METAL_GRILLE', 'METAL_RAILING', 'METAL_DUCT', 'METAL_GARAGE_DOOR',
    'METAL_MANHOLE', 'WOOD_SOLID_SMALL', 'WOOD_SOLID_MEDIUM', 'WOOD_SOLID_LARGE',
    'WOOD_SOLID_POLISHED', 'WOOD_FLOOR_DUSTY', 'WOOD_HOLLOW_SMALL', 'WOOD_HOLLOW_MEDIUM',
    'WOOD_HOLLOW_LARGE', 'WOOD_CHIPBOARD', 'WOOD_OLD_CREAKY', 'WOOD_HIGH_DENSITY', 'WOOD_LATTICE',
    'CERAMIC', 'ROOF_TILE', 'ROOF_FELT', 'FIBREGLASS', 'TARPAULIN', 'PLASTIC', 'PLASTIC_HOLLOW',
    'PLASTIC_HIGH_DENSITY', 'PLASTIC_CLEAR', 'PLASTIC_HOLLOW_CLEAR', 'PLASTIC_HIGH_DENSITY_CLEAR',
    'FIBREGLASS_HOLLOW', 'RUBBER', 'RUBBER_HOLLOW', 'LINOLEUM', 'LAMINATE', 'CARPET_SOLID',
    'CARPET_SOLID_DUSTY', 'CARPET_FLOORBOARD', 'CLOTH', 'PLASTER_SOLID', 'PLASTER_BRITTLE',
    'CARDBOARD_SHEET', 'CARDBOARD_BOX', 'PAPER', 'FOAM', 'FEATHER_PILLOW', 'POLYSTYRENE',
    'LEATHER', 'TVSCREEN', 'SLATTED_BLINDS', 'GLASS_SHOOT_THROUGH', 'GLASS_BULLETPROOF',
    'GLASS_OPAQUE', 'PERSPEX', 'CAR_METAL', 'CAR_PLASTIC', 'CAR_SOFTTOP', 'CAR_SOFTTOP_CLEAR',
    'CAR_GLASS_WEAK', 'CAR_GLASS_MEDIUM', 'CAR_GLASS_STRONG', 'CAR_GLASS_BULLETPROOF',
    'CAR_GLASS_OPAQUE', 'WATER', 'BLOOD', 'OIL', 'PETROL', 'FRESH_MEAT', 'DRIED_MEAT',
    'EMISSIVE_GLASS', 'EMISSIVE_PLASTIC', 'VFX_METAL_ELECTRIFIED', 'VFX_METAL_WATER_TOWER',
    'VFX_METAL_STEAM', 'VFX_METAL_FLAME', 'PHYS_NO_FRICTION', 'PHYS_GOLF_BALL',
    'PHYS_TENNIS_BALL', 'PHYS_CASTER', 'PHYS_CASTER_RUSTY', 'PHYS_CAR_VOID', 'PHYS_PED_CAPSULE',
    'PHYS_ELECTRIC_FENCE', 'PHYS_ELECTRIC_METAL', 'PHYS_BARBED_WIRE', 'PHYS_POOLTABLE_SURFACE',
    'PHYS_POOLTABLE_CUSHION', 'PHYS_POOLTABLE_BALL', 'BUTTOCKS', 'THIGH_LEFT', 'SHIN_LEFT',
    'FOOT_LEFT', 'THIGH_RIGHT', 'SHIN_RIGHT', 'FOOT_RIGHT', 'SPINE0', 'SPINE1', 'SPINE2',
    'SPINE3', 'CLAVICLE_LEFT', 'UPPER_ARM_LEFT', 'LOWER_ARM_LEFT', 'HAND_LEFT', 'CLAVICLE_RIGHT',
    'UPPER_ARM_RIGHT', 'LOWER_ARM_RIGHT', 'HAND_RIGHT', 'NECK', 'HEAD', 'ANIMAL_DEFAULT',
    'CAR_ENGINE', 'PUDDLE', 'CONCRETE_PAVEMENT', 'BRICK_PAVEMENT', 'PHYS_DYNAMIC_COVER_BOUND',
    'VFX_WOOD_BEER_BARREL', 'WOOD_HIGH_FRICTION', 'ROCK_NOINST', 'BUSHES_NOINST',
    'METAL_SOLID_ROAD_SURFACE', 'STUNT_RAMP_SURFACE', 'TEMP_01', 'TEMP_02', 'TEMP_03', 'TEMP_04',
    'TEMP_05', 'TEMP_06', 'TEMP_07', 'TEMP_08', 'TEMP_09', 'TEMP_10', 'TEMP_11', 'TEMP_12',
    'TEMP_13', 'TEMP_14', 'TEMP_15', 'TEMP_16', 'TEMP_17', 'TEMP_18', 'TEMP_19', 'TEMP_20',
    'TEMP_21', 'TEMP_22', 'TEMP_23', 'TEMP_24', 'TEMP_25', 'TEMP_26', 'TEMP_27', 'TEMP_28',
    'TEMP_29', 'TEMP_30',
)

BoundMaterialType = enum.IntEnum(
    "BoundMaterialType",
    {name: index for index, name in enumerate(_DEFAULT_BOUND_MATERIAL_NAMES)},
    module=__name__,
)


def coerce_bound_material_index(value: int | BoundMaterialType) -> int:
    return int(value)


def get_bound_material_type(index: int) -> BoundMaterialType | None:
    try:
        return BoundMaterialType(int(index))
    except ValueError:
        return None


def _fallback_color_from_name(name: str) -> RGB:
    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=3).digest()
    return (
        64 + (digest[0] % 160),
        64 + (digest[1] % 160),
        64 + (digest[2] % 160),
    )


def _parse_color_spec(spec: str) -> RGB:
    return parse_css_rgb(spec)


@dataclasses.dataclass(slots=True, frozen=True)
class BoundMaterialInfo:
    index: int
    name: str
    color: RGB


@dataclasses.dataclass(slots=True, frozen=True)
class BoundMaterialLibrary:
    names: tuple[str, ...]
    colors: dict[int, RGB] = dataclasses.field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.names)

    def get_name(self, index: int) -> str:
        if 0 <= index < len(self.names):
            return self.names[index]
        return f"MATERIAL_{index}"

    def get_color(self, index: int) -> RGB:
        if index in self.colors:
            return self.colors[index]
        return _fallback_color_from_name(self.get_name(index))

    def get(self, index: int) -> BoundMaterialInfo:
        return BoundMaterialInfo(index=index, name=self.get_name(index), color=self.get_color(index))


DEFAULT_BOUND_MATERIAL_LIBRARY = BoundMaterialLibrary(_DEFAULT_BOUND_MATERIAL_NAMES)


def get_bound_material_name(index: int | BoundMaterialType) -> str:
    return DEFAULT_BOUND_MATERIAL_LIBRARY.get_name(int(index))


def get_bound_material_color(index: int | BoundMaterialType) -> RGB:
    return DEFAULT_BOUND_MATERIAL_LIBRARY.get_color(int(index))


def parse_bound_material_names(text: str) -> BoundMaterialLibrary:
    names: list[str] = []
    colors: dict[int, RGB] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "|" in stripped:
            name, color_spec = (part.strip() for part in stripped.split("|", 1))
            colors[len(names)] = _parse_color_spec(color_spec)
            names.append(name)
            continue
        names.append(stripped)
    return BoundMaterialLibrary(tuple(names), colors)


def read_bound_material_names(path: str | Path) -> BoundMaterialLibrary:
    source = Path(path)
    return parse_bound_material_names(source.read_text(encoding="utf-8", errors="ignore"))


__all__ = [
    "BoundMaterialInfo",
    "BoundMaterialLibrary",
    "BoundMaterialType",
    "DEFAULT_BOUND_MATERIAL_LIBRARY",
    "coerce_bound_material_index",
    "get_bound_material_color",
    "get_bound_material_name",
    "get_bound_material_type",
    "parse_bound_material_names",
    "read_bound_material_names",
]
