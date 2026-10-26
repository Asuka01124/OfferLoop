# 数据约定与命令

## 位置与格式

Python 3.10+，无第三方依赖。全局选项 `--root`、`--as-of` 放在子命令之前。日期为YYYY-MM-DD；默认使用Asia/Shanghai的当天，90天窗口含首尾，起点为当天减89天。`--as-of` 应从宿主用户日期传入，不能为让旧帖通过而伪造日期。

```text
<data-root>/
  banks/后端开发/Java.json
  banks/大模型应用开发/Agent.json
  reports/<日期-唯一标识>.json
  profiles/<用户代号>/sessions/<会话ID>.json
```

`banks` 文件包含 `schema_version: 1`、`role`、`direction`、`updated_at`、以ID索引的 `sources` 和 `questions` 对象。ID由规范化后的URL或题目生成，跨次更新稳定。只有已有合格来源时才创建题库文件；失败候选只进入报告。

脚本做结构和一致性校验，无法自行证明AI填写的证据真实；调用者必须先读原帖。写入采用同目录临时文件加原子替换，并用数据目录写锁拒绝并发写入。题库和报告是两个独立文件，不是跨文件事务；发生磁盘错误时检查两者后重试，同一来源和问法可幂等导入。旧题和旧来源保留用于追溯，选题时过滤过期来源。

默认路径为 `~/.codex/internship-interview-data`，可用环境变量 `INTERNSHIP_INTERVIEW_DATA` 或 `--root` 更改。若受工作区写权限约束，明确采用稳定的工作区数据目录。不要把用户的真实回答、简历或运行数据提交进Skill Git仓库。

## 命令速查

以下为PowerShell调用示意，先将路径赋值为当前环境的实际绝对路径：

```powershell
$interviewScript = 'D:\codex-session\internship-interview\scripts\interview_bank.py'
$interviewDataRoot = 'D:\codex-session\internship-interview-data'
python $interviewScript --root $interviewDataRoot window
python $interviewScript --root $interviewDataRoot catalog
python $interviewScript --root $interviewDataRoot sessions --profile 'default'
python $interviewScript --root $interviewDataRoot plan --role '后端开发' --direction 'Java'
python $interviewScript --root $interviewDataRoot ingest --role '后端开发' --direction 'Java' --input 'D:\codex-session\batch.json'
python $interviewScript --root $interviewDataRoot select --role '后端开发' --direction 'Java' --count 5 --profile 'default'
python $interviewScript --root $interviewDataRoot prepare --role '后端开发' --direction 'Java' --input 'D:\codex-session\rubrics.json'
python $interviewScript --root $interviewDataRoot start --role '后端开发' --direction 'Java' --mode practice --profile 'default' --question-ids q_ID1 q_ID2
python $interviewScript --root $interviewDataRoot show --profile 'default' --session SESSION_ID
python $interviewScript --root $interviewDataRoot answer --profile 'default' --session SESSION_ID --input 'D:\codex-session\answer.json'
python $interviewScript --root $interviewDataRoot summary --profile 'default' --session SESSION_ID
```

`SESSION_ID`、`q_ID1` 等必须替换为上一步实际返回的ID，不是固定值。`sessions` 列出当前用户的会话，可据此继续尚未完成的面试；不返回评分或参考答案。面试停止时仅在使用者明确要求结束后给 `summary` 添加 `--finish`，这会将未完成会话标为提前结束；未答题不按零分计。

`select/start` 支持 `--company '字节'`、可重复的 `--topic 'Redis'`（任一标签匹配）、`--review all|unseen|weak`、`--seed 42`。`select --ready` 只选已有评分表的题；默认也返回待准备题目。`weak` 指上次主问题得分低于7或使用过提示。默认 `all` 在覆盖知识点的同时优先未做题。`start --question-ids ...` 保留已准备题目的明确顺序，仍核验岗位、来源时效和筛选条件。未传ID则按 `--count` 自动选择已准备题，数量不足报错。

`select` 输出是供面试官AI使用的内部信息，包含来源与可能存在的评分表；不要原样展示给使用者。`start/show` 仅输出当前题目和进度，不泄露答案。

## 采集批次

根对象包含 `sources` 数组和可选 `searches` 数组。每个来源至少有URL和访问状态；未成功核验的条目允许字段不全，脚本将其标为待核验或排除。成功候选遵循下面的形状。此例完全是字段说明，`example.com` 与正文均为虚构，不可当真实面经导入生产题库：

