#!/usr/bin/env python3
"""Maintain evidence-backed interview banks and snapshot-based practice sessions."""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import tempfile
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid


VERSION = 1
SCORING_VERSION = 2
KINDS = {"基础问答", "算法编程", "场景设计", "故障排查", "项目追问", "行为面试"}
INTERNSHIP_TYPES = {"日常实习", "暑期实习", "实习", "转正面试"}
TRACKING = {"spm", "from", "share_token", "share_source", "sourcessr", "tocommentid"}
SITES = [
    ("牛客", "nowcoder.com"), ("掘金", "juejin.cn"),
    ("CSDN", "blog.csdn.net"), ("博客园", "cnblogs.com"),
    ("力扣讨论", "leetcode.cn/discuss"), ("知乎", "zhihu.com"),
    ("B站", "bilibili.com"), ("V2EX", "v2ex.com"),
    ("一亩三分地", "1point3acres.com"),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, name, limit=8000):
    require(isinstance(value, str) and bool(value.strip()), f"{name}必须为非空文本")
    require(len(value) <= limit, f"{name}超过{limit}字符")
    return value.strip()


def number(value, name):
    require(type(value) in (int, float) and math.isfinite(value), f"{name}必须是有限数字")
    return value


def string_list(value, name, nonempty=False):
    require(isinstance(value, list), f"{name}必须为数组")
    if nonempty:
        require(bool(value), f"{name}不能为空")
    return list(dict.fromkeys(text(item, name, 1000) for item in value))


def day(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
            "日期必须为YYYY-MM-DD，不可用月份或更新时间代替")
    return date.fromisoformat(value)


def today():
    return datetime.now(timezone(timedelta(hours=8))).date()


def window(as_of):
    return {"start": (as_of - timedelta(days=89)).isoformat(),
            "end": as_of.isoformat(), "days": 90, "inclusive": True}


def recent(value, as_of):
    return as_of - timedelta(days=89) <= day(value) <= as_of


def label(value):
    value = unicodedata.normalize("NFKC", text(value, "目录名称", 80))
    require(not re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            and not value.endswith((".", " ")) and not value.startswith(".")
            and value.split(".")[0].upper() not in
            {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}, "目录名称包含非法路径或保留名称")
    return value


def url(value):
    parts = urlsplit(text(value, "URL", 4000))
    require(parts.scheme in {"http", "https"} and parts.hostname
            and not parts.username and not parts.password, "仅接受不含凭据的HTTP/HTTPS URL")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def normalized(value):
    value = unicodedata.normalize("NFKC", text(value, "题目", 3000))
    # Preserve operators such as C++, C#, equality, and mathematical constraints.
    return re.sub(r"\s+", "", value).rstrip("。？?")


def identifier(prefix, value):
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                          parse_constant=lambda value: (_ for _ in ()).throw(
                              ValueError(f"非法JSON数字: {value}")))
    except (OSError, ValueError) as exc:
        raise ValueError(f"无法读取JSON {path}: {exc}") from exc


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(root):
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".write.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("数据目录正在写入；若上次异常退出，确认无其他进程后再移除锁文件") from exc
    try:
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def bank_path(root, role, direction):
    return root / "banks" / label(role) / (label(direction) + ".json")


def load_bank(root, role, direction, create=False):
    path = bank_path(root, role, direction)
    if not path.exists():
        require(create, "对应岗位题库不存在，请先更新题库")
        return {"schema_version": VERSION, "role": label(role), "direction": label(direction),
                "updated_at": None, "sources": {}, "questions": {}}
    bank = read_json(path)
    validate_bank(bank)
    require(bank["role"] == label(role) and bank["direction"] == label(direction), "题库路径与岗位不一致")
    return bank


def validate_rubric(rubric, as_of):
    require(isinstance(rubric, dict), "评分表必须为对象")
    version = rubric.get("scoring_version", 1)
    require(type(version) is int and version in {1, SCORING_VERSION}, "不支持的评分规则版本")
    if version == SCORING_VERSION:
        text(rubric.get("assessment_target"), "本题考察目标", 2000)
        require(rubric.get("question_kind") in KINDS, "评分表须声明题型")
        string_list(rubric.get("acceptable_alternatives"), "可接受的替代解法")
        string_list(rubric.get("assumptions", []), "题目假设")
        string_list(rubric.get("nonessential", []), "非必答扩展")
    require(day(rubric.get("prepared_at")) <= as_of, "评分表核对日期不能在未来")
    text(rubric.get("reference_answer"), "参考答案")
    criteria = rubric.get("criteria")
    require(isinstance(criteria, list) and bool(criteria), "评分维度不能为空")
    seen, total = set(), 0
    for criterion in criteria:
        require(isinstance(criterion, dict), "评分维度必须为对象")
        key = text(criterion.get("id"), "评分维度ID", 80)
        require(key not in seen, "评分维度ID重复")
        seen.add(key)
        text(criterion.get("label"), "评分维度名称", 200)
        maximum = number(criterion.get("max_points"), "维度满分")
        require(0 < maximum <= 10, "维度满分须大于0且不超过10")
        total += maximum
        string_list(criterion.get("expected"), "期望要点", nonempty=True)
        if version == SCORING_VERSION:
            string_list(criterion.get("evidence_required"), "可观察的评分证据", nonempty=True)
            string_list(criterion.get("critical_errors", []), "关键技术错误")
    require(math.isclose(total, 10), "评分表总分必须为10")
    refs = rubric.get("references")
    require(isinstance(refs, list) and bool(refs), "评分表需要技术参考资料")
    for ref in refs:
        require(isinstance(ref, dict), "参考资料必须为对象")
        url(ref.get("url"))
        text(ref.get("title"), "参考资料标题", 300)
        require(day(ref.get("checked_at")) <= day(rubric["prepared_at"]),
                "参考资料核对日期不能晚于评分表准备日期")
    string_list(rubric.get("common_mistakes", []), "常见错误")


