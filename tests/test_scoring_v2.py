"""Verify clarification, fact checks, evidence-based grading, and legacy scores."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_interview_bank import AS_OF, DIRECTION, ROLE, SCRIPT, bank, question, response, rubric, source


def dialogue(kind="clarification", key="r1"):
    return {"id": key, "kind": kind, "question": "你说的控制级具体指什么？",
            "answer": "我指的是流程指引，具体执行限制还取决于宿主。", "origin": "generated"}


def check(status="unverified"):
    item = {"id": "c1", "claim": "测试平台的工具数量限制", "scope": "测试平台v1，模型可见的工具",
            "status": status, "checked_at": AS_OF.isoformat(), "reason": "按明确的版本和统计范围核验"}
    if status != "unverified":
        item.update({"source_url": "https://example.com/tool-reference", "excerpt": "虚构测试证据：该版本按此范围统计。"})
    return item


class ScoringV2Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        bank.ingest(self.root, ROLE, DIRECTION,
                    {"sources": [source(questions=[question(f"测试问题{i}") for i in range(3)])]}, AS_OF)
        self.ids = list(bank.load_bank(self.root, ROLE, DIRECTION)["questions"])
        bank.prepare(self.root, ROLE, DIRECTION,
                     {"rubrics": [{"question_id": qid, "rubric": rubric()} for qid in self.ids]}, AS_OF)
        self.sid = self.start()

    def start(self, count=1, mode="practice"):
        return bank.start(self.root, ROLE, DIRECTION, AS_OF, mode=mode,
                          question_ids=self.ids[:count])["session_id"]

    def send(self, payload):
        return bank.answer(self.root, "default", self.sid, payload, AS_OF)

    def pending(self, status="pending_clarification"):
        payload = {"question_id": self.ids[0], "answer": "控制级", "status": status,
                   "reason": "回答含义需要确认", "next_prompt": "你说的控制级具体指什么？"}
        if status == "pending_verification":
            payload["evidence_checks"] = [check()]
        return payload

    def final(self, scores=(6, 4)):
        return response(self.ids[0], scores, "控制级")

    def test_pending_answer_has_no_score_and_does_not_advance(self):
        result = self.send(self.pending())
        self.assertEqual(result["answered"], 0)
        self.assertEqual(result["next_question"]["id"], self.ids[0])
        self.assertEqual(result["current_question_state"], "pending_clarification")
        self.assertNotIn("feedback", result)
        saved = bank.load_session(self.root, "default", self.sid)
        self.assertEqual(saved["answers"], [])
        self.assertNotIn("score", saved["draft"])
        bad = self.pending()
        bad["grade"] = self.final()["grade"]
        with self.assertRaises(ValueError):
            self.send(bad)

    def test_unresolved_ambiguity_cannot_be_scored_by_setting_readiness_flags(self):
        self.send(self.pending())
        with self.assertRaises(ValueError):
            self.send(self.final())
        self.assertEqual(bank.load_session(self.root, "default", self.sid)["answers"], [])

    def test_clarification_preserves_initial_answer_without_counting_as_a_hint(self):
        self.send(self.pending())
        payload = self.final()
        payload.update({"rounds": [dialogue()], "resolution": "使用者已明确控制级所指的范围"})
        result = self.send(payload)
        self.assertEqual(result["feedback"]["score"], 10)
        self.assertEqual(result["feedback"]["hints_used"], 0)
        self.assertEqual(result["feedback"]["clarifications_used"], 1)
        record = bank.load_session(self.root, "default", self.sid)["answers"][0]
        self.assertEqual(record["answer"], "控制级")
        self.assertEqual(record["rounds"][0]["answer"], dialogue()["answer"])
        self.assertEqual(bank.select(self.root, ROLE, DIRECTION, AS_OF, review="weak")["available"], 0)

    def test_cannot_relabel_clarification_as_hint_or_overwrite_initial_answer(self):
        self.send(self.pending())
        payload = self.final()
        payload.update({"rounds": [dialogue()], "resolution": "已澄清", "hints_used": 1})
        with self.assertRaises(ValueError):
            self.send(payload)
        payload.pop("hints_used")
        payload["answer"] = "改写后的首次回答"
        with self.assertRaises(ValueError):
            self.send(payload)
        self.assertEqual(bank.load_session(self.root, "default", self.sid)["draft"]["answer"], "控制级")

    def test_completed_round_ids_are_idempotent_and_immutable(self):
        payload = {"question_id": self.ids[0], "answer": "控制级", "status": "ready_to_score",
                   "reason": "已完成本题交流", "rounds": [dialogue("followup")]}
        self.send(payload)
        self.send(payload)
        self.assertEqual(len(bank.load_session(self.root, "default", self.sid)["draft"]["rounds"]), 1)
        payload["rounds"][0]["answer"] = "被覆盖的回答"
        with self.assertRaises(ValueError):
            self.send(payload)

    def test_rounds_cannot_store_premature_scores_or_feedback(self):
        for field, value in (("score", 2), ("feedback", "不正确")):
            payload = self.pending()
            payload["rounds"] = [dict(dialogue(), **{field: value})]
            with self.assertRaises(ValueError):
                self.send(payload)

    def test_reference_material_alone_cannot_prove_candidate_understanding(self):
        payload = self.final()
        payload["evidence_checks"] = [check("verified")]
        payload["grade"]["criteria"][0]["evidence_refs"] = ["check:c1"]
        with self.assertRaises(ValueError):
            self.send(payload)

    def test_v2_rubric_requires_observable_targets_and_matching_question_kind(self):
        for field in ("assessment_target", "acceptable_alternatives"):
            item = rubric()
            item.pop(field)
            with self.assertRaises(ValueError):
                bank.prepare(self.root, ROLE, DIRECTION,
                             {"rubrics": [{"question_id": self.ids[0], "rubric": item}]}, AS_OF)
        item = rubric()
        item["criteria"][0].pop("evidence_required")
        with self.assertRaises(ValueError):
            bank.validate_rubric(item, AS_OF)
        item = rubric()
        item["question_kind"] = "故障排查"
        with self.assertRaises(ValueError):
            bank.prepare(self.root, ROLE, DIRECTION,
                         {"rubrics": [{"question_id": self.ids[0], "rubric": item}]}, AS_OF)

    def test_fact_dispute_blocks_grading_until_matching_evidence_is_recorded(self):
        self.send(self.pending("pending_verification"))
        with self.assertRaises(ValueError):
            self.send(self.final())
        payload = self.final()
        payload.update({"evidence_checks": [check("verified")], "resolution": "已取得与范围匹配的资料"})
        payload["grade"]["criteria"][0]["evidence_refs"].append("check:c1")
        result = self.send(payload)
        self.assertEqual(result["feedback"]["score"], 10)
        saved = bank.load_session(self.root, "default", self.sid)["answers"][0]
        self.assertEqual(len(saved["evidence_events"]), 2)
        self.assertEqual(saved["evidence_checks"][0]["scope"], check()["scope"])

    def test_cannot_change_claim_or_scope_to_make_a_dispute_disappear(self):
        self.send(self.pending("pending_verification"))
        evidence = check("verified")
        evidence["scope"] = "另一个平台的另一个版本"
        payload = self.final()
        payload.update({"evidence_checks": [evidence], "resolution": "已核验"})
        with self.assertRaises(ValueError):
            self.send(payload)
        self.assertEqual(bank.load_session(self.root, "default", self.sid)["draft"]
                         ["evidence_checks"]["c1"]["status"], "unverified")

    def test_switching_pending_states_does_not_bypass_clarification(self):
        self.send(self.pending())
        self.send({"question_id": self.ids[0], "status": "pending_verification", "reason": "还需核验事实",
                   "evidence_checks": [check()]})
        payload = self.final()
        payload.update({"evidence_checks": [check("verified")], "resolution": "已核验事实但未记录澄清回答"})
        with self.assertRaises(ValueError):
            self.send(payload)

    def test_partial_assessment_is_not_zero_or_inflated_to_ten(self):
        payload = self.final()
        payload["grade"]["criteria"][1].update({"status": "not_assessed", "score": None,
                                                  "evidence_refs": [], "reason": "本题尚未验证该边界"})
        payload["grade"]["issues"] = []
        payload["grade"]["unverified"] = ["边界处理尚待实际验证"]
        result = self.send(payload)
        self.assertEqual(result["feedback"]["status"], "partial")
        self.assertIsNone(result["feedback"]["score"])
        self.assertEqual(result["feedback"]["assessment"]["earned_points"], 6)
        self.assertEqual(result["feedback"]["assessment"]["assessed_max_points"], 6)
        report = bank.summary(self.root, "default", self.sid)
        self.assertIsNone(report["average_score"])
        self.assertEqual(report["scored_questions"], 0)
        self.assertEqual(bank.select(self.root, ROLE, DIRECTION, AS_OF, review="weak")["available"], 0)

    def test_unsupported_deductions_and_fake_evidence_are_rejected(self):
        payload = self.final((5, 3))
        payload["grade"]["issues"] = []
        with self.assertRaises(ValueError):
            self.send(payload)
        payload = self.final()
        payload["grade"]["criteria"][0]["evidence_refs"] = ["round:missing"]
        with self.assertRaises(ValueError):
            self.send(payload)
        payload = self.final()
        payload["grade"]["criteria"][1].update(status="not_assessed", score=0, evidence_refs=[])
        with self.assertRaises(ValueError):
            self.send(payload)

    def test_invalid_question_is_excluded_from_average(self):
        self.sid = self.start(count=2)
        self.send({"question_id": self.ids[0], "answer": "控制级", "status": "invalid",
                   "reason": "题目对控制级的定义存在错误前提"})
        self.send(response(self.ids[1], (5, 3)))
        result = bank.summary(self.root, "default", self.sid)
        self.assertEqual(result["average_score"], 8)
        self.assertEqual(result["unscored_questions"], 1)
        self.assertIsNone(result["details"][0]["answer"]["score"])

    def test_skip_requires_user_request_and_is_not_a_zero_grade(self):
        payload = {"question_id": self.ids[0], "answer": "", "status": "skipped", "reason": "跳过"}
        with self.assertRaises(ValueError):
            self.send(payload)
        payload["user_requested"] = True
        self.send(payload)
        result = bank.summary(self.root, "default", self.sid)
        self.assertIsNone(result["average_score"])
        self.assertEqual(result["unscored_questions"], 1)

    def test_mock_resume_and_early_finish_keep_unresolved_answer_ungraded(self):
        self.sid = self.start(mode="mock")
        self.send(self.pending())
        progress = bank.public_progress(bank.load_session(self.root, "default", self.sid))
        self.assertEqual(progress["followup_prompt"], self.pending()["next_prompt"])
        active = bank.summary(self.root, "default", self.sid)
        self.assertNotIn("details", active)
        self.assertNotIn("average_score", active)
        ended = bank.summary(self.root, "default", self.sid, finish=True)
        self.assertIsNone(ended["average_score"])
        self.assertEqual(ended["pending_questions"], 1)
        self.assertEqual(ended["details"][0]["pending"]["answer"], "控制级")

    def test_legacy_rubric_is_readable_but_cannot_start_a_new_v2_session(self):
        old = rubric()
        old.pop("scoring_version")
        bank.prepare(self.root, ROLE, DIRECTION,
                     {"rubrics": [{"question_id": qid, "rubric": old} for qid in self.ids]}, AS_OF)
        with self.assertRaises(ValueError):
            bank.start(self.root, ROLE, DIRECTION, AS_OF, count=1)
        report = bank.catalog(self.root, AS_OF)["banks"][0]
        self.assertEqual(report["questions_prepared_legacy"], 3)
        self.assertEqual(report["questions_prepared"], 0)

    def test_legacy_score_is_labelled_and_not_rewritten_or_used_for_v2_weakness(self):
        path = bank.session_path(self.root, "default", self.sid)
        old = bank.read_json(path)
        old.pop("scoring_version")
        old.pop("draft")
        old["status"] = "completed"
        old["questions"][0]["rubric"].pop("scoring_version")
        old["answers"] = [{"question_id": self.ids[0], "answer": "控制级", "score": 2,
                           "hints_used": 0, "answered_at": "2026-10-26T12:00:00+00:00"}]
        bank.atomic_json(path, old)
        original = path.read_bytes()
        result = bank.summary(self.root, "default", self.sid)
        self.assertEqual(result["average_score"], 2)
        self.assertEqual(result["scoring_version"], 1)
        self.assertEqual(result["details"][0]["answer"]["scoring_version"], 1)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(bank.select(self.root, ROLE, DIRECTION, AS_OF, review="weak")["available"], 0)

    def test_legacy_active_session_can_finish_without_v2_payload(self):
        path = bank.session_path(self.root, "default", self.sid)
        old = bank.read_json(path)
        old.pop("scoring_version")
        old.pop("draft")
        old["questions"][0]["rubric"].pop("scoring_version")
        bank.atomic_json(path, old)
        payload = {"question_id": self.ids[0], "answer": "旧版回答", "grade": {
            "criteria": [{"id": "correctness", "score": 5, "reason": "旧版理由"},
                         {"id": "reasoning", "score": 3, "reason": "旧版理由"}]}}
        self.assertEqual(self.send(payload)["feedback"]["score"], 8)
        self.assertEqual(bank.summary(self.root, "default", self.sid)["scoring_version"], 1)

    def test_mixed_versions_are_reported_separately(self):
        self.sid = self.start(count=2)
        self.send(self.final())
        self.send(response(self.ids[1]))
        path = bank.session_path(self.root, "default", self.sid)
        session = bank.read_json(path)
        session["answers"][0]["scoring_version"] = 1
        bank.atomic_json(path, session)
        result = bank.summary(self.root, "default", self.sid)
        self.assertIsNone(result["average_score"])
        self.assertEqual(len(result["score_groups"]), 2)
        self.assertEqual(result["topic_scores"], [])

    def test_cli_pending_question_survives_resume(self):
        path = self.root / "pending.json"
        bank.atomic_json(path, self.pending())
        command = [sys.executable, str(SCRIPT), "--root", str(self.root), "--as-of", AS_OF.isoformat()]
        recorded = subprocess.run(command + ["answer", "--session", self.sid, "--input", str(path)],
                                  check=True, capture_output=True, encoding="utf-8")
        self.assertEqual(json.loads(recorded.stdout)["answered"], 0)
        resumed = subprocess.run(command + ["show", "--session", self.sid],
                                 check=True, capture_output=True, encoding="utf-8")
        self.assertEqual(json.loads(resumed.stdout)["current_question_state"], "pending_clarification")


if __name__ == "__main__":
    unittest.main()
