from collections import defaultdict

import numpy as np

from cirkit.templates.region_graph.graph import (
    PartitionNode,
    RegionGraph,
    RegionGraphNode,
    RegionNode,
)
from cirkit.utils.scope import Scope

HyperCube = tuple[tuple[int, ...], tuple[int, ...]]  # Just to shorten the annotation.
"""A hypercube represented by "top-left" and "bottom-right" coordinates (cut points)."""


class HypercubeToScope(dict[HyperCube, Scope]):
    """Helper class to map sub-hypercubes to scopes with caching for variables arranged in a \
    hypercube.

    This is implemented as a dict subclass with customized __missing__, so that:
        - If a hypercube is already queried, the corresponding scope is retrieved the dict;
        - If it's not in the dict yet, the scope is calculated and cached to the dict.
    """

    def __init__(self, shape: tuple[int, int, int]) -> None:
        r"""Initialize a hypercube to scope object.
        Note that this does not accept initial elements and is initialized empty.

        Args:
            shape: The image shape $(C, H, W)$, where $H$ is the height, $W$ is the width,
                and $C$ is the number of channels.
        """
        super().__init__()
        self.ndims = len(shape)
        self.shape = shape
        # ANNOTATE: Numpy has typing issues.
        self.hypercube = np.arange(np.prod(shape), dtype=np.int64).reshape(shape)

    def __missing__(self, key: HyperCube) -> Scope:
        """Construct the item when not exist in the dict.

        Args:
            key: The key that is missing from the dict, i.e., a hypercube that is
                visited for the first time.

        Returns:
            Scope: The value for the key, i.e., the corresponding scope.

        Raises:
            ValueError: If the hyper-cube key has incorrect shape, or if it's empty.
        """
        point1, point2 = key  # HyperCube is from point1 to point2.

        if not (len(point1) == len(point2) == self.ndims):
            raise ValueError("The dimension of the HyperCube is not correct")
        if not all(0 <= x1 < x2 <= shape for x1, x2, shape in zip(point1, point2, self.shape)):
            raise ValueError("The HyperCube is empty")
        return Scope(
            self.hypercube[  # type: ignore[misc]
                tuple(slice(x1, x2) for x1, x2 in zip(point1, point2))
            ]
            .reshape(-1)
            .tolist()
        )


def tree2rg(tree: np.ndarray) -> RegionGraph:
    """Convert a tree structure into a region graph. Useful to convert CLTs into HCLT region graphs.
     More details in https://arxiv.org/abs/2409.07953.

    Args:
        tree (np.ndarray): A tree in form of list of predecessors, i.e. tree[i] is the parent of i,
            and is equal to -1 when i is root.

    Returns:
        A region graph.
    """
    # TODO: check the input encodes a rooted tree
    num_variables = len(tree)
    nodes: list[RegionGraphNode] = []
    in_nodes: dict[RegionGraphNode, list[RegionGraphNode]] = defaultdict(list)
    partitions: list[PartitionNode | None] = [None] * num_variables

    for v in range(num_variables):
        cur_v, prev_v = v, int(tree[v])
        while prev_v != -1:
            if partitions[prev_v] is None:
                p_scope = {v, prev_v}
                partitions[prev_v] = PartitionNode(p_scope)
            else:
                p_scope = {v} | partitions[prev_v].scope
                partitions[prev_v] = PartitionNode(p_scope)
            cur_v, prev_v = prev_v, tree[cur_v]

    for part_node in partitions:
        if part_node is not None:
            nodes.append(part_node)

    regions: list[RegionNode | None] = [None] * num_variables
    for cur_v in range(num_variables):
        prev_v = tree[cur_v]
        leaf_region = RegionNode({cur_v})
        nodes.append(leaf_region)
        if partitions[cur_v] is None:
            if prev_v != -1:
                in_nodes[partitions[prev_v]].append(leaf_region)
            regions[cur_v] = leaf_region
        else:
            in_nodes[partitions[cur_v]].append(leaf_region)
            p_scope = partitions[cur_v].scope
            if regions[cur_v] is None:
                regions[cur_v] = RegionNode(p_scope)
                nodes.append(regions[cur_v])
            in_nodes[regions[cur_v]].append(partitions[cur_v])
            if prev_v != -1:
                in_nodes[partitions[prev_v]].append(regions[cur_v])

    outputs = [regions[cur_v] for cur_v, prev_v in enumerate(tree) if prev_v == -1]
    return RegionGraph(nodes, in_nodes, outputs=outputs)