def validate_bank(bank):
    require(isinstance(bank, dict) and bank.get("schema_version") == VERSION, "不支持的题库版本")
    label(bank.get("role"))
    label(bank.get("direction"))
    require(isinstance(bank.get("sources"), dict) and isinstance(bank.get("questions"), dict),
            "题库sources/questions必须为对象")
    for sid, source in bank["sources"].items():
        require(source.get("id") == sid and sid == identifier("s_", url(source.get("url"))),
                "来源ID或URL损坏")
        day(source.get("published_at"))
        if source.get("interview_at") is not None:
            day(source["interview_at"])
    for qid, question in bank["questions"].items():
        require(question.get("id") == qid, "题目ID损坏")
        text(question.get("text"), "题目", 3000)
        require(question.get("kind") in KINDS, "题型无效")
        string_list(question.get("tags"), "知识点标签", nonempty=True)
        require(bool(question.get("occurrences")), "题目缺少来源")
        for occurrence in question["occurrences"]:
            require(occurrence.get("source_id") in bank["sources"], "题目引用不存在的来源")
            text(occurrence.get("original_text"), "原始问法", 3000)


class CandidateError(ValueError):
    def __init__(self, status, reason):
        self.status = status
        super().__init__(reason)


def check_candidate(source, as_of):
    require(isinstance(source, dict), "来源条目必须为对象")
    source = copy.deepcopy(source)
    source["url"] = url(source.get("url"))
    if source.get("access_status") not in {"full", "user_provided_full"}:
        raise CandidateError("pending", "未读取完整正文：" + str(source.get("skip_reason", "访问受限或仅有摘要")))
    for key, reason in [("personal_account", "无法确认个人参与面试"),
                        ("is_original", "不是个人原帖或存在转载")]:
        if source.get(key) is not True:
            raise CandidateError("excluded" if source.get(key) is False else "pending", reason)
    if source.get("internship_type") not in INTERNSHIP_TYPES:
        raise CandidateError("excluded", "未确认属于实习岗位或实习转正面试")
    verify = source.get("verification")
    require(isinstance(verify, dict), "缺少原帖核验依据")
    if verify.get("publication_kind") != "first_published":
        raise CandidateError("pending", "不能用修改、抓取或搜索日期代替首次发布日期")
    text(verify.get("personal_excerpt"), "个人参与面试证据", 320)
    text(verify.get("publication_excerpt"), "首次发布日期证据", 320)
    text(verify.get("internship_excerpt"), "实习身份依据", 320)
    require(verify.get("method") in {"web", "browser", "user_provided"}, "核验方式无效")
    require((source["access_status"] == "user_provided_full") == (verify["method"] == "user_provided"),
            "用户提供正文的核验方式不一致")
    published = day(source.get("published_at"))
    if not recent(source["published_at"], as_of):
        raise CandidateError("excluded", "首次发布日期不在最近90天内或处于未来")
    require(published <= day(verify.get("verified_at")) <= as_of, "核验日期无效")
    if source.get("interview_at") is not None:
        if not recent(source["interview_at"], as_of):
            raise CandidateError("excluded", "实际面试日期不在最近90天内或处于未来")
        require(day(source["interview_at"]) <= day(verify["verified_at"]), "面试时间不能晚于核验日期")
    for key in ("title", "platform", "author", "role"):
        text(source.get(key), key, 500)
    for key in ("company", "round", "department"):
        if source.get(key) is not None:
            text(source[key], key, 500)
    source["experience_key"] = text(source.get("experience_key") or source["url"], "面试经历标识", 4000)
    questions = source.get("questions")
    require(isinstance(questions, list) and bool(questions), "没有可提取的具体问题")
    for question in questions:
        require(isinstance(question, dict), "问题必须为对象")
        text(question.get("text"), "原始题目", 3000)
        text(question.get("canonical_text", question["text"]), "整理后的题目", 3000)
        require(question.get("kind") in KINDS, "题型必须为规定值")
        require(question.get("difficulty") in {"基础", "中等", "深入", "未评估"}, "难度值无效")
        string_list(question.get("tags"), "知识点标签", nonempty=True)
        string_list(question.get("followups", []), "原帖追问")
        if question.get("round_original") is not None:
            text(question["round_original"], "原题所属轮次", 200)
    return source


def active_occurrences(bank, question, as_of, company=None):
    result = []
    for occurrence in question["occurrences"]:
        source = bank["sources"][occurrence["source_id"]]
        if (recent(source["published_at"], as_of)
                and (source.get("interview_at") is None or recent(source["interview_at"], as_of))
                and (not company or company.casefold() in (source.get("company") or "").casefold())):
            result.append((occurrence, source))
    return result


