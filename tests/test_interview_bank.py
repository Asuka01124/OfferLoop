"""Exercise freshness, provenance, deduplication, and interview state invariants."""

from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "interview_bank.py"
SPEC = importlib.util.spec_from_file_location("interview_bank", SCRIPT)
bank = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bank)
AS_OF = date(2026, 10, 26)
ROLE, DIRECTION = "后端开发", "Java"


def source(index=1, questions=None):
    # All source URLs, evidence, and people in this fixture are synthetic.
    return {
        "url": f"https://example.com/post/{index}", "title": "测试面经", "platform": "测试平台",
        "author": "测试作者", "published_at": "2026-10-20", "interview_at": "2026-10-19",
        "company": "测试公司", "role": ROLE, "round": "一面", "internship_type": "日常实习",
        "personal_account": True, "is_original": True, "access_status": "full",
        "verification": {"method": "web", "verified_at": AS_OF.isoformat(),
                         "publication_kind": "first_published", "publication_excerpt": "首次发布2026-10-20",
                         "personal_excerpt": "我昨天参加了一面", "internship_excerpt": "投递日常实习"},
        "questions": questions if questions is not None else [question()],
    }


def question(value="HashMap的底层实现是什么？", tags=None):
    return {"text": value, "kind": "基础问答", "difficulty": "基础",
            "tags": tags or ["Java", "HashMap"], "followups": ["为什么使用红黑树？"]}


def rubric():
    return {"prepared_at": AS_OF.isoformat(), "reference_answer": "这是测试使用的参考答案。",
            "criteria": [{"id": "correctness", "label": "正确性", "max_points": 6,
                          "expected": ["测试关键点"]},
                         {"id": "reasoning", "label": "解释", "max_points": 4,
                          "expected": ["测试边界"]}],
            "references": [{"url": "https://example.com/docs", "title": "测试技术资料",
                            "checked_at": AS_OF.isoformat()}]}


def response(qid, scores=(5, 3), answer_text="这是使用者的原始回答。"):
    return {"question_id": qid, "answer": answer_text, "hints_used": 0,
            "grade": {"criteria": [{"id": "correctness", "score": scores[0], "reason": "测试评分理由一"},
                                   {"id": "reasoning", "score": scores[1], "reason": "测试评分理由二"}],
                      "strengths": ["测试优点"], "gaps": ["测试遗漏"]}}


class BankTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def ingest(self, sources):
        return bank.ingest(self.root, ROLE, DIRECTION, {"sources": sources}, AS_OF)

    def load(self):
        return bank.load_bank(self.root, ROLE, DIRECTION)

    def ready(self, count=2):
        questions = [question(f"测试问题{i}？", [f"主题{i}"]) for i in range(count)]
        self.ingest([source(questions=questions)])
        ids = list(self.load()["questions"])
        bank.prepare(self.root, ROLE, DIRECTION,
                     {"rubrics": [{"question_id": qid, "rubric": rubric()} for qid in ids]}, AS_OF)
        return ids

    def start(self, ids, mode="practice", profile="default"):
        return bank.start(self.root, ROLE, DIRECTION, AS_OF, mode=mode,
                          profile=profile, question_ids=ids)

    def test_default_data_root_is_agent_independent_and_overrides_are_respected(self):
        with mock.patch.dict(bank.os.environ, {}, clear=True), mock.patch.object(bank.Path, "home", return_value=self.root):
            self.assertEqual(bank.parser().parse_args(["catalog"]).root, self.root / ".interview-data")
        custom = self.root / "shared-data"
        with mock.patch.dict(bank.os.environ, {"INTERNSHIP_INTERVIEW_DATA": str(custom)}, clear=True):
            self.assertEqual(bank.parser().parse_args(["catalog"]).root, custom)
            explicit = self.root / "explicit-data"
            self.assertEqual(bank.parser().parse_args(["--root", str(explicit), "catalog"]).root, explicit)

    def test_window_contains_exactly_ninety_calendar_days(self):
        result = bank.window(AS_OF)
        self.assertEqual((bank.day(result["end"]) - bank.day(result["start"])).days, 89)
        self.assertTrue(bank.recent(result["start"], AS_OF))
        self.assertFalse(bank.recent((AS_OF - timedelta(days=90)).isoformat(), AS_OF))
        self.assertFalse(bank.recent((AS_OF + timedelta(days=1)).isoformat(), AS_OF))

    def test_original_recent_source_and_provenance_are_saved(self):
        report = self.ingest([source()])
        self.assertEqual(report["counts"], {"accepted": 1, "pending": 0, "excluded": 0, "candidates": 1})
        data = self.load()
        item = next(iter(data["questions"].values()))
        sid = item["occurrences"][0]["source_id"]
        self.assertEqual(data["sources"][sid]["verification"]["personal_excerpt"], "我昨天参加了一面")
        self.assertEqual(item["occurrences"][0]["original_text"], question()["text"])
        self.assertEqual(report["stats"]["experiences_active"], 1)

    def test_invalid_candidates_do_not_create_a_bank(self):
        for patch, expected in [({"published_at": "2026-07-01"}, "excluded"),
                                ({"published_at": "2026-10-27"}, "excluded"),
                                ({"interview_at": "2026-07-01"}, "excluded"),
                                ({"interview_at": "2026-10-27"}, "excluded"),
                                ({"is_original": False}, "excluded"),
                                ({"personal_account": False}, "excluded"),
                                ({"internship_type": "社招"}, "excluded"),
                                ({"access_status": "login_required"}, "pending"),
                                ({"published_at": "2026-10"}, "pending")]:
            with self.subTest(patch=patch):
                item = source()
                item.update(patch)
                report = self.ingest([item])
                self.assertEqual(report["decisions"][0]["status"], expected)
                self.assertIsNone(report["bank_path"])
        self.assertFalse((self.root / "banks").exists())

    def test_modified_date_and_missing_evidence_are_not_accepted(self):
        a, b = source(1), source(2)
        a["verification"]["publication_kind"] = "modified"
        b["verification"].pop("personal_excerpt")
        result = self.ingest([a, b])
        self.assertEqual(result["counts"]["pending"], 2)

    def test_unknown_interview_date_is_kept_and_deprioritized(self):
        unknown = source(1, [question("未知日期的问题", ["共同主题"])])
        unknown["interview_at"] = None
        known = source(2, [question("明确日期的问题", ["共同主题"])])
        result = self.ingest([unknown, known])
        self.assertEqual(result["stats"]["sources_without_interview_date"], 1)
        picked = bank.select(self.root, ROLE, DIRECTION, AS_OF, count=1)
        self.assertEqual(picked["questions"][0]["text"], "明确日期的问题")

    def test_reimport_is_idempotent_and_tracking_does_not_duplicate_source(self):
        self.ingest([source()])
        item = source()
        item["url"] += "?utm_source=test&spm=123#section"
        report = self.ingest([item])
        self.assertEqual(report["new_questions"], 0)
        self.assertEqual(report["new_occurrences"], 0)
        self.assertEqual(len(self.load()["sources"]), 1)
        self.assertEqual(len(next(iter(self.load()["questions"].values()))["occurrences"]), 1)

    def test_same_question_keeps_multiple_sources_and_shared_experience(self):
        a, b = source(1), source(2)
        a["experience_key"] = b["experience_key"] = "same-person-same-interview"
        report = self.ingest([a, b])
        self.assertEqual(report["new_questions"], 1)
        self.assertEqual(report["stats"]["sources_active"], 2)
        self.assertEqual(report["stats"]["experiences_active"], 1)
        picked = bank.select(self.root, ROLE, DIRECTION, AS_OF, count=1)
        self.assertEqual(picked["questions"][0]["experience_count"], 1)

    def test_semantic_merge_requires_explicit_existing_id(self):
        self.ingest([source()])
        qid = next(iter(self.load()["questions"]))
        item = question("说说HashMap怎样实现")
        item["merge_into"] = qid
        report = self.ingest([source(2, [item])])
        self.assertEqual(report["merged_occurrences"], 1)
        self.assertEqual(len(self.load()["questions"]), 1)
        self.assertEqual(len(self.load()["questions"][qid]["occurrences"]), 2)

    def test_invalid_source_merge_is_atomic(self):
        item = source(questions=[question("新问题"), {**question("别的问题"), "merge_into": "q_missing"}])
        report = self.ingest([item])
        self.assertEqual(report["counts"]["pending"], 1)
        self.assertIsNone(report["bank_path"])

    def test_distinct_code_semantics_are_not_normalized_together(self):
        for left, right in [("C++", "C#"), ("a!=b", "a=b"), ("1.0", "10"), ("a+b", "ab"),
                            ("x==X", "x==x")]:
            self.assertNotEqual(bank.normalized(left), bank.normalized(right))

    def test_expired_sources_are_filtered_when_selecting_without_deleting_history(self):
        self.ingest([source()])
        result = bank.select(self.root, ROLE, DIRECTION, AS_OF + timedelta(days=100), count=1)
        self.assertEqual(result["available"], 0)
        self.assertEqual(len(self.load()["questions"]), 1)

    def test_company_and_topic_filters_apply_to_active_occurrences(self):
        a, b = source(1), source(2)
        a["company"], b["company"] = "甲公司", "乙公司"
        self.ingest([a, b])
        result = bank.select(self.root, ROLE, DIRECTION, AS_OF, count=1, company="甲", topics=["HashMap"])
        item = result["questions"][0]
        self.assertEqual(len(item["sources"]), 1)
        self.assertEqual(next(iter(item["sources"].values()))["company"], "甲公司")
        self.assertEqual(bank.select(self.root, ROLE, DIRECTION, AS_OF, count=1, topics=["Redis"])["selected"], 0)

    def test_path_traversal_and_reserved_names_are_rejected(self):
        for name in ["../外部", "..", "C:\\temp", "a/b", "CON", "a.", ".hidden"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                bank.bank_path(self.root, name, DIRECTION)

    def test_malformed_existing_bank_is_not_overwritten(self):
        path = bank.bank_path(self.root, ROLE, DIRECTION)
        path.parent.mkdir(parents=True)
        path.write_text("not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.ingest([source()])
        self.assertEqual(path.read_text(encoding="utf-8"), "not json")

    def test_concurrent_writer_lock_is_respected(self):
        with bank.locked(self.root):
            with self.assertRaises(ValueError):
                self.ingest([source()])
        self.assertFalse((self.root / ".write.lock").exists())

    def test_rubric_must_be_ten_points_with_references_and_unique_dimensions(self):
        for mutate in [lambda r: r["criteria"][0].update(max_points=5),
                       lambda r: r.update(references=[]),
                       lambda r: r["criteria"][1].update(id="correctness"),
                       lambda r: r["criteria"][0].update(max_points=float("nan"))]:
            item = rubric()
            mutate(item)
            with self.assertRaises(ValueError):
                bank.validate_rubric(item, AS_OF)

    def test_insufficient_or_unprepared_bank_cannot_start(self):
        self.ingest([source()])
        with self.assertRaises(ValueError):
            bank.start(self.root, ROLE, DIRECTION, AS_OF, count=1)
        ids = self.ready(1)
        with self.assertRaises(ValueError):
            self.start(ids + ["q_missing"])
        self.assertFalse((self.root / "profiles").exists())

    def test_start_returns_no_answers_and_snapshot_survives_bank_edits(self):
        ids = self.ready(1)
        started = self.start(ids)
        self.assertNotIn("rubric", json.dumps(started))
        changed = rubric()
        changed["reference_answer"] = "后来修改的答案"
        bank.prepare(self.root, ROLE, DIRECTION, {"rubrics": [{"question_id": ids[0], "rubric": changed}]}, AS_OF)
        stored = bank.load_session(self.root, "default", started["session_id"])
        self.assertEqual(stored["questions"][0]["rubric"]["reference_answer"], rubric()["reference_answer"])

    def test_out_of_order_duplicate_and_excess_scores_do_not_modify_session(self):
        ids = self.ready()
        started = self.start(ids)
        sid = started["session_id"]
        for payload in [response(ids[1]), response(ids[0], (7, 3)), response(ids[0], (True, 3))]:
            with self.assertRaises(ValueError):
                bank.answer(self.root, "default", sid, payload, AS_OF)
        self.assertEqual(len(bank.load_session(self.root, "default", sid)["answers"]), 0)
        bank.answer(self.root, "default", sid, response(ids[0]), AS_OF)
        with self.assertRaises(ValueError):
            bank.answer(self.root, "default", sid, response(ids[0]), AS_OF)

    def test_practice_feedback_and_profile_isolation(self):
        ids = self.ready(1)
        sid = self.start(ids)["session_id"]
        result = bank.answer(self.root, "default", sid, response(ids[0]), AS_OF)
        self.assertEqual(result["feedback"]["score"], 8)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(bank.select(self.root, ROLE, DIRECTION, AS_OF, count=1, review="unseen")["available"], 0)
        self.assertEqual(bank.select(self.root, ROLE, DIRECTION, AS_OF, count=1, review="unseen", profile="另一个人")["available"], 1)

    def test_mock_does_not_leak_grades_before_completion(self):
        ids = self.ready()
        sid = self.start(ids, mode="mock")["session_id"]
        result = bank.answer(self.root, "default", sid, response(ids[0]), AS_OF)
        self.assertNotIn("feedback", result)
        self.assertNotIn("score", json.dumps(bank.summary(self.root, "default", sid)))
        bank.answer(self.root, "default", sid, response(ids[1], (4, 2)), AS_OF)
        report = bank.summary(self.root, "default", sid)
        self.assertEqual(report["average_score"], 7)
        self.assertEqual(len(report["details"]), 2)

    def test_finish_early_does_not_score_unanswered_questions_as_zero(self):
        ids = self.ready()
        sid = self.start(ids, mode="mock")["session_id"]
        bank.answer(self.root, "default", sid, response(ids[0]), AS_OF)
        result = bank.summary(self.root, "default", sid, finish=True)
        self.assertEqual(result["status"], "finished_early")
        self.assertEqual(result["average_score"], 8)
        self.assertIsNone(result["details"][1]["answer"])

    def test_hints_make_a_high_scoring_question_eligible_for_review(self):
        ids = self.ready(1)
        sid = self.start(ids)["session_id"]
        payload = response(ids[0], (6, 4))
        payload["hints_used"] = 1
        bank.answer(self.root, "default", sid, payload, AS_OF)
        self.assertEqual(bank.select(self.root, ROLE, DIRECTION, AS_OF, count=1, review="weak")["available"], 1)

    def test_followup_provenance_and_empty_answer_are_checked(self):
        ids = self.ready(1)
        sid = self.start(ids)["session_id"]
        payload = response(ids[0])
        payload["followups"] = [{"question": "模型新增的问题", "answer": "回答", "origin": "source"}]
        with self.assertRaises(ValueError):
            bank.answer(self.root, "default", sid, payload, AS_OF)
        with self.assertRaises(ValueError):
            bank.answer(self.root, "default", sid, response(ids[0], (0, 0), ""), AS_OF)
        skipped = response(ids[0], (0, 0), "")
        skipped["skipped"] = True
        self.assertEqual(bank.answer(self.root, "default", sid, skipped, AS_OF)["feedback"]["score"], 0)

    def test_explicit_question_id_is_not_lost_in_large_banks(self):
        ids = self.ready(105)
        chosen = ids[-1]
        self.assertEqual(self.start([chosen])["next_question"]["id"], chosen)

    def test_cli_unicode_roundtrip_and_error_exit(self):
        fixture = self.root / "batch.json"
        bank.atomic_json(fixture, {"sources": [source()]})
        base = [sys.executable, str(SCRIPT), "--root", str(self.root / "cli"), "--as-of", AS_OF.isoformat()]
        imported = subprocess.run(base + ["ingest", "--role", ROLE, "--direction", DIRECTION,
                                          "--input", str(fixture)], capture_output=True, encoding="utf-8")
        self.assertEqual(imported.returncode, 0, imported.stderr)
        self.assertEqual(json.loads(imported.stdout)["counts"]["accepted"], 1)
        catalog = subprocess.run(base + ["catalog"], capture_output=True, encoding="utf-8")
        self.assertEqual(json.loads(catalog.stdout)["banks"][0]["role"], ROLE)
        missing = subprocess.run(base + ["select", "--role", "不存在", "--direction", DIRECTION],
                                 capture_output=True, encoding="utf-8")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("error", json.loads(missing.stderr))

    def test_complete_cli_workflow_with_saved_rubric_and_answer(self):
        base = [sys.executable, str(SCRIPT), "--root", str(self.root / "e2e"), "--as-of", AS_OF.isoformat()]

        def run(*arguments):
            result = subprocess.run(base + list(arguments), capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        def payload_file(name, data):
            path = self.root / name
            bank.atomic_json(path, data)
            return str(path)

        batch = payload_file("batch.json", {"sources": [source()]})
        run("ingest", "--role", ROLE, "--direction", DIRECTION, "--input", batch)
        selected = run("select", "--role", ROLE, "--direction", DIRECTION, "--count", "1")
        qid = selected["questions"][0]["id"]
        rubrics = payload_file("rubrics.json", {"rubrics": [{"question_id": qid, "rubric": rubric()}]})
        run("prepare", "--role", ROLE, "--direction", DIRECTION, "--input", rubrics)
        session = run("start", "--role", ROLE, "--direction", DIRECTION,
                      "--mode", "mock", "--question-ids", qid)
        sid = session["session_id"]
        resumable = run("sessions")["sessions"]
        self.assertEqual(resumable[0]["session_id"], sid)
        self.assertNotIn("rubric", json.dumps(resumable))
        self.assertEqual(run("show", "--session", sid)["next_question"]["id"], qid)
        self.assertNotIn("details", run("summary", "--session", sid))
        answer_file = payload_file("answer.json", response(qid))
        completed = run("answer", "--session", sid, "--input", answer_file)
        self.assertEqual(completed["status"], "completed")
        self.assertNotIn("feedback", completed)
        self.assertEqual(run("summary", "--session", sid)["average_score"], 8)


if __name__ == "__main__":
    unittest.main()
