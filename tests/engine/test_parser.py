"""tests/engine/test_parser.py — ChainParser 测试"""

import pytest

from engine.parser import ChainParser, ParsedChain, ParsedEdge, ParsedNode


class TestParsedNode:

    def test_basic(self):
        node = ParsedNode(node_id="n1", node_type="gas_price_detector", label="Gas")
        assert node.node_id == "n1"
        assert node.node_type == "gas_price_detector"
        assert node.config == {}
        assert node.position == {}


class TestParsedEdge:

    def test_defaults(self):
        edge = ParsedEdge(source_id="s1", target_id="t1")
        assert edge.edge_id == ""
        assert edge.source_port == "output"
        assert edge.target_port == "input"


class TestParsedChain:

    def test_node_map(self):
        chain = ParsedChain(
            nodes=[
                ParsedNode(node_id="a", node_type="trigger"),
                ParsedNode(node_id="b", node_type="detector"),
            ]
        )
        assert chain.node_map["a"].node_type == "trigger"
        assert chain.node_map["b"].node_type == "detector"
        assert chain.node_map.get("c") is None

    def test_adjacency(self):
        chain = ParsedChain(
            nodes=[
                ParsedNode(node_id="a", node_type="trigger"),
                ParsedNode(node_id="b", node_type="detector"),
                ParsedNode(node_id="c", node_type="action"),
            ],
            edges=[
                ParsedEdge(source_id="a", target_id="b"),
                ParsedEdge(source_id="b", target_id="c"),
            ],
        )
        assert chain.adjacency["a"] == ["b"]
        assert chain.adjacency["b"] == ["c"]
        assert chain.adjacency["c"] == []

    def test_reverse_adjacency(self):
        chain = ParsedChain(
            nodes=[
                ParsedNode(node_id="a", node_type="trigger"),
                ParsedNode(node_id="b", node_type="detector"),
            ],
            edges=[ParsedEdge(source_id="a", target_id="b")],
        )
        assert chain.reverse_adjacency["a"] == []
        assert chain.reverse_adjacency["b"] == ["a"]

    def test_get_outgoing_edges(self):
        chain = ParsedChain(
            nodes=[
                ParsedNode(node_id="a", node_type="trigger"),
                ParsedNode(node_id="b", node_type="detector"),
                ParsedNode(node_id="c", node_type="action"),
            ],
            edges=[
                ParsedEdge(edge_id="e1", source_id="a", target_id="b"),
                ParsedEdge(edge_id="e2", source_id="a", target_id="c"),
            ],
        )
        assert len(chain.get_outgoing_edges("a")) == 2
        assert len(chain.get_outgoing_edges("b")) == 0

    def test_get_incoming_edges(self):
        chain = ParsedChain(
            nodes=[
                ParsedNode(node_id="a", node_type="trigger"),
                ParsedNode(node_id="b", node_type="detector"),
            ],
            edges=[ParsedEdge(source_id="a", target_id="b")],
        )
        assert len(chain.get_incoming_edges("b")) == 1
        assert len(chain.get_incoming_edges("a")) == 0

    def test_get_edges_by_source_port(self):
        chain = ParsedChain(
            nodes=[
                ParsedNode(node_id="a", node_type="comparator"),
                ParsedNode(node_id="b", node_type="action"),
                ParsedNode(node_id="c", node_type="action"),
            ],
            edges=[
                ParsedEdge(source_id="a", source_port="true", target_id="b"),
                ParsedEdge(source_id="a", source_port="false", target_id="c"),
            ],
        )
        true_edges = chain.get_edges_by_source_port("a", "true")
        assert len(true_edges) == 1
        assert true_edges[0].target_id == "b"

        false_edges = chain.get_edges_by_source_port("a", "false")
        assert len(false_edges) == 1
        assert false_edges[0].target_id == "c"


class TestChainParser:

    def test_parse_simple(self):
        config = {
            "nodes": [
                {"id": "t1", "type": "alert_trigger", "label": "Trigger"},
                {"id": "d1", "type": "gas_price_detector", "config": {"threshold": 80}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "target": "d1"},
            ],
        }
        chain = ChainParser.parse(config)

        assert len(chain.nodes) == 2
        assert chain.nodes[0].node_id == "t1"
        assert chain.nodes[1].config == {"threshold": 80}
        assert len(chain.edges) == 1
        assert chain.edges[0].source_id == "t1"

    def test_parse_empty(self):
        chain = ChainParser.parse({})
        assert len(chain.nodes) == 0
        assert len(chain.edges) == 0

    def test_parse_with_positions(self):
        config = {
            "nodes": [
                {"id": "t1", "type": "alert_trigger", "position": {"x": 100, "y": 200}},
            ],
            "edges": [],
        }
        chain = ChainParser.parse(config)
        assert chain.nodes[0].position == {"x": 100, "y": 200}

    def test_parse_with_handles(self):
        config = {
            "nodes": [
                {"id": "c1", "type": "comparator"},
                {"id": "a1", "type": "action"},
            ],
            "edges": [
                {
                    "source": "c1", "sourceHandle": "true",
                    "target": "a1", "targetHandle": "input",
                },
            ],
        }
        chain = ChainParser.parse(config)
        assert chain.edges[0].source_port == "true"
        assert chain.edges[0].target_port == "input"

    def test_to_dict(self):
        chain = ParsedChain(
            nodes=[ParsedNode(node_id="n1", node_type="trigger", label="T")],
            edges=[ParsedEdge(edge_id="e1", source_id="n1", target_id="n2")],
        )
        data = ChainParser.to_dict(chain)
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "n1"
        assert len(data["edges"]) == 1
        assert data["edges"][0]["source"] == "n1"

    def test_roundtrip(self):
        config = {
            "nodes": [
                {"id": "t1", "type": "alert_trigger", "label": "T", "config": {}, "position": {"x": 0}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "sourcePort": "output", "target": "d1", "targetPort": "input"},
            ],
        }
        chain = ChainParser.parse(config)
        data = ChainParser.to_dict(chain)
        chain2 = ChainParser.parse(data)

        assert len(chain2.nodes) == 1
        assert chain2.edges[0].source_port == "output"
