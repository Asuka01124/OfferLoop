# 评分v2的数据与交互

评分由宿主AI根据实际交流和已核对资料完成。脚本校验状态、记录引用、分值与版本，不能独立证明事实真伪或自动理解回答。以下示例是字段说明，`example.com`、题目ID与短证据均须替换为实际核验结果。

## 版本和评分表

题库的 `schema_version` 仍为1；评分表、会话与新结果使用 `scoring_version: 2`，两者含义不同。没有评分版本的旧评分表及旧会话按v1解释。`start` 只为v2评分表创建新会话；旧评分表须重新核验并 `prepare`，不能只补一个版本号。

`prepare` 的输入外层是 `{"rubrics": [{"question_id": "实际题目ID", "rubric": {...}}]}`。v2的rubric示例：

```json
{
  "scoring_version": 2,
  "question_kind": "基础问答",
  "assessment_target": "解释机制与执行边界，并用具体例子支持自己的理解",
  "assumptions": ["以本题明确的宿主环境为准"],
  "acceptable_alternatives": ["接受不同术语和等价实现，依据解释是否成立判断"],
  "nonessential": ["无需复述文档原话或列举所有扩展知识点"],
  "prepared_at": "2026-10-27",
  "criteria": [
    {
      "id": "mechanism",
      "label": "机制与可行性",
      "max_points": 6,
      "expected": ["说明该机制在具体环境中怎样生效"],
      "evidence_required": ["使用者自己的机制解释或可行实现"],
      "critical_errors": ["把与前提冲突的实现当作可行方案"]
    },
    {
      "id": "reasoning",
      "label": "依据与边界",
      "max_points": 4,
      "expected": ["解释成立条件与一个失败场景"],
      "evidence_required": ["使用者对例子、条件或验证过程的解释"],
      "critical_errors": []
    }
  ],
  "reference_answer": "填入本题经过资料核对的实际参考回答；它不是必须逐字覆盖的清单。",
  "common_mistakes": [],
  "references": [{"url": "https://example.com/reference", "title": "字段示例：与本题匹配的原始资料", "checked_at": "2026-10-27"}]
}
```

`question_kind` 须与原题相同，可为基础问答、算法编程、场景设计、故障排查、项目追问、行为面试。维度和权重按题型设置，总满分10；`expected` 只是参考，`evidence_required` 描述实际需要观察到什么，`critical_errors` 列真正影响正确性或可行性的错误。不要要求实习候选人达到题目未声明的资深岗位标准。

## 本题状态

继续使用 `answer --session ... --input ...`，根据输入的 `status` 保存草稿或结束本题：

| 输入status | 含义 | 是否推进主问题 |
| --- | --- | --- |
| `pending_clarification` | 含义不明确，先中性澄清 | 否 |
| `pending_verification` | 具体事实、版本或统计范围待核验 | 否 |
| `ready_to_score` | 本题交流和前提已确认，等待评分 | 否 |
| `scored` | 根据本题全部证据提交最终评价 | 是 |
| `invalid` | 题目或评分前提有错误，本题不计分 | 是 |
| `skipped` | 使用者明确要求跳过，本题不计分 | 是 |

首次提交须有原始 `answer`；后续可省略，但不能覆盖原始回答。补充回答使用 `rounds`。待处理状态禁止提交 `grade`、`score` 或 `total`，不会增加已处理题数。`show` 会返回当前状态、待问的 `followup_prompt` 和已有问答，方便续答。

### 澄清示例

首次记录使用者含义不清的回答：

```json
{
  "question_id": "实际题目ID",
  "answer": "控制级",
  "status": "pending_clarification",
  "reason": "控制级的具体含义尚不明确，不能判断为技术错误",
  "next_prompt": "你说的控制级具体指什么？能举一个实际例子吗？"
}
```

得到澄清回答后记录一轮对话，说明歧义如何解除：

```json
{
  "question_id": "实际题目ID",
  "status": "ready_to_score",
  "reason": "使用者已说明术语含义及实际例子",
  "resolution": "本轮已明确控制级所指的机制与边界",
  "rounds": [{"id": "r1", "kind": "clarification", "origin": "generated", "question": "你说的控制级具体指什么？能举一个实际例子吗？", "answer": "保存使用者的实际澄清回答"}]
}
```

每轮包含唯一 `id`、`kind`、`origin`、`question`、`answer`；只保存已完成的问答，待回答的问题放 `next_prompt`。`kind` 为 `clarification`（澄清）、`followup`（普通追问）、`hint`（实质解题提示）。同ID的相同轮次可以重试，不重复计数；不同内容须用新ID，不可覆盖。`origin: source` 的问法须能在原帖追问中找到，否则使用 `generated`。

