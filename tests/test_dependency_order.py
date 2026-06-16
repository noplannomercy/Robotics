from dependency_order import order_by_dependency


def _assert_dependency_invariant(ordered, edges):
    """모든 엣지(caller, callee)에서 callee가 caller보다 먼저 와야 한다."""
    pos = {name: i for i, name in enumerate(ordered)}
    for caller, callee in edges:
        if caller in pos and callee in pos:
            assert pos[callee] < pos[caller], f"{callee} must precede {caller}"


def test_linear_chain():
    # A는 B에, B는 C에 의존 → 처리 순서: C, B, A
    nodes = {"A", "B", "C"}
    edges = [("A", "B"), ("B", "C")]
    ordered, cycles = order_by_dependency(nodes, edges)
    assert cycles == []
    assert ordered == ["C", "B", "A"]


def test_independent_nodes_sorted():
    ordered, cycles = order_by_dependency({"X", "Y", "Z"}, [])
    assert ordered == ["X", "Y", "Z"]
    assert cycles == []


def test_diamond_invariant():
    nodes = {"A", "B", "C", "D"}
    edges = [("D", "B"), ("D", "C"), ("B", "A"), ("C", "A")]
    ordered, cycles = order_by_dependency(nodes, edges)
    assert cycles == []
    assert ordered[0] == "A"
    assert ordered[-1] == "D"
    _assert_dependency_invariant(ordered, edges)


def test_cycle_reported_not_ordered():
    # A↔B 순환, C는 A에 의존 → A,B,C 모두 순환에 막혀 ordered에 못 들어감
    nodes = {"A", "B", "C"}
    edges = [("A", "B"), ("B", "A"), ("C", "A")]
    ordered, cycles = order_by_dependency(nodes, edges)
    assert set(cycles) == {"A", "B", "C"}
    assert ordered == []


def test_unknown_edge_endpoints_ignored():
    ordered, cycles = order_by_dependency({"A"}, [("A", "GHOST"), ("GHOST", "A")])
    assert ordered == ["A"]
    assert cycles == []
