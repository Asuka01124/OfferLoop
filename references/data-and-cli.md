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

默认路径为用户主目录下的 `~/.interview-data`，在同一操作系统用户下与Agent名称和Skill安装位置无关。Windows示例为 `C:\Users\你的用户名\.interview-data`，macOS/Linux为 `~/.interview-data`。可用环境变量 `INTERNSHIP_INTERVIEW_DATA` 或 `--root` 更改，优先级为命令行、环境变量、默认目录。若宿主限制写入，申请该目录的必要写权限，不静默改存工作区。不同机器、WSL或不同系统用户拥有各自主目录，跨环境共用需要显式指定同一个可访问位置。不要把用户的真实回答、简历或运行数据提交进Skill Git仓库。

## 命令速查

以下为PowerShell调用示意，先将路径赋值为当前环境的实际绝对路径：

```powershell
$interviewScript = 'D:\codex-session\OfferLoop\scripts\interview_bank.py'
$interviewDataRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.interview-data'
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

`select/start` 支持 `--company '字节'`、可重复的 `--topic 'Redis'`（任一标签匹配）、`--review all|unseen|weak`、`--seed 42`。`select --ready` 只选已有v2评分表的题；默认也返回待准备题目。`weak` 只参考v2完整评分低于7或使用实质提示的记录，旧版低分、部分评价和中性澄清不作为弱项依据。默认 `all` 在覆盖知识点的同时优先未做题。`start --question-ids ...` 保留已准备题目的明确顺序，仍核验岗位、来源时效和筛选条件。未传ID则按 `--count` 自动选择已准备题，数量不足报错。

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
- 题型 `kind` 为 `基础问答`、`算法编程`、`场景设计`、`故障排查`、`项目追问`、`行为面试`。难度 `difficulty` 为 `基础`、`中等`、`深入`、`未评估`。
- `text` 是原始问法，`canonical_text` 是不改变约束的整理问法。算法题必须保留输入输出要求、约束和边界条件，不能只记一个算法标签。
- 语义归并时加 `merge_into: "实际存在的q_ID"`，只有核对原题约束后才可使用；自动规范化保留C++、C#、不等号和小数等语义，不进行模糊匹配。
- `experience_key` 由同一次面试的最初原帖或经核验的经历标识确定；缺省使用规范化URL。发现跨平台同次经历时须显式统一该值，否则不能宣称频次已跨站彻底去重。
- 同一原帖多轮面试的不同问题可以在题目里附 `round_original`；按原帖保存的轮次不足以表达时应拆出明确的经历标识，不能猜测轮次。

## 准备评分表

完整字段与可复制的JSON形状见[评分v2的数据与交互](scoring-v2.md)。根对象为 `{"rubrics": [{"question_id": "实际题目ID", "rubric": {...}}]}`。必须先核对资料，再调用 `prepare`。

新评分表使用 `scoring_version: 2`，声明本题的 `question_kind`、`assessment_target`、`acceptable_alternatives`，每个维度有 `evidence_required`。评分维度满分合计10分，关注可观察的理解与可行性，不能将参考答案作为关键词清单。题型必须匹配原题。`catalog` 的 `questions_prepared` 统计v2表，`questions_prepared_legacy` 单独统计旧表。

旧表仍可读取，但用于新面试时须重新核验并prepare为v2；不能只补版本号。`start` 保存当前题目和评分表的快照，后续题库更新不影响已开始的会话。

## 回答、续答与评分

`answer` 可以多次保存同一道题，尚未完成时不推进题号。首次记录带原始 `answer`；以后省略或保留完全相同的值，补充回答写入 `rounds`，不能覆盖原文。

| 场景 | 输入与行为 |
| --- | --- |
| 含义不清 | `status: pending_clarification`，附reason与中性next_prompt，不带分数 |
| 事实争议 | `status: pending_verification`，记录明确claim、scope及未核验的evidence_checks |
| 续答澄清 | 追加已完成的clarification轮次，附resolution；尚未结束时继续保存待处理状态 |
| 核验完成 | 更新同ID核验结论，附匹配的来源与短证据，不得换主张或范围 |
| 等待评分 | `status: ready_to_score`，确认歧义和争议已解除，暂不提交分数 |
| 最终评分 | `status: scored`，附readiness和grade，评价本题全部交流 |
| 主动跳过 | `status: skipped`、`user_requested: true`及reason，无grade、无分数 |
| 无效题 | `status: invalid`及reason，无grade、无分数 |

每轮 `rounds` 只保存id、kind、origin、question、answer。kind区分clarification、followup、hint，原帖追问的origin为source且必须能找到原始记录；生成追问为generated。提示次数按hint轮次计算，澄清次数另记，不能在轮次中预存评分或反馈。

grade覆盖全部维度，每个维度声明assessed或not_assessed；结论使用confirmed、issues、unverified三部分。已评价维度及确认、问题结论须引用使用者原答或对话，外部资料不能单独证明使用者掌握了什么。扣分须有具体问题和证据引用。

未评价维度的score为null、证据数组为空，并说明未验证内容；脚本将结果标为partial，保留已评价部分分子与满分，总分为空，不补零、不折算满分。完整评价才计算0至10分。调用者不能自行提交未经校验的总分。

练习模式在本题完成后返回反馈与参考答案；模拟模式只返回进度，结束后通过summary统一揭晓。`show` 返回已有问答、当前状态和待问问题，可恢复草稿。暂停无需finish；使用者明确要求提前结束时才调用 `summary --finish`，草稿仍保留为未评分。

`summary` 提供scoring_version、score_groups、scored_questions、unscored_questions、pending_questions、hinted_answers及clarified_answers。partial、invalid、skipped和未答题不进入平均分。旧会话按v1读取或继续，原分数不重算；混合版本分别汇总，不生成混合平均分。分数只描述本次题目中的面试表现，不能代表整体开发能力。