def stats(bank, as_of):
    active = [q for q in bank["questions"].values() if active_occurrences(bank, q, as_of)]
    source_ids = {o["source_id"] for q in active for o, _ in active_occurrences(bank, q, as_of)}
    return {"questions_total": len(bank["questions"]), "questions_active": len(active),
            "sources_active": len(source_ids),
            "experiences_active": len({bank["sources"][sid]["experience_key"] for sid in source_ids}),
            "sources_without_interview_date": sum(bank["sources"][sid].get("interview_at") is None
                                                   for sid in source_ids),
            "questions_prepared": sum(bool(q.get("rubric")) and
                                      q["rubric"].get("scoring_version", 1) == SCORING_VERSION for q in active),
            "questions_prepared_legacy": sum(bool(q.get("rubric")) and
                                             q["rubric"].get("scoring_version", 1) == 1 for q in active)}


def ingest(root, role, direction, batch, as_of):
    require(isinstance(batch, dict) and isinstance(batch.get("sources"), list), "批次必须有sources数组")
    require(isinstance(batch.get("searches", []), list), "searches必须为数组")
    with locked(root):
        bank = load_bank(root, role, direction, create=True)
        report_id = as_of.isoformat() + "-" + uuid.uuid4().hex[:12]
        report = {"schema_version": VERSION, "id": report_id, "role": bank["role"],
                  "direction": bank["direction"], "window": window(as_of),
                  "searches": batch.get("searches", []), "decisions": [], "new_questions": 0,
                  "new_occurrences": 0, "merged_occurrences": 0}
        for raw in batch["sources"]:
            raw_url = raw.get("url") if isinstance(raw, dict) else None
            try:
                source = check_candidate(raw, as_of)
                require(label(source["role"]) == bank["role"], "来源岗位与目标题库不匹配")
                sid = identifier("s_", source["url"])
                # Stage each source so one invalid merge cannot leave orphan questions.
                staged = copy.deepcopy(bank["questions"])
                new_questions = new_occurrences = merged = 0
                for item in source.pop("questions"):
                    canonical = item.get("canonical_text", item["text"]).strip()
                    qid = item.get("merge_into") or identifier("q_", normalized(canonical))
                    if item.get("merge_into"):
                        require(qid in staged, "merge_into引用不存在的题目")
                        require(staged[qid]["kind"] == item["kind"], "不能归并不同题型")
                    if qid not in staged:
                        staged[qid] = {"id": qid, "text": canonical, "kind": item["kind"],
                                       "difficulty": item["difficulty"], "tags": [],
                                       "occurrences": [], "rubric": None}
                        new_questions += 1
                    question = staged[qid]
                    require(question["kind"] == item["kind"], "相同问法的题型冲突，请核对后再归并")
                    question["tags"] = sorted(set(question["tags"]) | set(item["tags"]))
                    occurrence = {"source_id": sid, "original_text": item["text"].strip(),
                                  "round": item.get("round_original", source.get("round")),
                                  "followups": item.get("followups", [])}
                    existing = next((o for o in question["occurrences"]
                                     if o["source_id"] == sid
                                     and normalized(o["original_text"]) == normalized(item["text"])), None)
                    if existing is None:
                        question["occurrences"].append(occurrence)
                        new_occurrences += 1
                        if qid in bank["questions"]:
                            merged += 1
                    else:
                        existing["followups"] = list(dict.fromkeys(existing["followups"] + occurrence["followups"]))
                source["id"] = sid
                bank["sources"][sid] = source
                bank["questions"] = staged
                for key, value in [("new_questions", new_questions), ("new_occurrences", new_occurrences),
                                   ("merged_occurrences", merged)]:
                    report[key] += value
                report["decisions"].append({"url": source["url"], "status": "accepted", "source_id": sid})
            except (ValueError, TypeError, KeyError) as exc:
                report["decisions"].append({"url": raw_url, "status": getattr(exc, "status", "pending"),
                                             "reason": str(exc)})
        report["counts"] = {status: sum(d["status"] == status for d in report["decisions"])
                            for status in ("accepted", "pending", "excluded")}
        report["counts"]["candidates"] = len(batch["sources"])
        report["stats"] = stats(bank, as_of)
        report_path = root / "reports" / (report_id + ".json")
        report["report_path"] = str(report_path)
        path = bank_path(root, role, direction)
        if report["counts"]["accepted"]:
            bank["updated_at"] = as_of.isoformat()
            validate_bank(bank)
            atomic_json(path, bank)
        report["bank_path"] = str(path) if path.exists() else None
        atomic_json(report_path, report)
        return report


def catalog(root, as_of):
    banks = []
    for path in sorted((root / "banks").glob("*/*.json")):
        bank = read_json(path)
        validate_bank(bank)
        banks.append({"role": bank["role"], "direction": bank["direction"], "path": str(path),
                      "updated_at": bank["updated_at"], **stats(bank, as_of)})
    return {"root": str(root), "window": window(as_of), "banks": banks}


