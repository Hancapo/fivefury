from __future__ import annotations

from typing import TYPE_CHECKING

from ...authoring.context import BuildContext
from ...authoring.diagnostics import DiagnosticSeverity, ValidationReport

if TYPE_CHECKING:
    from .asset import Ydr


def validate_drawable(
    drawable: Ydr,
    *,
    context: BuildContext | None = None,
) -> ValidationReport:
    del context
    report = ValidationReport()
    asset = drawable.path or drawable.name or None

    def issue(
        code: str,
        message: str,
        *,
        severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
        path: str | None = None,
    ) -> None:
        report.issue(code, message, severity=severity, asset=asset, path=path)

    models = list(drawable.iter_models())
    if not models:
        issue("missing_models", "YDR has no drawable models", path="models")
    if not drawable.materials:
        issue("missing_materials", "YDR has no materials", path="materials")

    embedded_names = {
        texture.name.lower()
        for texture in (
            drawable.embedded_textures.textures
            if drawable.embedded_textures is not None
            else []
        )
    }
    for material_position, material in enumerate(drawable.materials):
        material_path = f"materials[{material_position}]"
        if material.shader_definition is None:
            issue(
                "missing_shader_definition",
                f"Material '{material.name or material.index}' has no resolved shader",
                path=f"{material_path}.shader_definition",
            )
        if not material.resolved_shader_file_name:
            issue(
                "missing_shader_file",
                f"Material '{material.name or material.index}' has no shader file name",
                path=f"{material_path}.shader_file_name",
            )
        for parameter_position, parameter in enumerate(material.parameters):
            parameter_path = f"{material_path}.parameters[{parameter_position}]"
            legacy_parameter = (
                material.shader_definition.get_parameter(parameter.name)
                if material.shader_definition is not None
                else None
            )
            if (
                parameter.is_texture
                and parameter.texture is None
                and legacy_parameter is not None
                and legacy_parameter.is_texture
            ):
                issue(
                    "unbound_texture_slot",
                    f"Material '{material.name or material.index}' leaves optional texture slot '{parameter.name}' empty",
                    severity=DiagnosticSeverity.INFO,
                    path=f"{parameter_path}.texture",
                )
            if (
                parameter.is_texture
                and parameter.texture is not None
                and embedded_names
                and parameter.texture.name.lower() not in embedded_names
            ):
                issue(
                    "external_texture_reference",
                    f"Texture '{parameter.texture.name}' is not present in embedded textures",
                    severity=DiagnosticSeverity.INFO,
                    path=f"{parameter_path}.texture",
                )

    bone_count = drawable.skeleton.bone_count if drawable.skeleton is not None else 0
    bone_tags = (
        {int(bone.tag) for bone in drawable.skeleton.bones}
        if drawable.skeleton is not None
        else set()
    )
    for model_position, model in enumerate(models):
        model_path = f"models[{model_position}]"
        if model.has_skin and not drawable.has_skeleton:
            issue(
                "missing_skeleton",
                f"Model {model.index} is skinned but the drawable has no skeleton",
                path=f"{model_path}.skeleton_binding",
            )
        if (
            drawable.skeleton is not None
            and model.bone_index >= drawable.skeleton.bone_count
        ):
            issue(
                "invalid_model_bone_binding",
                f"Model {model.index} references bone index {model.bone_index} outside skeleton range",
                path=f"{model_path}.bone_index",
            )
        if int(model.skeleton_binding.has_skin) not in (0, 1):
            issue(
                "invalid_has_skin_flag",
                f"Model {model.index} uses unsupported HasSkin value {model.skeleton_binding.has_skin}",
                path=f"{model_path}.skeleton_binding.has_skin",
            )
        if int(model.skeleton_binding.unknown_2) != 0:
            issue(
                "unexpected_skeleton_binding_unknown_2",
                f"Model {model.index} uses non-zero SkeletonBindUnk2 value {model.skeleton_binding.unknown_2}",
                severity=DiagnosticSeverity.WARNING,
                path=f"{model_path}.skeleton_binding.unknown_2",
            )
        for mesh_index, mesh in enumerate(model.meshes):
            mesh_path = f"{model_path}.meshes[{mesh_index}]"
            if mesh.material_index < 0 or mesh.material_index >= len(
                drawable.materials
            ):
                issue(
                    "invalid_material_index",
                    f"Mesh references invalid material index {mesh.material_index}",
                    path=f"{mesh_path}.material_index",
                )
            for texture in (
                mesh.material.textures if mesh.material is not None else []
            ):
                if texture.uv_index is not None and texture.uv_index >= len(
                    mesh.texcoords
                ):
                    issue(
                        "missing_uv_channel",
                        f"Mesh is missing UV{texture.uv_index} required by texture slot '{texture.parameter_name or texture.name}'",
                        path=f"{mesh_path}.texcoords",
                    )
            if mesh.blend_weights and len(mesh.blend_weights) != mesh.vertex_count:
                issue(
                    "weights_size_mismatch",
                    "Blend weights count does not match vertex count",
                    path=f"{mesh_path}.blend_weights",
                )
            if mesh.blend_indices and len(mesh.blend_indices) != mesh.vertex_count:
                issue(
                    "indices_size_mismatch",
                    "Blend indices count does not match vertex count",
                    path=f"{mesh_path}.blend_indices",
                )
            if mesh.is_skinned and not mesh.bone_ids:
                issue(
                    "missing_bone_palette",
                    "Skinned mesh has no bone id palette",
                    path=f"{mesh_path}.bone_ids",
                )
            if mesh.is_skinned and not model.has_skin:
                issue(
                    "missing_model_skin_flag",
                    "Skinned mesh belongs to a model with HasSkin disabled",
                    path=f"{model_path}.skeleton_binding.has_skin",
                )
            if mesh.bone_ids and drawable.skeleton is not None:
                for bone_position, bone_id in enumerate(mesh.bone_ids):
                    resolved_id = int(bone_id)
                    if (
                        resolved_id not in bone_tags
                        and not 0 <= resolved_id < bone_count
                    ):
                        issue(
                            "unknown_bone_id",
                            f"Mesh references unknown bone id {bone_id}",
                            path=f"{mesh_path}.bone_ids[{bone_position}]",
                        )
    if drawable.joints is not None and drawable.joints.has_limits:
        if not drawable.has_skeleton:
            issue(
                "missing_skeleton_for_joints",
                "YDR has joint limits but no skeleton",
                path="joints",
            )
        for index, limit in enumerate(drawable.joints.rotation_limits):
            resolved_id = int(limit.bone_id)
            if (
                drawable.skeleton is not None
                and resolved_id not in bone_tags
                and not 0 <= resolved_id < bone_count
            ):
                issue(
                    "unknown_joint_rotation_bone",
                    f"Rotation limit references unknown bone id {limit.bone_id}",
                    path=f"joints.rotation_limits[{index}].bone_id",
                )
        for index, limit in enumerate(drawable.joints.translation_limits):
            resolved_id = int(limit.bone_id)
            if (
                drawable.skeleton is not None
                and resolved_id not in bone_tags
                and not 0 <= resolved_id < bone_count
            ):
                issue(
                    "unknown_joint_translation_bone",
                    f"Translation limit references unknown bone id {limit.bone_id}",
                    path=f"joints.translation_limits[{index}].bone_id",
                )
    return report