`hints_used` 由 `hint` 轮次数计算，`clarifications_used` 单独统计；无需手动填写提示次数。不能把中性澄清算成提示，也不能把提供了解题方向的提示改名为澄清。通常一两轮足以完成判断，避免不断追加与原考察目标无关的追问。

### 核验示例

工具数量等问题必须明确具体主张及范围，先记录未核验事实：

```json
{
  "question_id": "实际题目ID",
  "answer": "保存使用者的原始回答",
  "status": "pending_verification",
  "reason": "需要先确认版本与统计口径",
  "evidence_checks": [{"id": "c1", "claim": "本题所说的工具数量限制", "scope": "明确产品、版本及统计的工具范围", "status": "unverified", "checked_at": "2026-10-27", "reason": "尚未取得与本题范围匹配的资料"}]
}
```

核验完成后，用相同ID、相同 `claim` 和 `scope` 更新为 `verified` 或 `refuted`，附 `source_url`、不超过320字符的 `excerpt`、真实 `checked_at` 和 `reason`。更换主张或范围必须另建ID，不能借此消掉原争议。进入 `ready_to_score/scored` 前所有争议须有结论，并提交 `resolution`；如果题目前提被证伪，可直接 `invalid` 并说明原因。

核验变更保存在 `evidence_events`，不覆盖历史。核对不到时保留待核验或结束为无效题；不能凭印象中的数字扣分。切换到另一种待处理状态也不会自动解除此前的歧义或事实争议。

## 最终评价

本题可以直接一次完成评价，也可以在草稿交流后提交；不要求每题都追问。评分前用 `readiness` 说明语义和相关事实为何已经清楚：

```json
{
  "question_id": "实际题目ID",
  "status": "scored",
  "readiness": {"meaning_clear": true, "facts_checked": true, "reason": "已结合实际回答、必要澄清与对应资料确认评分前提"},
  "grade": {
    "criteria": [
      {"id": "mechanism", "status": "assessed", "score": 5, "reason": "说明有证据支持的具体表现和扣分原因", "evidence_refs": ["initial", "round:r1"]},
      {"id": "reasoning", "status": "assessed", "score": 3, "reason": "说明本题边界分析中已确认的不足", "evidence_refs": ["round:r1"]}
    ],
    "confirmed": [{"claim": "本题已确认的表现", "evidence_refs": ["initial", "round:r1"]}],
    "issues": [{"claim": "本题有证据支持的具体问题", "evidence_refs": ["round:r1"]}],
    "unverified": ["没有通过本题实际考察的其他能力"]
  }
}
```

引用值可以是 `initial`、`round:轮次ID`、`check:核验ID`。不存在的轮次和未核验资料不能当评分证据；扣分须附 `issues`。即使有正确参考资料，也仍应从使用者自己的回答中判断其理解，不能把资料中的正确内容当作使用者已掌握的证据。

没有观察到的维度使用 `status: not_assessed`、`score: null`、空 `evidence_refs`，并在 `unverified` 说明缺少什么证据。脚本自动将该题结果标为 `partial`，保留已评价部分的 `earned_points/assessed_max_points`，但总分为null，不补零、不折算为满分、不进入平均分或低分错题筛选。能力未验证和已经证明错误须分开记录。

只有完整评价的本题才有0至10分，分数辅助描述本题面试表现。未覆盖的扩展知识不是自动扣分理由，也不能由一次口头回答推断整体开发能力。

## 跳过、无效、暂停与旧记录

- `skipped` 需要 `user_requested: true` 和 `reason`；`invalid` 需要说明错误前提或歧义。两者不带grade、不记零分、不进入平均分。明确的技术错误则应在可评价的本题中按证据评分，不能为了回避低分都设为无效。
- 暂停时保留草稿，用 `sessions/show` 恢复；明确结束时才调用 `summary --finish`。提前结束的草稿仍未评分，可在最终复盘中看到已有原始回答。
- 模拟模式的待处理状态与最终记录都不对使用者泄露评分、参考答案；结束后再复盘。轮次中不保存单独评分，避免先定分再追问。
- 缺少 `scoring_version` 的旧会话按v1展示并可继续完成，原分数不重算。新会话使用v2；旧评分表重新prepare后也不影响旧会话快照。
- 汇总按版本分别报告；即使历史数据出现混合版本，也不生成混合平均分。`weak` 只依据v2完整评分低于7或使用实质提示的记录，旧版低分和澄清次数不自动成为新规则下的弱项。