def prepare(root, role, direction, payload, as_of):
    require(isinstance(payload, dict) and isinstance(payload.get("rubrics"), list), "需要rubrics数组")
    with locked(root):
        bank = load_bank(root, role, direction)
        seen = set()
        for item in payload["rubrics"]:
            qid = item.get("question_id")
            require(qid in bank["questions"] and qid not in seen, "题目ID不存在或重复")
            seen.add(qid)
            validate_rubric(item.get("rubric"), as_of)
            if item["rubric"].get("scoring_version", 1) == SCORING_VERSION:
                require(item["rubric"]["question_kind"] == bank["questions"][qid]["kind"],
                        "评分表题型与原题不一致")
            bank["questions"][qid]["rubric"] = copy.deepcopy(item["rubric"])
        atomic_json(bank_path(root, role, direction), bank)
    return {"prepared": len(seen), "question_ids": sorted(seen)}


def session_path(root, profile, session_id):
    require(isinstance(session_id, str) and re.fullmatch(r"[a-f0-9]{32}", session_id), "会话ID无效")
    return root / "profiles" / label(profile) / "sessions" / (session_id + ".json")


def history(root, profile, role, direction):
    result = {}
    for path in sorted((root / "profiles" / label(profile) / "sessions").glob("*.json")):
        session = read_json(path)
        require(session.get("schema_version") == VERSION, "不支持的会话版本")
        if session["role"] == role and session["direction"] == direction:
            for answer in session["answers"]:
                if answer.get("score") is None or answer.get("status", "scored") != "scored":
                    continue
                qid = answer["question_id"]
                timestamp = (answer["answered_at"], session["id"])
                if qid not in result or timestamp > result[qid]["timestamp"]:
                    result[qid] = {"timestamp": timestamp, "score": answer["score"],
                                   "hints_used": answer["hints_used"],
                                   "scoring_version": answer.get("scoring_version", session.get("scoring_version", 1))}
    return result


def select(root, role, direction, as_of, count=5, company=None, topics=None,
           profile="default", review="all", ready=False, seed=None, question_ids=None):
    require(type(count) is int and 1 <= count <= 100, "题量须为1至100")
    bank = load_bank(root, role, direction)
    previous = history(root, profile, bank["role"], bank["direction"])
    candidates = []
    rng = random.Random(seed)
    for qid, question in bank["questions"].items():
        if question_ids is not None and qid not in question_ids:
            continue
        occurrences = active_occurrences(bank, question, as_of, company)
        if not occurrences or (ready and (not question.get("rubric") or
                                          question["rubric"].get("scoring_version", 1) != SCORING_VERSION)):
            continue
        if topics and not set(topics).intersection(question["tags"]):
            continue
        if review == "unseen" and qid in previous:
            continue
        if review == "weak" and (qid not in previous or
                                  previous[qid]["scoring_version"] != SCORING_VERSION or
                                  (previous[qid]["score"] >= 7 and not previous[qid]["hints_used"])):
            continue
        item = copy.deepcopy(question)
        item["occurrences"] = [o for o, _ in occurrences]
        item["sources"] = {s["id"]: s for _, s in occurrences}
        item["experience_count"] = len({s["experience_key"] for _, s in occurrences})
        known = [s["interview_at"] for _, s in occurrences if s.get("interview_at")]
        latest = max(s.get("interview_at") or s["published_at"] for _, s in occurrences)
        item["_rank"] = (qid not in previous, bool(known), latest, item["experience_count"], rng.random())
        candidates.append(item)
    available = len(candidates)
    chosen, covered = [], set()
    while candidates and len(chosen) < count:
        # Add topic coverage without sacrificing the exact role and source filters.
        best = max(candidates, key=lambda q: (bool(set(q["tags"]) - covered), q["_rank"]))
        candidates.remove(best)
        covered.update(best["tags"])
        best.pop("_rank")
        chosen.append(best)
    return {"window": window(as_of), "role": bank["role"], "direction": bank["direction"],
            "requested": count, "available": available, "selected": len(chosen), "questions": chosen}


def public_progress(session):
    index = len(session["answers"])
    current = session["questions"][index] if index < len(session["questions"]) and session["status"] == "active" else None
    result = {"session_id": session["id"], "mode": session["mode"], "status": session["status"],
            "scoring_version": session.get("scoring_version", 1),
            "answered": index, "total": len(session["questions"]),
            "next_question": {"id": current["id"], "text": current["text"],
                              "kind": current["kind"]} if current else None}
    draft = session.get("draft")
    if current and draft:
        result["current_question_state"] = draft["status"]
        result["followup_prompt"] = draft.get("next_prompt")
        result["current_answer"] = draft["answer"]
        result["dialogue"] = [{k: r[k] for k in ("id", "kind", "question", "answer", "origin")}
                              for r in draft["rounds"]]
    return result


