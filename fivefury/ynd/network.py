from __future__ import annotations

import copy
import dataclasses
from collections import Counter
from pathlib import Path
from collections.abc import Hashable

from .model import Ynd, YndLink, YndNode
from .regions import get_ynd_area_id


def _node_key(node: YndNode, fallback_index: int, duplicate_keys: set[Hashable]) -> Hashable:
    if node.key is not None:
        return node.key
    candidate: Hashable = int(node.node_id)
    if candidate not in duplicate_keys:
        return candidate
    return fallback_index


@dataclasses.dataclass(slots=True)
class YndNetwork:
    version: int = 1
    path: str = ""
    nodes: list[YndNode] = dataclasses.field(default_factory=list)

    @classmethod
    def from_nodes(cls, nodes: list[YndNode], *, path: str | Path = "", version: int = 1) -> "YndNetwork":
        return cls(version=int(version), path=str(path) if path else "", nodes=list(nodes))

    def build_ynds(self) -> list[Ynd]:
        draft_nodes = copy.deepcopy(self.nodes)
        raw_keys: list[Hashable] = [node.key if node.key is not None else int(node.node_id) for node in draft_nodes]
        duplicate_keys = {key for key, count in Counter(raw_keys).items() if count > 1}

        keyed_nodes: list[tuple[Hashable, YndNode]] = []
        for index, node in enumerate(draft_nodes):
            key = _node_key(node, index, duplicate_keys)
            node.key = key
            node.area_id = get_ynd_area_id(node.position)
            keyed_nodes.append((key, node))

        area_nodes: dict[int, list[YndNode]] = {}
        for _, node in keyed_nodes:
            area_nodes.setdefault(int(node.area_id), []).append(node)

        area_local_ids: dict[Hashable, tuple[int, int]] = {}
        for area_id, nodes in area_nodes.items():
            provisional_nodes = sorted(nodes, key=lambda node: (1 if node.is_ped_node else 0, int(node.node_id)))
            for local_id, node in enumerate(provisional_nodes):
                node.node_id = local_id
                area_local_ids[node.key] = (area_id, local_id)

        for _, node in keyed_nodes:
            for link in node.links:
                if link.target_key is not None:
                    target_key = link.target_key
                elif link.area_id is None:
                    target_key = link.node_id
                else:
                    continue
                target_info = area_local_ids.get(target_key)
                if target_info is None:
                    raise ValueError(f"YND link target {target_key!r} could not be resolved inside the network")
                link.area_id, link.node_id = target_info

        built_ynds: list[Ynd] = []
        for area_id in sorted(area_nodes):
            built_ynds.append(
                Ynd.from_nodes(
                    area_nodes[area_id],
                    area_id=area_id,
                    path=self.path,
                    version=self.version,
                ).build()
            )
        return built_ynds
