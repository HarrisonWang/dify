from typing import Optional

from pydantic import BaseModel, Field, model_validator

from core.workflow.graph_engine.condition_handlers.base_handler import RunConditionHandler
from core.workflow.graph_engine.condition_handlers.condition_manager import ConditionManager
from core.workflow.graph_engine.entities.run_condition import RunCondition


class GraphNode(BaseModel):
    id: str
    """node id"""

    parent_id: Optional[str] = None
    """parent node id, e.g. iteration/loop"""

    predecessor_node_id: Optional[str] = None
    """predecessor node id"""

    descendant_node_ids: list[str] = []
    """descendant node ids"""

    run_condition: Optional[RunCondition] = None
    """condition to run the node"""

    node_config: dict
    """original node config"""

    source_edge_config: Optional[dict] = None
    """original source edge config"""

    sub_graph: Optional["Graph"] = None
    """sub graph of the node, e.g. iteration/loop sub graph"""

    def add_child(self, node_id: str) -> None:
        if node_id not in self.descendant_node_ids:
            self.descendant_node_ids.append(node_id)

    def get_run_condition_handler(self) -> Optional[RunConditionHandler]:
        """
        Get run condition handler

        :return: run condition handler
        """
        if not self.run_condition:
            return None

        return ConditionManager.get_condition_handler(
            run_condition=self.run_condition
        )


class Graph(BaseModel):
    graph_nodes: dict[str, GraphNode] = Field(default_factory=dict)
    """graph nodes"""

    root_node: GraphNode
    """root node of the graph"""

    @model_validator(mode='after')
    def add_root_node(cls, values):
        root_node = values.root_node
        values.graph_nodes[root_node.id] = root_node
        return values

    @classmethod
    def init(cls, root_node_config: dict, run_condition: Optional[RunCondition] = None) -> "Graph":
        """
        Init graph

        :param root_node_config: root node config
        :param run_condition: run condition when root node parent is iteration/loop
        :return: graph
        """
        node_id = root_node_config.get('id')
        if not node_id:
            raise ValueError("Graph root node id is required")

        root_node = GraphNode(
            id=node_id,
            parent_id=root_node_config.get('parentId'),
            node_config=root_node_config,
            run_condition=run_condition
        )

        return cls(root_node=root_node)

    def add_edge(self, edge_config: dict,
                 source_node_config: dict,
                 target_node_config: dict,
                 target_node_sub_graph: Optional["Graph"] = None,
                 run_condition: Optional[RunCondition] = None) -> None:
        """
        Add edge to the graph

        :param edge_config: edge config
        :param source_node_config: source node config
        :param target_node_config: target node config
        :param target_node_sub_graph: sub graph
        :param run_condition: run condition
        """
        source_node_id = source_node_config.get('id')
        if not source_node_id:
            return

        if source_node_id not in self.graph_nodes:
            return

        target_node_id = target_node_config.get('id')
        if not target_node_id:
            return

        source_node = self.graph_nodes.get(source_node_id)
        if not source_node:
            return

        source_node.add_child(target_node_id)

        if target_node_id not in self.graph_nodes:
            target_graph_node = GraphNode(
                id=target_node_id,
                parent_id=source_node_config.get('parentId'),
                predecessor_node_id=source_node_id,
                node_config=target_node_config,
                run_condition=run_condition,
                source_edge_config=edge_config,
                sub_graph=target_node_sub_graph
            )

            self.add_graph_node(target_graph_node)
        else:
            target_node = self.graph_nodes.get(target_node_id)
            if not target_node:
                return

            target_node.predecessor_node_id = source_node_id
            target_node.run_condition = run_condition
            target_node.source_edge_config = edge_config
            target_node.sub_graph = target_node_sub_graph

    def get_leaf_nodes(self) -> list[GraphNode]:
        """
        Get leaf nodes of the graph

        :return: leaf nodes
        """
        leaf_nodes = []
        for node_id, graph_node in self.graph_nodes.items():
            if (
                    not graph_node.descendant_node_ids  # has no child
                    or  # or has only one child and the child is the root node
                    (
                            graph_node.descendant_node_ids
                            and graph_node.descendant_node_ids[0] == self.root_node.id
                    )
            ):
                leaf_nodes.append(graph_node)

        return leaf_nodes

    def get_descendant_graphs(self, node_id: str) -> list["Graph"]:
        """
        Get descendant graphs of the specific node

        :param node_id: node id
        :return: descendant graphs
        """
        if node_id not in self.graph_nodes:
            return []

        graph_node = self.graph_nodes.get(node_id)
        if not graph_node or not graph_node.descendant_node_ids:
            return []

        descendant_graphs: list[Graph] = []
        for descendant_node_id in graph_node.descendant_node_ids:
            descendant_graph_node = self.graph_nodes.get(descendant_node_id)
            if not descendant_graph_node:
                continue

            descendants_graph = Graph(root_node=descendant_graph_node)
            for sub_descendant_node_id in descendant_graph_node.descendant_node_ids:
                descendants_graph.add_descendants_graph_nodes(self, sub_descendant_node_id)

            descendant_graphs.append(descendants_graph)

        return descendant_graphs

    def add_graph_node(self, graph_node: GraphNode) -> None:
        """
        Add graph node to the graph

        :param graph_node: graph node
        """
        if graph_node.id in self.graph_nodes:
            return

        self.graph_nodes[graph_node.id] = graph_node

    def add_descendants_graph_nodes(self, predecessor_graph: "Graph", node_id: str) -> None:
        """
        Add descendants graph nodes

        :param predecessor_graph: predecessor graph
        :param node_id: node id
        """
        if node_id not in predecessor_graph.graph_nodes:
            return

        graph_node = predecessor_graph.graph_nodes.get(node_id)
        if not graph_node:
            return

        if graph_node.id not in self.graph_nodes:
            self.add_graph_node(graph_node)

            for child_node_id in graph_node.descendant_node_ids:
                self.add_descendants_graph_nodes(predecessor_graph, child_node_id)