def start(root, role, direction, as_of, count=5, mode="practice", profile="default",
          company=None, topics=None, review="all", seed=None, question_ids=None):
    require(mode in {"practice", "mock"}, "面试模式无效")
    with locked(root):
        selection = select(root, role, direction, as_of, count=len(question_ids) if question_ids else count,
                           company=company, topics=topics, profile=profile, review=review,
                           ready=True, seed=seed, question_ids=question_ids)
        if question_ids:
            require(len(question_ids) == len(set(question_ids)), "所选题目ID重复")
            by_id = {q["id"]: q for q in selection["questions"]}
            require(all(qid in by_id for qid in question_ids), "所选题目已过期、不匹配过滤条件或尚未准备v2评分表")
            questions = [by_id[qid] for qid in question_ids]
        else:
            require(selection["selected"] == count,
                    f"有效且已准备v2评分表的题量不足：需要{count}，可用{selection['available']}。旧评分表需重新prepare，或减少题量、补采")
            questions = selection["questions"]
        require(bool(questions), "不能开始空面试")
        for question in questions:
            validate_rubric(question["rubric"], as_of)
        session = {"schema_version": VERSION, "id": uuid.uuid4().hex, "profile": label(profile),
                   "scoring_version": SCORING_VERSION, "draft": None,
                   "role": selection["role"], "direction": selection["direction"], "mode": mode,
                   "started_on": as_of.isoformat(), "created_at": datetime.now(timezone.utc).isoformat(),
                   "window": window(as_of), "status": "active",
                   "questions": questions, "answers": []}
        path = session_path(root, profile, session["id"])
        atomic_json(path, session)
    return {**public_progress(session), "session_path": str(path)}


def load_session(root, profile, session_id):
    session = read_json(session_path(root, profile, session_id))
    require(session.get("schema_version") == VERSION and session.get("id") == session_id
            and session.get("profile") == label(profile), "会话身份或版本不匹配")
    require(session.get("scoring_version", 1) in {1, SCORING_VERSION}, "不支持的会话评分版本")
    return session


def sessions(root, profile="default"):
    items = []
    for path in (root / "profiles" / label(profile) / "sessions").glob("*.json"):
        session = load_session(root, profile, path.stem)
        items.append({**public_progress(session), "role": session["role"],
                      "direction": session["direction"], "started_on": session["started_on"],
                      "created_at": session.get("created_at", session["started_on"])})
    return {"profile": label(profile), "sessions": sorted(items, key=lambda s: s["created_at"], reverse=True)}


def validate_grade(grade, rubric):
    require(isinstance(grade, dict), "grade必须为对象")
    require(isinstance(grade.get("criteria"), list), "评分需要criteria数组")
    expected = {c["id"]: c for c in rubric["criteria"]}
    seen, total = set(), 0
    for item in grade["criteria"]:
        key = item.get("id")
        require(key in expected and key not in seen, "评分维度未知或重复")
        seen.add(key)
        value = number(item.get("score"), "得分")
        require(0 <= value <= expected[key]["max_points"], "评分超出该维度范围")
        text(item.get("reason"), "评分理由", 2000)
        total += value
    require(seen == set(expected), "评分维度不完整")
    string_list(grade.get("strengths", []), "回答优点")
    string_list(grade.get("gaps", []), "关键遗漏")
    return round(total, 4)


def merge_rounds(draft, incoming, question):
    require(isinstance(incoming, list), "rounds必须为数组")
    existing = {item["id"]: item for item in draft["rounds"]}
    source_prompts = {prompt for occurrence in question["occurrences"]
                      for prompt in occurrence["followups"]}
    for item in incoming:
        require(isinstance(item, dict), "每轮对话必须为对象")
        require(set(item).issubset({"id", "kind", "question", "answer", "origin"}),
                "对话轮次只保存问答与类型；评分在本题结束时统一提交")
        key = text(item.get("id"), "对话轮次ID", 80)
        require(item.get("kind") in {"clarification", "followup", "hint"},
                "对话须区分clarification、followup、hint")
        text(item.get("question"), "追问或提示", 3000)
        text(item.get("answer"), "本轮使用者回答", 16000)
        require(item.get("origin") in {"source", "generated"}, "追问须标注来源类型")
        if item["origin"] == "source":
            require(item["question"] in source_prompts, "原帖追问必须能在来源记录中找到")
        if key in existing:
            require(existing[key] == item, "已记录的对话不可覆盖，请使用新的轮次ID")
            continue
        draft["rounds"].append(copy.deepcopy(item))
        existing[key] = item


def merge_evidence(draft, incoming, as_of):
    require(isinstance(incoming, list), "evidence_checks必须为数组")
    for item in incoming:
        require(isinstance(item, dict), "核验记录必须为对象")
        key = text(item.get("id"), "核验ID", 80)
        text(item.get("claim"), "待核验的具体主张", 2000)
        text(item.get("scope"), "核验适用范围和版本", 2000)
        text(item.get("reason"), "核验理由", 2000)
        require(day(item.get("checked_at")) <= as_of, "核验日期不能在未来")
        require(item.get("status") in {"unverified", "verified", "refuted"}, "核验状态无效")
        if item["status"] != "unverified":
            url(item.get("source_url"))
            text(item.get("excerpt"), "与主张匹配的短证据", 320)
        previous = draft["evidence_checks"].get(key)
        if previous:
            require(previous["claim"] == item["claim"] and previous["scope"] == item["scope"],
                    "同一核验ID不能更换主张或适用范围，请新增核验ID")
        if previous != item:
            draft["evidence_events"].append(copy.deepcopy(item))
            draft["evidence_checks"][key] = copy.deepcopy(item)


