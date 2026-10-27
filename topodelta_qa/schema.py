from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, NotRequired, TypeAlias, TypedDict

import yaml

Edge: TypeAlias = tuple[str, str]
Answer: TypeAlias = bool | int | Literal["unreachable"]
Task: TypeAlias = Literal["reachability", "shortest_path", "direct_edge"]
TASKS: tuple[Task, ...] = ("reachability", "shortest_path", "direct_edge")
OPERATIONS = ("addition", "deletion", "reversal")


@dataclass(frozen=True)
class Graph:
    nodes: tuple[str, ...]
    edges: tuple[Edge, ...]

    def __post_init__(self):
        if not 6 <= len(self.nodes) <= 12 or len(set(self.nodes)) != len(self.nodes):
            raise ValueError("Graphs require 6–12 unique nodes")
        if any(not isinstance(n, str) or not n for n in self.nodes):
            raise ValueError("Node labels must be nonempty strings")
        if len(set(self.edges)) != len(self.edges):
            raise ValueError("Parallel edges are forbidden")
        if any(u == v or u not in self.nodes or v not in self.nodes for u, v in self.edges):
            raise ValueError("Invalid directed edge")
        if self.nodes != tuple(sorted(self.nodes)) or self.edges != tuple(sorted(self.edges)):
            raise ValueError("Graph structure must be canonical")

    def json(self) -> dict:
        return asdict(self)

    @classmethod
    def parse(cls, value: dict) -> "Graph":
        if set(value) != {"nodes", "edges"}:
            raise ValueError("Unexpected graph fields")
        return cls(tuple(value["nodes"]), tuple(tuple(e) for e in value["edges"]))


@dataclass(frozen=True)
class Question:
    id: str
    task: Task
    source: str
    target: str

    def __post_init__(self):
        if self.task not in TASKS or self.source == self.target:
            raise ValueError("Invalid question")

    def text(self) -> str:
        u, v = self.source, self.target
        return {
            "reachability": f"Is there a directed path from {u} to {v}?",
            "shortest_path": f"What is the minimum number of directed edges in a path from {u} to {v}? Return 'unreachable' if none exists.",
            "direct_edge": f"Is there a directed edge from {u} to {v}?",
        }[self.task]

    def json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Config:
    seed: int = 20261027
    groups: int = 120
    max_attempts: int = 12000
    min_nodes: int = 6
    max_nodes: int = 12
    output: str = "outputs/pilot"
    train_fraction: float = 0.7
    validation_fraction: float = 0.15
    bootstrap_replicates: int = 1000

    def __post_init__(self):
        for name in ("seed", "groups", "max_attempts", "min_nodes", "max_nodes", "bootstrap_replicates"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if not 6 <= self.min_nodes <= self.max_nodes <= 12:
            raise ValueError("Node range must be within 6–12")
        if self.groups < 1 or self.max_attempts < self.groups or self.bootstrap_replicates < 1:
            raise ValueError("Invalid generation budget")
        if not 0 < self.train_fraction < 1 or not 0 < self.validation_fraction < 1 - self.train_fraction:
            raise ValueError("Invalid split fractions")
        if not isinstance(self.output, str) or not self.output:
            raise ValueError("Output must be a nonempty path")

    @classmethod
    def load(cls, path: Path) -> "Config":
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("Config must be a mapping")
        return cls(**data)


# Serialized record contracts; dataclasses and boundary validators enforce values.


class EditDelta(TypedDict):
    operation: Literal["addition", "deletion", "reversal"]
    operand: list[str]
    operation_count: int
    added: list[list[str]]
    deleted: list[list[str]]
    directed_set_difference_count: int


class NodeGeometry(TypedDict):
    label: str
    center: list[float]
    box: list[float]
    label_box: list[float]


class EdgeGeometry(TypedDict):
    edge: list[str]
    line: list[list[float]]
    arrowhead: list[list[float]]


class Scene(TypedDict):
    canvas: list[int]
    style: int
    nodes: list[NodeGeometry]
    edges: list[EdgeGeometry]


class PathCertificate(TypedDict):
    kind: Literal["path"]
    path: list[str]


class ReachableSetCertificate(TypedDict):
    kind: Literal["reachable_set"]
    nodes: list[str]


class ShortestPathCertificate(TypedDict):
    kind: Literal["shortest_path"]
    path: list[str]
    distances: dict[str, int | None]


class EdgeClaimCertificate(TypedDict):
    kind: Literal["edge_claim"]
    source: str
    target: str
    present: bool


Certificate: TypeAlias = PathCertificate | ReachableSetCertificate | ShortestPathCertificate | EdgeClaimCertificate


class VariantRecord(TypedDict):
    id: str
    role: Literal["original", "redraw", "edited"]
    graph: dict
    scene: Scene
    answers: dict[str, Answer]
    certificates: dict[str, Certificate]
    edit: EditDelta | None
    relevance: dict[str, bool]
    assets: dict[str, str]
    asset_hashes: NotRequired[dict[str, str]]
    semantic_changed_edges: NotRequired[dict[str, list[list[str]]]]
    pixel_diff: NotRequired[dict]


class GroupRecord(TypedDict):
    id: str
    split: Literal["train", "validation", "test"]
    attempt: int
    seed: int
    generator_version: str
    questions: list[dict]
    variants: list[VariantRecord]


class SinglePrediction(TypedDict):
    id: str
    protocol: Literal["single"]
    answer: Answer
    certificate: NotRequired[Certificate]


class PairedPrediction(TypedDict):
    id: str
    protocol: Literal["paired"]
    answers: list[Answer]
    certificates: NotRequired[list[Certificate]]
    delta: NotRequired[dict[str, list[list[str]]]]
