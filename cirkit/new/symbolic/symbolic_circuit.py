from typing import Any, Dict, Iterable, Iterator, Optional, Type

from cirkit.new.layers import InnerLayer, InputLayer
from cirkit.new.region_graph import PartitionNode, RegionGraph, RegionNode, RGNode
from cirkit.new.reparams import Reparameterization
from cirkit.new.symbolic.symbolic_layer import (
    SymbolicInputLayer,
    SymbolicLayer,
    SymbolicProductLayer,
    SymbolicSumLayer,
)
from cirkit.new.utils import Scope

# TODO: double check docs and __repr__


# Disable: It's designed to have these many attributes.
class SymbolicCircuit:  # pylint: disable=too-many-instance-attributes
    """The symbolic representation of a tensorized circuit."""

    # TODO: how to design interface? require kwargs only?
    # TODO: how to deal with too-many?
    # pylint: disable-next=too-many-arguments,too-many-locals
    def __init__(  # type: ignore[misc]  # Ignore: Unavoidable for kwargs.
        self,
        region_graph: RegionGraph,
        *,
        num_input_units: int,
        num_sum_units: int,
        num_classes: int = 1,
        input_layer_cls: Type[InputLayer],
        input_layer_kwargs: Optional[Dict[str, Any]] = None,
        input_reparam: Optional[Reparameterization] = None,
        sum_layer_cls: Type[InnerLayer],  # TODO: more specific?
        sum_layer_kwargs: Optional[Dict[str, Any]] = None,
        sum_reparam: Reparameterization,
        prod_layer_cls: Type[InnerLayer],  # TODO: more specific?
        prod_layer_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """Construct symbolic circuit from a region graph.

        Args:
            region_graph (RegionGraph): The region graph to convert.
            num_input_units (int): _description_
            num_sum_units (int): _description_
            num_classes (int, optional): _description_. Defaults to 1.
            input_layer_cls (Type[InputLayer]): The layer class for input layers.
            input_layer_kwargs (Optional[Dict[str, Any]], optional): The additional kwargs for \
                input layer class. Defaults to None.
            input_reparam (Optional[Reparameterization], optional): The reparameterization for \
                input layer parameters, can be None if it has no params. Defaults to None.
            sum_layer_cls (Type[InnerLayer]): The layer class for sum layers.
            sum_layer_kwargs (Optional[Dict[str, Any]], optional): The additional kwargs for sum \
                layer class. Defaults to None.
            sum_reparam (Reparameterization): The reparameterization for sum layer parameters.
            prod_layer_cls (Type[InnerLayer]): The layer class for product layers.
            prod_layer_kwargs (Optional[Dict[str, Any]], optional): The additional kwargs for \
                product layer class. Defaults to None.
        """
        self.region_graph = region_graph
        self.scope = region_graph.scope
        self.num_vars = region_graph.num_vars
        self.is_smooth = region_graph.is_smooth
        self.is_decomposable = region_graph.is_decomposable
        self.is_structured_decomposable = region_graph.is_structured_decomposable
        self.is_omni_compatible = region_graph.is_omni_compatible

        node_layer: Dict[RGNode, SymbolicLayer] = {}

        for rg_node in region_graph.nodes:
            layers_in = (node_layer[node_in] for node_in in rg_node.inputs)
            layer: SymbolicLayer
            # Ignore: Unavoidable for kwargs.
            if isinstance(rg_node, RegionNode) and not rg_node.inputs:  # Input node.
                layer = SymbolicInputLayer(
                    rg_node,
                    layers_in,
                    num_units=num_input_units,
                    layer_cls=input_layer_cls,
                    layer_kwargs=input_layer_kwargs,  # type: ignore[misc]
                    reparam=input_reparam,
                )
            elif isinstance(rg_node, RegionNode) and rg_node.inputs:  # Inner region node.
                layer = SymbolicSumLayer(
                    rg_node,
                    layers_in,
                    num_units=num_sum_units if rg_node.outputs else num_classes,
                    layer_cls=sum_layer_cls,
                    layer_kwargs=sum_layer_kwargs,  # type: ignore[misc]
                    reparam=sum_reparam,
                )
            elif isinstance(rg_node, PartitionNode):  # Partition node.
                layer = SymbolicProductLayer(
                    rg_node,
                    layers_in,
                    num_units=prod_layer_cls._infer_num_prod_units(
                        num_sum_units, len(rg_node.inputs)
                    ),
                    layer_cls=prod_layer_cls,
                    layer_kwargs=prod_layer_kwargs,  # type: ignore[misc]
                    reparam=None,
                )
            else:
                assert False, "This should not happen."
            node_layer[rg_node] = layer

        self._node_layer = node_layer  # Insertion order is preserved by dict@py3.7+.

    #######################################    Properties    #######################################
    # Here are the basic properties and some structural properties of the SymbC. Some of them are
    # simply defined in __init__. Some requires additional treatment and is define below. We list
    # everything here to add "docstrings" to them.

    scope: Scope
    """The scope of the SymbC, i.e., the union of scopes of all output layers."""

    num_vars: int
    """The number of variables referenced in the SymbC, i.e., the size of scope."""

    is_smooth: bool
    """Whether the SymbC is smooth, i.e., all inputs to a sum have the same scope."""

    is_decomposable: bool
    """Whether the SymbC is decomposable, i.e., inputs to a product have disjoint scopes."""

    is_structured_decomposable: bool
    """Whether the SymbC is structured-decomposable, i.e., compatible to itself."""

    is_omni_compatible: bool
    """Whether the SymbC is omni-compatible, i.e., compatible to all circuits of the same scope."""

    def is_compatible(
        self, other: "SymbolicCircuit", *, scope: Optional[Iterable[int]] = None
    ) -> bool:
        """Test compatibility with another symbolic circuit over the given scope.

        Args:
            other (SymbolicCircuit): The other symbolic circuit to compare with.
            scope (Optional[Iterable[int]], optional): The scope over which to check. If None, \
                will use the intersection of the scopes of two SymbC. Defaults to None.

        Returns:
            bool: Whether self is compatible to other.
        """
        return self.region_graph.is_compatible(other.region_graph, scope=scope)

    #######################################    Layer views    ######################################
    # These are iterable views of the nodes in the SymbC, and the topological order is guaranteed
    # (by a stronger ordering). For efficiency, all these views are iterators (implemented as a
    # container iter or a generator), so that they can be chained for iteration without
    # instantiating intermediate containers.

    @property
    def layers(self) -> Iterator[SymbolicLayer]:
        """All layers in the circuit."""
        return iter(self._node_layer.values())

    @property
    def sum_layers(self) -> Iterator[SymbolicSumLayer]:
        """Sum layers in the circuit, which are always inner layers."""
        # Ignore: SymbolicSumLayer contains Any.
        return (
            layer
            for layer in self.layers
            if isinstance(layer, SymbolicSumLayer)  # type: ignore[misc]
        )

    @property
    def product_layers(self) -> Iterator[SymbolicProductLayer]:
        """Product layers in the circuit, which are always inner layers."""
        # Ignore: SymbolicProductLayer contains Any.
        return (
            layer
            for layer in self.layers
            if isinstance(layer, SymbolicProductLayer)  # type: ignore[misc]
        )

    @property
    def input_layers(self) -> Iterator[SymbolicInputLayer]:
        """Input layers of the circuit."""
        # Ignore: SymbolicInputLayer contains Any.
        return (
            layer
            for layer in self.layers
            if isinstance(layer, SymbolicInputLayer)  # type: ignore[misc]
        )

    @property
    def output_layers(self) -> Iterator[SymbolicSumLayer]:
        """Output layers of the circuit, which are always sum layers."""
        return (layer for layer in self.sum_layers if not layer.outputs)

    @property
    def inner_layers(self) -> Iterator[SymbolicLayer]:
        """Inner (non-input) layers in the circuit."""
        return (layer for layer in self.layers if layer.inputs)

    ####################################    (De)Serialization    ###################################
    # TODO: impl? or just save RG and kwargs of SymbC?