def validate_grade_v2(grade, rubric, draft):
    require(isinstance(grade, dict), "grade必须为对象")
    require(isinstance(grade.get("criteria"), list), "评分需要criteria数组")
    refs = {"initial"} if draft["answer"].strip() else set()
    refs.update("round:" + item["id"] for item in draft["rounds"])
    refs.update("check:" + key for key, item in draft["evidence_checks"].items()
                if item["status"] != "unverified")

    def evidence(value):
        values = string_list(value, "回答证据引用", nonempty=True)
        require(set(values).issubset(refs), "评分引用了不存在或尚未核验的证据")
        require(any(ref == "initial" or ref.startswith("round:") for ref in values),
                "评价使用者的表现须引用其回答，不能只引用外部资料")

    expected = {criterion["id"]: criterion for criterion in rubric["criteria"]}
    seen, earned, assessed_max, missing = set(), 0, 0, []
    deductions = False
    for item in grade["criteria"]:
        require(isinstance(item, dict), "评分维度必须为对象")
        key = item.get("id")
        require(key in expected and key not in seen, "评分维度未知或重复")
        seen.add(key)
        text(item.get("reason"), "评分理由", 2000)
        require(item.get("status") in {"assessed", "not_assessed"}, "维度须标注是否已评价")
        if item["status"] == "not_assessed":
            require(item.get("score") is None, "未评价的维度必须留空，不能记零分")
            require(not item.get("evidence_refs"), "未评价的维度不能伪造已评价证据")
            missing.append(key)
            continue
        maximum = expected[key]["max_points"]
        value = number(item.get("score"), "得分")
        require(0 <= value <= maximum, "评分超出该维度范围")
        evidence(item.get("evidence_refs"))
        deductions = deductions or value < maximum
        earned += value
        assessed_max += maximum
    require(seen == set(expected), "评分维度不完整")
    for field in ("confirmed", "issues"):
        items = grade.get(field)
        require(isinstance(items, list), f"{field}必须为数组")
        for item in items:
            require(isinstance(item, dict), "评价结论须附证据")
            text(item.get("claim"), "评价结论", 2000)
            evidence(item.get("evidence_refs"))
    require(not deductions or bool(grade["issues"]), "扣分须写明有证据支持的具体问题")
    unknown = string_list(grade.get("unverified"), "尚待验证的能力")
    require(not missing or bool(unknown), "存在未评价维度时须说明尚待验证的内容")
    return {"score": round(earned, 4) if not missing else None,
            "earned_points": round(earned, 4), "assessed_max_points": round(assessed_max, 4),
            "unassessed_criteria": missing, "complete": not missing}


def answer_v2(root, profile, session_id, session, question, payload, as_of):
    status = payload.get("status")
    pending = {"pending_clarification", "pending_verification", "ready_to_score"}
    require(status in pending | {"scored", "skipped", "invalid"}, "请声明本题状态，再决定是否评分")
    require(not payload.get("followups"), "v2使用rounds区分澄清、追问与提示")
    require(payload.get("scoring_version", SCORING_VERSION) == SCORING_VERSION, "不能混用评分版本")
    draft = copy.deepcopy(session.get("draft"))
    if draft is None:
        require(isinstance(payload.get("answer"), str), "首次记录须保存使用者的原始回答")
        draft = {"question_id": question["id"], "answer": payload["answer"], "rounds": [],
                 "evidence_checks": {}, "evidence_events": [], "resolutions": [],
                 "clarification_pending": False, "clarification_since": 0}
    else:
        require(draft["question_id"] == question["id"], "草稿题目与当前题目不一致")
        require("answer" not in payload or payload["answer"] == draft["answer"],
                "原始回答不可覆盖；请将补充回答追加为rounds")
    merge_rounds(draft, payload.get("rounds", []), question)
    merge_evidence(draft, payload.get("evidence_checks", []), as_of)
    if draft["clarification_pending"] and payload.get("resolution"):
        clarification = [item["id"] for item in draft["rounds"][draft["clarification_since"]:]
                         if item["kind"] == "clarification"]
        require(bool(clarification), "须记录针对歧义的澄清回答，不能只改状态")
        draft["clarification_pending"] = False
        draft["resolutions"].append({"reason": text(payload["resolution"], "澄清结论", 2000),
                                      "round_ids": clarification})
    unresolved = [item for item in draft["evidence_checks"].values() if item["status"] == "unverified"]
    hints = sum(item["kind"] == "hint" for item in draft["rounds"])
    if "hints_used" in payload:
        require(type(payload["hints_used"]) is int and payload["hints_used"] == hints,
                "提示次数由hint轮次计算；澄清与普通追问不能计作提示")
    if status in {"ready_to_score", "scored"}:
        require(not draft["clarification_pending"], "歧义尚未澄清，不能评分")
        require(not unresolved, "事实争议尚未核验，不能评分")
        if (session.get("draft") or {}).get("status") == "pending_verification":
            conclusion = text(payload.get("resolution"), "事实核验结论", 2000)
            draft["resolutions"].append({"reason": conclusion,
                                          "check_ids": sorted(draft["evidence_checks"])})
        require(draft["answer"].strip() or bool(draft["rounds"]), "尚未作答，不能评分")
    if status in pending:
        require(not any(key in payload for key in ("grade", "score", "total")), "待处理状态不得提前保存分数")
        draft["reason"] = text(payload.get("reason"), "本题状态原因", 2000)
        if status == "pending_clarification":
            draft["next_prompt"] = text(payload.get("next_prompt"), "中性的澄清问题", 3000)
            draft["clarification_pending"] = True
            draft["clarification_since"] = len(draft["rounds"])
        elif status == "pending_verification":
            require(bool(unresolved), "待核验状态须记录具体的未核验主张")
            draft["next_prompt"] = payload.get("next_prompt")
        else:
            draft["next_prompt"] = None
        draft["status"] = status
        draft["hints_used"] = hints
        session["draft"] = draft
        atomic_json(session_path(root, profile, session_id), session)
        return public_progress(session)

    record = {"question_id": question["id"], "answer": draft["answer"], "rounds": draft["rounds"],
              "evidence_checks": list(draft["evidence_checks"].values()),
              "evidence_events": draft["evidence_events"], "resolutions": draft["resolutions"],
              "scoring_version": SCORING_VERSION, "status": status, "hints_used": hints,
              "clarifications_used": sum(item["kind"] == "clarification" for item in draft["rounds"]),
              "answered_on": as_of.isoformat(), "answered_at": datetime.now(timezone.utc).isoformat(),
              "score": None}
    if status == "scored":
        readiness = payload.get("readiness")
        require(isinstance(readiness, dict) and readiness.get("meaning_clear") is True
                and readiness.get("facts_checked") is True, "评分前须确认语义已清楚且相关事实已有依据")
        text(readiness.get("reason"), "评分准备依据", 2000)
        assessment = validate_grade_v2(payload.get("grade"), question["rubric"], draft)
        record.update({"grade": copy.deepcopy(payload["grade"]), "readiness": copy.deepcopy(readiness),
                       "assessment": assessment, "score": assessment["score"]})
        if not assessment["complete"]:
            record["status"] = "partial"
    else:
        require(not any(key in payload for key in ("grade", "score", "total")), "跳过或无效题不得附带分数")
        record["reason"] = text(payload.get("reason"), "不计分原因", 2000)
        if status == "skipped":
            require(payload.get("user_requested") is True, "跳过须由使用者明确提出")
    session["answers"].append(record)
    session["draft"] = None
    if len(session["answers"]) == len(session["questions"]):
        session["status"] = "completed"
    atomic_json(session_path(root, profile, session_id), session)
    result = public_progress(session)
    if session["mode"] == "practice":
        result["feedback"] = {"score": record["score"], "status": record["status"],
                              "scoring_version": SCORING_VERSION, "hints_used": hints,
                              "clarifications_used": record["clarifications_used"],
                              "grade": record.get("grade"), "assessment": record.get("assessment"),
                              "reason": record.get("reason"), "sources": question["sources"]}
        if status == "scored":
            result["feedback"]["rubric"] = question["rubric"]
    return result