```json
{
  "searches": [{"platform": "个人博客", "query": "后端开发 Java 实习 面经 2026-10", "checked": 1}],
  "sources": [{
    "url": "https://example.com/interview/123",
    "title": "字段示例：后端实习一面记录",
    "platform": "个人博客",
    "author": "示例作者",
    "published_at": "2026-10-20",
    "interview_at": "2026-10-19",
    "company": "示例公司",
    "department": null,
    "role": "后端开发",
    "round": "一面",
    "internship_type": "日常实习",
    "personal_account": true,
    "is_original": true,
    "access_status": "full",
    "experience_key": "同一人同一次面试跨平台共享的标识",
    "verification": {
      "method": "web",
      "verified_at": "2026-10-26",
      "publication_kind": "first_published",
      "publication_excerpt": "原页显示首次发布于2026-10-20",
      "personal_excerpt": "作者自述：昨天参加了这家公司的第一轮面试",
      "internship_excerpt": "作者自述：投递的是Java日常实习岗位"
    },
    "questions": [{
      "text": "HashMap的底层实现是什么？",
      "canonical_text": "HashMap的底层实现是什么？",
      "kind": "基础问答",
      "difficulty": "基础",
      "tags": ["Java", "集合", "HashMap"],
      "followups": ["为什么使用红黑树？"]
    }]
  }]
}
```

- `access_status` 成功值：`full`、`user_provided_full`。受限页面可用 `login_required`、`points_required`、`captcha`、`failed`、`snippet_only`，并填 `skip_reason`。
- `verification.method` 为 `web`、`browser`、`user_provided`；用户提供正文对应 `user_provided_full`，仍需可核验的日期和来源链接。
- `personal_account/is_original` 必须是布尔值true，不能用字符串。`publication_kind` 必须为 `first_published`。
- `interview_at` 未说明时填null，不能推算。`company/round/department` 未提供也可填null。`role` 使用本次确认的岗位分类，原始岗位写法可额外放 `role_original`。
- `internship_type` 为 `日常实习`、`暑期实习`、`实习`、`转正面试`；最后一项限确为实习转正。
- 题型 `kind` 为 `基础问答`、`算法编程`、`场景设计`、`项目追问`、`行为面试`。难度 `difficulty` 为 `基础`、`中等`、`深入`、`未评估`。
- `text` 是原始问法，`canonical_text` 是不改变约束的整理问法。算法题必须保留输入输出要求、约束和边界条件，不能只记一个算法标签。
- 语义归并时加 `merge_into: "实际存在的q_ID"`，只有核对原题约束后才可使用；自动规范化保留C++、C#、不等号和小数等语义，不进行模糊匹配。
- `experience_key` 由同一次面试的最初原帖或经核验的经历标识确定；缺省使用规范化URL。发现跨平台同次经历时须显式统一该值，否则不能宣称频次已跨站彻底去重。
- 同一原帖多轮面试的不同问题可以在题目里附 `round_original`；按原帖保存的轮次不足以表达时应拆出明确的经历标识，不能猜测轮次。

## 准备评分表

根对象：`{"rubrics": [{"question_id": "实际题目ID", "rubric": {...}}]}`。每个rubric包含：

```json
{
  "prepared_at": "2026-10-26",
  "criteria": [
    {"id": "correctness", "label": "技术正确性", "max_points": 5, "expected": ["结合题目所问版本解释正确的数据结构"]},
    {"id": "coverage", "label": "关键点覆盖", "max_points": 2, "expected": ["解释定位、冲突处理和扩容"]},
    {"id": "reasoning", "label": "原理与边界", "max_points": 2, "expected": ["区分版本差异和适用条件"]},
    {"id": "clarity", "label": "表达", "max_points": 1, "expected": ["逻辑清楚，术语准确"]}
  ],
  "reference_answer": "此处必须写经过资料核对、适合口述的实际答案，不能直接复制字段示例。",
  "common_mistakes": ["混淆实现细节与API保证"],
  "references": [{"url": "https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html", "title": "Java 21 HashMap API", "checked_at": "2026-10-26"}]
}
```

各维度的expected必须是本题具体要求。引用资料必须实际支持参考答案；例如讨论红黑树实现时API文档不足，应另核对对应版本源码。示例日期均应换成本次真实日期。

## 回答与评分记录

`answer` 输入示例形状：

```json
{
  "question_id": "实际题目ID",
  "answer": "使用者的原始回答",
  "hints_used": 0,
  "grade": {
    "criteria": [
      {"id": "correctness", "score": 4, "reason": "指出回答中具体正确之处和错误"},
      {"id": "coverage", "score": 1, "reason": "指出遗漏的本题关键点"},
      {"id": "reasoning", "score": 1, "reason": "指出边界或原因解释的不足"},
      {"id": "clarity", "score": 1, "reason": "表达清楚"}
    ],
    "strengths": ["基于实际回答填写"],
    "gaps": ["基于冻结评分表填写"]
  },
  "followups": []
}
```

`followups` 可存 `{question, answer, origin: "source"|"generated", feedback}`；`source` 追问必须与已保存原帖追问一致。使用者明确跳过时传 `skipped: true`、空answer与各维度零分。不能用空回答代表尚未作答。

脚本计算总分并校验维度，不接受调用者直接提供未经校验的total。练习模式立即返回评分和参考答案；模拟模式只返回进度，结束后通过summary统一揭晓。会话中的题目与评分表是开始时快照，后续更新题库不会改变已经开始的面试。
