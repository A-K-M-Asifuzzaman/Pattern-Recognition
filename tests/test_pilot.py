import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from topodelta_qa.dataset import generate, input_exports, read_jsonl, split_schedule
from topodelta_qa.evaluate import edge_scores, evaluate_records, load_predictions, parse_delta
from topodelta_qa.render import RenderError, positions, scene, unchanged_geometry, validate_scene
from topodelta_qa.schema import Config, Graph, Question
from topodelta_qa.semantics import certificate, cross_split_duplicates, edit, isomorphic, reference_answer, solve, valid_certificate
from topodelta_qa.verify import validate_dataset, validate_group


def graph(edges=()):
    return Graph(tuple("ABCDEF"), tuple(sorted(edges)))


def q(task, source="A", target="E"):
    return Question("q", task, source, target)


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.g = graph([("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("D", "E")])

    def test_primary_and_reference_positive_negative_unreachable(self):
        cases = [(q("reachability"), True), (q("reachability", "E", "A"), False),
                 (q("shortest_path"), 3), (q("shortest_path", "A", "F"), "unreachable"),
                 (q("direct_edge", "B", "D"), True), (q("direct_edge", "D", "B"), False)]
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(solve(self.g, query), expected)
                self.assertEqual(reference_answer(self.g, query), expected)
                self.assertTrue(valid_certificate(self.g, query, expected, certificate(self.g, query)))

    def test_all_edit_operations_and_reversal_delta(self):
        for operation, operand, expected_added, expected_deleted in (
            ("addition", ("E", "F"), [["E", "F"]], []),
            ("deletion", ("A", "B"), [], [["A", "B"]]),
            ("reversal", ("A", "B"), [["B", "A"]], [["A", "B"]]),
        ):
            changed, delta = edit(self.g, operation, operand)
            self.assertEqual(delta["added"], expected_added)
            self.assertEqual(delta["deleted"], expected_deleted)
            self.assertEqual(delta["operation_count"], 1)
            self.assertEqual(delta["directed_set_difference_count"], 2 if operation == "reversal" else 1)
            self.assertEqual(changed.nodes, self.g.nodes)
        for operation, operand in (("addition", ("A", "B")), ("deletion", ("E", "A")),
                                   ("reversal", ("E", "A")), ("addition", ("A", "A"))):
            with self.assertRaises(ValueError):
                edit(self.g, operation, operand)
        reciprocal, _ = edit(self.g, "addition", ("B", "A"))
        with self.assertRaises(ValueError):
            edit(reciprocal, "reversal", ("A", "B"))

    def test_one_edit_different_question_relevance(self):
        changed, _ = edit(self.g, "deletion", ("A", "B"))
        edge_question, path_question = q("direct_edge", "A", "B"), q("reachability")
        self.assertNotEqual(solve(self.g, edge_question), solve(changed, edge_question))
        self.assertEqual(solve(self.g, path_question), solve(changed, path_question))

    def test_multiple_valid_paths_and_certificates(self):
        for path in (["A", "B", "D", "E"], ["A", "C", "D", "E"]):
            self.assertTrue(valid_certificate(self.g, q("reachability"), True, {"kind": "path", "path": path}))
            cert = certificate(self.g, q("shortest_path"))
            cert["path"] = path
            self.assertTrue(valid_certificate(self.g, q("shortest_path"), 3, cert))

    def test_invalid_certificates_and_explicit_absence(self):
        self.assertFalse(valid_certificate(self.g, q("reachability"), True, {"kind": "path", "path": ["A", "E"]}))
        self.assertFalse(valid_certificate(self.g, q("reachability"), True, []))
        neg = q("reachability", "E", "A")
        self.assertFalse(valid_certificate(self.g, neg, False, {"kind": "reachable_set", "nodes": []}))
        self.assertFalse(valid_certificate(self.g, neg, False, {"kind": "reachable_set", "nodes": ["E", "F"]}))
        self.assertFalse(valid_certificate(self.g, q("direct_edge", "E", "A"), False, {}))
        self.assertFalse(valid_certificate(self.g, q("direct_edge", "E", "A"), False, {"kind": "edge_claim", "source": "A", "target": "E", "present": False}))
        cert = certificate(self.g, q("shortest_path"))
        cert["distances"]["D"] = 1
        self.assertFalse(valid_certificate(self.g, q("shortest_path"), 3, cert))
        cert = certificate(self.g, q("shortest_path"))
        cert["path"] = ["A", "B", "A", "C", "D", "E"]
        self.assertFalse(valid_certificate(self.g, q("shortest_path"), 3, cert))
        self.assertFalse(valid_certificate(self.g, q("shortest_path"), True, certificate(self.g, q("shortest_path"))))

    def test_exact_isomorphism_ignores_labels_but_not_structure(self):
        relabel = dict(zip("ABCDEF", "UVWXYZ"))
        renamed = Graph(tuple("UVWXYZ"), tuple(sorted((relabel[u], relabel[v]) for u, v in self.g.edges)))
        self.assertTrue(isomorphic(self.g, renamed))
        g1 = graph(list(zip("ABCDEF", "BCDEFA")))
        g2 = graph(list(zip("ABCDEF", "BCAEFD")))
        self.assertFalse(isomorphic(g1, g2))  # Same node/edge counts and degree signatures.
        groups = [{"id": "a", "split": "train", "variants": [{"id": "a1", "graph": self.g.json()}]},
                  {"id": "b", "split": "test", "variants": [{"id": "b1", "graph": renamed.json()}]}]
        self.assertTrue(cross_split_duplicates(groups))
        groups[1]["split"] = "train"
        self.assertFalse(cross_split_duplicates(groups))


class RenderingTests(unittest.TestCase):
    def test_crossings_and_unreadable_labels_rejected(self):
        points = {"A": [100, 100], "B": [700, 700], "C": [100, 700], "D": [700, 100], "E": [400, 100], "F": [400, 700]}
        with self.assertRaises(RenderError):
            validate_scene(graph([("A", "B"), ("C", "D")]), scene(graph([("A", "B"), ("C", "D")]), points, 0))
        labels = ("AAAAAAA", "B", "C", "D", "E", "F")
        g = Graph(labels, ())
        with self.assertRaises(RenderError):
            validate_scene(g, scene(g, positions(list(labels), 0), 0))

    def test_geometry_tamper_and_unchanged_edges(self):
        g = graph([("A", "B"), ("C", "D")])
        p = positions(list(g.nodes), 0.1)
        original = scene(g, p, 0)
        changed, _ = edit(g, "reversal", ("A", "B"))
        edited = scene(changed, p, 0)
        self.assertTrue(unchanged_geometry(original, edited, {("C", "D")}))
        edited["edges"][0]["arrowhead"][0][0] += 20
        with self.assertRaises(RenderError):
            validate_scene(changed, edited)


class DatasetAndMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.config = Config(groups=6, max_attempts=600, train_fraction=0.5, validation_fraction=0.2, bootstrap_replicates=50)
        cls.first = cls.root / "first"
        generate(cls.config, cls.first)
        cls.groups = read_jsonl(cls.first / "gold/groups.jsonl")
        from topodelta_qa.identity import read_key
        cls.single, cls.paired, cls.sg, cls.pg = input_exports(cls.groups, read_key(cls.first / "gold/id_key.json"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def single_oracle(self):
        return {r["id"]: {"id": r["id"], "protocol": "single", "answer": r["answer"], "certificate": r["certificate"]} for r in self.sg}

    def paired_oracle(self):
        return {r["id"]: {"id": r["id"], "protocol": "paired", "answers": r["answers"], "certificates": r["certificates"], "delta": r["delta"]} for r in self.pg}

    def test_generated_dataset_and_split_isolation(self):
        self.assertEqual(validate_dataset(self.first)["status"], "passed")
        self.assertEqual(Counter(g["split"] for g in self.groups), {"train": 3, "validation": 1, "test": 2})
        self.assertEqual(split_schedule(self.config), split_schedule(self.config))
        self.assertFalse(cross_split_duplicates(self.groups))
        for group in self.groups:
            validate_group(group)
            for row in self.single + self.paired:
                if row["group_id"] == group["id"]:
                    self.assertEqual(row["split"], group["split"])
        self.assertEqual({r["id"] for r in self.sg}, {r["id"] for r in self.single})
        for row in self.single + self.paired:
            self.assertFalse(set(row) & {"answers", "graph", "certificates", "relevance", "role", "edit", "delta", "mask"})
        with self.assertRaises(ValueError):
            generate(self.config, self.first)

    def test_repeat_generation_byte_reproducibility(self):
        second = self.root / "second"
        generate(self.config, second)
        first_files = {p.relative_to(self.first): p.read_bytes() for p in self.first.rglob("*") if p.is_file()}
        second_files = {p.relative_to(second): p.read_bytes() for p in second.rglob("*") if p.is_file()}
        self.assertEqual(first_files, second_files)

    def test_rejects_corrupted_saved_metadata(self):
        group = copy.deepcopy(self.groups[0])
        group["variants"][2]["edit"]["directed_set_difference_count"] = 99
        with self.assertRaises(ValueError):
            validate_group(group)
        group = copy.deepcopy(self.groups[0])
        group["variants"][1]["graph"]["edges"].pop()
        with self.assertRaises(ValueError):
            validate_group(group)

    def test_single_oracle_and_deliberately_wrong_missing(self):
        predictions = self.single_oracle()
        good = evaluate_records(self.groups, self.sg, self.pg, predictions, "single", 50, 4)
        for name in ("per_image_answer_accuracy", "redraw_pair_accuracy", "relevant_edit_pair_accuracy", "irrelevant_edit_pair_accuracy", "certificate_validity", "joint_success"):
            self.assertEqual(good["metrics"][name]["value"], 1)
            self.assertEqual(good["metrics"][name]["ci95"], [1, 1])
        self.assertIsNone(good["metrics"]["edge_delta_f1"]["value"])
        pair = next(r for r in self.pg if r["pair_kind"] == "redraw")
        selected = [r for r in self.sg if r["question_id"] == pair["question_id"] and r["variant_id"] in pair["variant_ids"]]
        for row in selected:
            predictions[row["id"]]["answer"] = "unreachable" if type(row["answer"]) is int else False if row["answer"] is True else True if row["answer"] is False else 999
            predictions[row["id"]]["certificate"] = {}
        wrong = evaluate_records(self.groups, self.sg, self.pg, predictions, "single", 50, 4)
        self.assertAlmostEqual(wrong["metrics"]["per_image_answer_accuracy"]["value"], 46 / 48)
        self.assertEqual(wrong["metrics"]["raw_redraw_agreement"]["value"], 1)
        self.assertAlmostEqual(wrong["metrics"]["redraw_pair_accuracy"]["value"], 11 / 12)
        predictions.pop(next(iter(predictions)))
        missing = evaluate_records(self.groups, self.sg, self.pg, predictions, "single", 50, 4)
        self.assertEqual(missing["handling"]["missing_predictions"], 1)
        empty = evaluate_records(self.groups, self.sg, self.pg, {}, "single", 50, 4)
        self.assertEqual(empty["metrics"]["raw_redraw_agreement"]["value"], 0)
        self.assertEqual(empty["metrics"]["per_image_answer_accuracy"]["denominator"], 48)
        self.assertEqual(empty["metrics"]["per_image_answer_accuracy"]["value"], 0)

    def test_paired_oracle_joint_and_wrong_second_answer(self):
        predictions = copy.deepcopy(self.paired_oracle())
        good = evaluate_records(self.groups, self.sg, self.pg, predictions, "paired", 50, 1)
        self.assertTrue(all(metric["value"] == 1 for metric in good["metrics"].values()))
        row = next(r for r in self.pg if r["pair_kind"] == "relevant_edit")
        predictions[row["id"]]["answers"][1] = None
        wrong = evaluate_records(self.groups, self.sg, self.pg, predictions, "paired", 50, 1)
        relevant_count = sum(r["pair_kind"] == "relevant_edit" for r in self.pg)
        self.assertAlmostEqual(wrong["metrics"]["relevant_edit_pair_accuracy"]["value"], (relevant_count - 1) / relevant_count)
        self.assertAlmostEqual(wrong["metrics"]["joint_success"]["value"], 35 / 36)
        self.assertEqual(wrong["metrics"]["edge_delta_f1"]["value"], 1)
        empty = evaluate_records(self.groups, self.sg, self.pg, {}, "paired", 50, 1)
        self.assertEqual(empty["metrics"]["edge_delta_f1"]["value"], 0)
        self.assertEqual(empty["metrics"]["joint_success"]["value"], 0)
        self.assertEqual(empty["handling"]["missing_predictions"], 36)

    def test_wrong_delta_and_certificate_penalize_joint_independently(self):
        predictions = copy.deepcopy(self.paired_oracle())
        row = next(r for r in self.pg if r["delta"]["added"] or r["delta"]["deleted"])
        predictions[row["id"]]["delta"] = {"added": [], "deleted": []}
        predictions[row["id"]]["certificates"][0] = {}
        result = evaluate_records(self.groups, self.sg, self.pg, predictions, "paired", 50, 1)
        self.assertEqual(result["metrics"]["per_image_answer_accuracy"]["value"], 1)
        self.assertAlmostEqual(result["metrics"]["edge_delta_f1"]["value"], 35 / 36)
        self.assertAlmostEqual(result["metrics"]["certificate_validity"]["value"], 71 / 72)
        self.assertAlmostEqual(result["metrics"]["joint_success"]["value"], 35 / 36)
        self.assertEqual(result, evaluate_records(self.groups, self.sg, self.pg, predictions, "paired", 50, 1))

    def test_prediction_input_errors(self):
        path = self.root / "predictions.jsonl"
        ident = self.sg[0]["id"]
        path.write_text('{broken\n{}\n' + json.dumps({"id": ident, "protocol": "single", "answer": None}) + '\n')
        predictions, errors = load_predictions(path, "single", {ident})
        self.assertEqual(len(predictions), 1)
        self.assertEqual(errors, {"malformed_lines": 1, "invalid_rows_without_id": 1})
        for rows in ([{"id": ident, "protocol": "paired"}], [{"id": "unknown", "protocol": "single"}],
                     [{"id": ident, "protocol": "single"}] * 2):
            path.write_text("\n".join(json.dumps(r) for r in rows))
            with self.assertRaises(ValueError):
                load_predictions(path, "single", {ident})

    def test_visible_generation_exhaustion(self):
        from unittest.mock import patch
        root = self.root / "failed"
        with patch("topodelta_qa.dataset.propose", side_effect=RenderError("forced_failure")):
            with self.assertRaises(RuntimeError):
                generate(Config(groups=1, max_attempts=2), root)
        summary = json.loads((root / "reports/generation.json").read_text())
        self.assertEqual((summary["attempted"], summary["rejected"], summary["accepted"]), (2, 2, 0))
        self.assertEqual(summary["status"], "failed")
        self.assertFalse((root / "manifest.json").exists())


class DeltaMetricTests(unittest.TestCase):
    def test_empty_sets_and_signed_reversal(self):
        self.assertEqual(edge_scores(set(), set()), (1, 1, 1))
        self.assertEqual(edge_scores(set(), {1}), (0, 0, 0))
        self.assertEqual(edge_scores({1}, set()), (0, 0, 0))
        self.assertEqual(edge_scores({1, 2}, {2, 3}), (0.5, 0.5, 0.5))
        gold = {("added", "B", "A"), ("deleted", "A", "B")}
        p, r, f = edge_scores({("added", "B", "A")}, gold)
        self.assertEqual((p, r), (1, 0.5))
        self.assertAlmostEqual(f, 2 / 3)
        self.assertIsNone(parse_delta({"added": [["A", "B"], ["A", "B"]], "deleted": []}, tuple("ABCDEF")))
        self.assertIsNone(parse_delta({"added": [["A", "B"]], "deleted": [["A", "B"]]}, tuple("ABCDEF")))
        self.assertIsNone(parse_delta({"added": [["A", "X"]], "deleted": []}, tuple("ABCDEF")))


if __name__ == "__main__":
    unittest.main()