def answer(root, profile, session_id, payload, as_of):
    require(isinstance(payload, dict), "回答记录必须为对象")
    with locked(root):
        session = load_session(root, profile, session_id)
        require(session["status"] == "active", "会话已结束，不能追加或覆盖回答")
        require(day(session["started_on"]) <= as_of, "回答日期不能早于开始日期")
        question = session["questions"][len(session["answers"])]
        require(payload.get("question_id") == question["id"], "请按当前题目顺序记录，不能覆盖已答题")
        if session.get("scoring_version", 1) == SCORING_VERSION:
            return answer_v2(root, profile, session_id, session, question, payload, as_of)
        raw_answer = payload.get("answer")
        require(isinstance(raw_answer, str), "answer必须为原始回答文本")
        score = validate_grade(payload.get("grade"), question["rubric"])
        if not raw_answer.strip():
            require(payload.get("skipped") is True and score == 0, "空回答仅用于使用者明确跳过，且须为零分")
        hints = payload.get("hints_used", 0)
        require(type(hints) is int and hints >= 0, "提示次数必须为非负整数")
        followups = payload.get("followups", [])
        require(isinstance(followups, list), "followups必须为数组")
        for item in followups:
            text(item.get("question"), "追问", 3000)
            text(item.get("answer"), "追问回答")
            require(item.get("origin") in {"source", "generated"}, "追问须标注source或generated")
            if item["origin"] == "source":
                original = {f for o in question["occurrences"] for f in o["followups"]}
                require(item["question"] in original, "原帖追问必须能在来源记录中找到")
        record = copy.deepcopy(payload)
        record.update({"score": score, "scoring_version": 1, "hints_used": hints, "answered_on": as_of.isoformat(),
                       "answered_at": datetime.now(timezone.utc).isoformat()})
        session["answers"].append(record)
        if len(session["answers"]) == len(session["questions"]):
            session["status"] = "completed"
        atomic_json(session_path(root, profile, session_id), session)
    result = public_progress(session)
    if session["mode"] == "practice":
        result["feedback"] = {"score": score, "grade": payload["grade"],
                              "hints_used": hints, "rubric": question["rubric"],
                              "sources": question["sources"]}
    return result


