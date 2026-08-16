from __future__ import annotations

import xml.etree.ElementTree as ET

from fivefury import MetaHash
from fivefury.vehiclemeta import (
    CarHandlingData,
    HandlingData,
    HandlingDataManager,
    VehicleCarCols,
    VehicleClass,
    VehicleColorIndices,
    VehicleCorona,
    VehicleInitData,
    VehicleInitDataList,
    VehicleLightSettings,
    VehicleModelFlag,
    VehicleModelFlags,
    VehicleModelInfoVariation,
    VehiclePlateType,
    VehicleVariation,
    VehicleWheelType,
    read_vehicle_meta,
    validate_vehicle_meta_xml,
)


def test_vehicles_meta_uses_retail_tokens_flags_aliases_and_float_arrays() -> None:
    document = VehicleInitDataList(
        vehicles=[
            VehicleInitData(
                model_name="jester",
                txd_name="jester",
                handling_id="JESTER",
                lod_distances=[15.0, 30.0],
                flags=(VehicleModelFlag.FLAG_SPORTS | VehicleModelFlag.FLAG_RICH_CAR),
                plate_type=VehiclePlateType.BACK,
                vehicle_class=VehicleClass.SPORT,
                wheel_type=VehicleWheelType.HIGH_END,
            )
        ]
    )

    data = document.to_bytes()
    root = ET.fromstring(data)
    item = root.find("./InitDatas/Item")

    assert item is not None
    assert (
        b'<lodDistances content="float_array">15.000000 30.000000</lodDistances>'
        in data
    )
    assert item.find("visibleSpawnDistScale") is not None
    assert item.find("weaponForceMult") is not None
    assert item.find("visibleSpawnDistanceScale") is None
    assert item.find("weaponForceMultiplier") is None
    assert item.findtext("flags") == "FLAG_SPORTS FLAG_RICH_CAR"
    assert item.findtext("type") == "VEHICLE_TYPE_CAR"
    assert item.findtext("plateType") == "VPT_BACK_PLATES"
    assert item.findtext("vehicleClass") == "VC_SPORT"
    assert item.findtext("wheelType") == "VWT_HIEND"
    assert read_vehicle_meta(data).content == document


def test_handling_meta_preserves_typed_and_null_subhandling_slots() -> None:
    document = HandlingDataManager(
        entries=[
            HandlingData(
                name=MetaHash("JESTER"),
                mass=1500.0,
                sub_handling=[
                    CarHandlingData(values={"fCamberFront": -0.02}),
                    None,
                ],
            )
        ]
    )

    data = document.to_bytes()
    root = ET.fromstring(data)
    handling = root.find("./HandlingData/Item")
    slots = root.findall("./HandlingData/Item/SubHandlingData/Item")

    assert handling is not None
    assert handling.attrib == {"type": "CHandlingData"}
    assert slots[0].attrib == {"type": "CCarHandlingData"}
    assert slots[1].attrib == {"type": "NULL"}
    assert list(slots[1]) == []
    assert read_vehicle_meta(data).content == document


def test_carvariations_meta_uses_retail_array_shapes() -> None:
    document = VehicleModelInfoVariation(
        vehicles=[
            VehicleVariation(
                model_name="jester",
                colors=[
                    VehicleColorIndices(
                        indices=[0, 1, 2, 3, 4, 5],
                        liveries=[True, False],
                    )
                ],
            )
        ]
    )

    data = document.to_bytes()
    root = ET.fromstring(data)
    indices = root.find("./variationData/Item/colors/Item/indices")
    liveries = root.findall("./variationData/Item/colors/Item/liveries/Item")

    assert indices is not None
    assert indices.attrib == {"content": "char_array"}
    assert indices.text == "0 1 2 3 4 5"
    assert [item.attrib for item in liveries] == [
        {"value": "true"},
        {"value": "false"},
    ]
    assert read_vehicle_meta(data).content == document


def test_vehicle_xml_validation_rejects_numeric_authoring_grammar() -> None:
    report = validate_vehicle_meta_xml(
        b"""<CVehicleModelInfo__InitDataList>
        <InitDatas><Item>
          <lodDistances><Item value="15" /></lodDistances>
          <visibleSpawnDistanceScale value="1" />
          <weaponForceMultiplier value="1" />
          <flags value="0" />
          <type value="0" />
          <plateType value="0" />
          <vehicleClass value="6" />
          <wheelType value="0" />
        </Item></InitDatas>
        </CVehicleModelInfo__InitDataList>"""
    )

    assert not report.valid
    assert {
        "vehicle.xml.array.float.invalid",
        "vehicle.xml.array.items.invalid",
        "vehicle.xml.element.alias.invalid",
        "vehicle.xml.flags.shape.invalid",
        "vehicle.xml.enum.shape.invalid",
    }.issubset({issue.code for issue in report})


def test_retail_unknown_flags_and_repeated_ik_offsets_survive_roundtrip() -> None:
    document = VehicleInitDataList.from_value(
        {
            "InitDatas": [
                {
                    "modelName": "futurecar",
                    "txdName": "futurecar",
                    "handlingId": "FUTURECAR",
                    "flags": "FLAG_SPORTS FLAG_FUTURE_RETAIL",
                    "requiredExtras": "extra_9",
                    "FirstPersonDriveByRightRearPassengerIKOffset": [
                        (0.0, -0.02, -0.04),
                        (0.0, -0.088, -0.047),
                    ],
                }
            ]
        }
    )

    data = document.to_bytes()
    reread = read_vehicle_meta(data).content
    vehicle = reread.vehicles[0]

    assert isinstance(vehicle.flags, VehicleModelFlags)
    assert vehicle.flags.known == VehicleModelFlag.FLAG_SPORTS
    assert vehicle.flags.unknown_tokens == ("FLAG_FUTURE_RETAIL",)
    assert data.count(b"FirstPersonDriveByRightRearPassengerIKOffset") == 2
    assert reread == document


def test_carcols_writer_uses_retail_corona_field_names() -> None:
    document = VehicleCarCols(
        lights=[
            VehicleLightSettings(
                id=1,
                tail_light_corona=VehicleCorona(
                    far_size=10.0,
                    far_intensity=1.0,
                    count=2,
                    spacing=50,
                    far_spacing=1,
                    rotation=(0.0, 3.11, 0.352),
                ),
            )
        ]
    )

    data = document.to_bytes()

    assert b'<size_far value="10.000000"' in data
    assert b'<intensity_far value="1.000000"' in data
    assert b'<numCoronas value="2"' in data
    assert b'<distBetweenCoronas value="50"' in data
    assert b'<yRotation value="3.110000"' in data
    assert read_vehicle_meta(data).content == document


def test_retail_misplaced_negative_fraction_is_normalized() -> None:
    document = read_vehicle_meta(
        b"""<CVehicleModelInfo__InitDataList><InitDatas><Item>
        <modelName>retailcar</modelName><txdName>retailcar</txdName>
        <handlingId>RETAILCAR</handlingId>
        <FirstPersonDriveByUnarmedIKOffset x="0.000000" y="0.-060000" z="0.-020000" />
        </Item></InitDatas></CVehicleModelInfo__InitDataList>"""
    ).content

    assert document.vehicles[0].first_person_ik_offsets["driver_unarmed"] == [
        (0.0, -0.06, -0.02)
    ]