def summary(root, profile, session_id, finish=False):
    if finish:
        with locked(root):
            session = load_session(root, profile, session_id)
            if session["status"] == "active":
                session["status"] = "finished_early"
                atomic_json(session_path(root, profile, session_id), session)
    else:
        session = load_session(root, profile, session_id)
    result = public_progress(session)
    if session["mode"] == "mock" and session["status"] == "active":
        result["message"] = "模拟面试尚未结束；使用者明确要求结束后可用--finish查看复盘"
        return result
    answers = {a["question_id"]: a for a in session["answers"]}
    topics, details, groups = {}, [], {}
    for question in session["questions"]:
        record = answers.get(question["id"])
        if record and record.get("score") is not None:
            version = record.get("scoring_version", session.get("scoring_version", 1))
            groups.setdefault(version, []).append(record["score"])
            for tag in question["tags"]:
                topics.setdefault(tag, []).append(record["score"])
        display_record = copy.deepcopy(record)
        if display_record:
            display_record.setdefault("scoring_version", session.get("scoring_version", 1))
        details.append({"question_id": question["id"], "text": question["text"],
                        "answer": display_record, "rubric": question["rubric"], "sources": question["sources"],
                        "pending": session.get("draft") if session.get("draft", {}) and
                        session["draft"]["question_id"] == question["id"] else None})
    scores = [a["score"] for a in session["answers"] if a.get("score") is not None]
    mixed = len(groups) > 1
    result.update({"average_score": round(sum(scores) / len(scores), 2) if scores and not mixed else None,
                   "score_scope": "本次题目中的面试表现，不能直接代表整体开发能力",
                   "scoring_label": "证据与追问评分v2" if session.get("scoring_version", 1) == 2 else "旧版要点评分v1",
                   "score_groups": [{"scoring_version": version, "questions": len(values),
                                     "average_score": round(sum(values) / len(values), 2)}
                                    for version, values in sorted(groups.items())],
                   "scored_questions": len(scores),
                   "unscored_questions": len(session["answers"]) - len(scores),
                   "pending_questions": int(bool(session.get("draft"))),
                   "hinted_answers": sum(bool(a["hints_used"]) for a in session["answers"]),
                   "clarified_answers": sum(bool(a.get("clarifications_used")) for a in session["answers"]),
                   "topic_scores": sorted([{"topic": tag, "average": round(sum(values) / len(values), 2),
                                            "answered": len(values)} for tag, values in topics.items()],
                                           key=lambda row: (row["average"], row["topic"])) if not mixed else [],
                   "details": details})
    return result


def plan(role, direction, as_of, company=None):
    start_date = day(window(as_of)["start"])
    months = sorted({(start_date + timedelta(days=i)).strftime("%Y-%m") for i in range(90)})
    queries = [{"platform": name,
                "query": f"site:{domain} {company or ''} {role} {direction} 实习 面经 {month}".strip()}
               for name, domain in SITES for month in months]
    return {"window": window(as_of), "role": role, "direction": direction, "queries": queries,
            "additional_terms": ["凉经", "挂经", "日常实习", "暑期实习", "一面", "二面"],
            "notice": "仅生成检索计划；须实际搜索并阅读原帖后才能入库"}


def parser():
    result = argparse.ArgumentParser(description="OfferLoop：近期个人实习面经题库与面试记录")
    result.add_argument("--root", type=Path, default=Path(
        os.environ.get("INTERNSHIP_INTERVIEW_DATA") or Path.home() / ".interview-data"))
    result.add_argument("--as-of", type=day, default=today(), help="用户当地日期YYYY-MM-DD")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("window")
    commands.add_parser("catalog")
    list_sessions = commands.add_parser("sessions")
    list_sessions.add_argument("--profile", default="default")
    for name in ("plan", "ingest", "select", "prepare", "start"):
        command = commands.add_parser(name)
        command.add_argument("--role", required=True)
        command.add_argument("--direction", required=True)
        if name in {"ingest", "prepare"}:
            command.add_argument("--input", required=True, type=Path)
        if name in {"plan", "select", "start"}:
            command.add_argument("--company")
        if name in {"select", "start"}:
            command.add_argument("--count", type=int, default=5)
            command.add_argument("--topic", action="append", dest="topics")
            command.add_argument("--profile", default="default")
            command.add_argument("--review", choices=["all", "unseen", "weak"], default="all")
            command.add_argument("--seed", type=int)
        if name == "select":
            command.add_argument("--ready", action="store_true")
        if name == "start":
            command.add_argument("--mode", choices=["practice", "mock"], default="practice")
            command.add_argument("--question-ids", nargs="+")
    for name in ("show", "answer", "summary"):
        command = commands.add_parser(name)
        command.add_argument("--session", required=True, dest="session_id")
        command.add_argument("--profile", default="default")
        if name == "answer":
            command.add_argument("--input", required=True, type=Path)
        if name == "summary":
            command.add_argument("--finish", action="store_true")
    return result


def main(argv=None):
    args = vars(parser().parse_args(argv))
    root = args.pop("root").expanduser().resolve()
    as_of = args.pop("as_of")
    command = args.pop("command")
    try:
        if "input" in args:
            args["payload" if command in {"prepare", "answer"} else "batch"] = read_json(args.pop("input"))
        if command == "window":
            output = window(as_of)
        elif command == "plan":
            output = plan(as_of=as_of, **args)
        elif command == "show":
            output = public_progress(load_session(root, **args))
        elif command == "summary":
            output = summary(root, **args)
        elif command == "sessions":
            output = sessions(root, **args)
        else:
            output = globals()[command](root=root, as_of=as_of, **args)
        print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
