# 实习面试教练

一个面向计算机实习求职的 Agent Skill：收集最近 **90 天**发布的个人面经，按岗位和方向维护本地 JSON 题库，再开展逐题练习、模拟面试、评分和错题复习。

Agent 负责联网检索、阅读原帖、提取问题与评价回答；Python 脚本负责日期过滤、数据校验、增量保存、选题和练习记录。

## 功能

- **先选岗位，再更新**：每次更新都根据本次需求确定岗位和方向，支持指定公司。
- **核验近期个人面经**：保留原帖链接、首次发布日期、面试时间、原始问法和核验依据。
- **按岗位分类**：例如 `后端开发/Java.json`、`大模型应用开发/Agent.json`。
- **增量更新和去重**：合并同题，保留多个来源；已识别的同一次面试跨平台分享共用经历标识。
- **两种面试模式**：逐题练习立即反馈；模拟面试结束后统一评分。
- **评分依据固定**：出题前准备评分表，开始面试时保存快照，后续题库更新不改变本场评分条件。
- **持续复习**：区分独立回答与提示后回答，支持未做题、薄弱题筛选和继续上次面试。
- **跨 Agent 共用数据**：同一系统用户默认使用 `~/.interview-data`。

## 环境要求

- Python **3.10 或更新版本**；题库管理脚本仅依赖标准库。
- 支持读取 `SKILL.md`、运行本地命令和读写文件的 Agent。
- 采集时需要联网搜索、网页阅读能力，或由使用者提供可核验的原帖正文。

题库按需建立，仓库中不附带真实面经题库或个人练习记录。

## 安装

先克隆仓库，或下载 ZIP 后解压：

```bash
git clone https://github.com/Asuka01124/internship-interview.git
cd internship-interview
```

将以下文件和目录复制到所用 Agent 的技能目录中：

```text
internship-interview/
├─ SKILL.md
├─ README.md
├─ agents/
├─ references/
├─ scripts/
└─ tests/
```

| Agent | 个人技能目录 | 调用方式 |
| --- | --- | --- |
| Codex | `~/.codex/skills/internship-interview/` | `$internship-interview` |
| Claude Code | `~/.claude/skills/internship-interview/` | `/internship-interview` |
| 其他 Agent | 使用其支持的技能加载位置 | 让 Agent 读取 `SKILL.md` 并按指令执行 |

Windows PowerShell 中，从本仓库根目录安装到 Codex 的示例：

```powershell
$interviewUserHome = [Environment]::GetFolderPath('UserProfile')
$interviewSkillTarget = Join-Path $interviewUserHome '.codex\skills\internship-interview'
New-Item -ItemType Directory -Path $interviewSkillTarget -Force | Out-Null
Copy-Item -Path '.\SKILL.md', '.\README.md', '.\agents', '.\references', '.\scripts', '.\tests' -Destination $interviewSkillTarget -Recurse
```

安装到 Claude Code 时，将目标中的 `.codex` 改为 `.claude`。若同名技能已经存在，先确认版本，再决定更新。`agents/openai.yaml` 是 Codex 的展示元数据，核心流程由 `SKILL.md`、参考文档和 Python 脚本组成。

Claude Code 的技能加载位置及调用方式见[官方文档](https://code.claude.com/docs/zh-CN/skills)。安装后可在新的 Agent 会话中检查是否能发现该技能。

## 快速开始

### 1. 更新题库

在 Codex 中输入：

```text
使用 $internship-interview，更新题库。
```

Skill 会先询问岗位或方向。也可以一次说清楚：

```text
使用 $internship-interview，更新 Java 后端实习题库，优先找字节和美团最近三个月的个人面经。
```

Claude Code 中使用对应命令：

```text
/internship-interview 更新大模型 Agent 应用开发实习题库。
```

采集结束后会报告检索范围、候选与收录数量、待核验和排除原因、新增题量及实际数据位置。题量不足时会说明结果，不自动用旧题或生成题补齐。

### 2. 开始面试

```text
使用 $internship-interview，选择 Java 后端，进行 5 道题的逐题练习，每题回答后评分。
```

```text
使用 $internship-interview，模拟一场大模型 Agent 开发实习面试，结束后统一评分。
```

未指定岗位时，Skill 会展示已有题库供选择。默认逐题练习、5 道题；每轮只展示一道主问题。

### 3. 复习或继续

```text
使用 $internship-interview，复习 Java 后端里我上次没答好的题。
```

```text
使用 $internship-interview，继续我上次没完成的面试。
```

多人共用时，指定不同的用户代号 `profile`，分别保存回答和成绩。

## 数据存在哪里

默认保存在当前操作系统用户的主目录下：

```text
~/.interview-data/
├─ banks/
│  ├─ 后端开发/
│  │  └─ Java.json
│  └─ 大模型应用开发/
│     └─ Agent.json
├─ reports/
│  └─ 每次采集的核验与统计报告.json
└─ profiles/
   └─ 用户代号/
      └─ sessions/
         └─ 面试会话.json
```

以上为数据形成后的结构示例，目录和题库文件按需生成。Windows 路径为 `C:\Users\你的用户名\.interview-data`；macOS/Linux 为 `~/.interview-data`。

数据位置优先级：

1. 命令行 `--root` 指定的目录。
2. 环境变量 `INTERNSHIP_INTERVIEW_DATA`。
3. 默认目录 `~/.interview-data`。

在同一系统用户下，Codex 和 Claude Code 使用相同数据位置即可共用题库。不同机器、不同用户以及 WSL 等环境各有自己的主目录，需要显式指定共同可访问的位置。

本项目默认在本机保存题库和回答，不会自动将运行数据上传到 GitHub。脚本使用原子文件替换和写锁保护数据；多个 Agent 同时更新时，遇到锁提示应稍后重试。

## 面经收录规则

| 项目 | 默认规则 |
| --- | --- |
| 时间窗口 | 包含当天的最近 90 个自然日，即 `[当天 − 89 天, 当天]` |
| 发布日期 | 核验原帖首次发布日期；修改时间和搜索抓取时间不算新发布 |
| 面试日期 | 明确提供时也必须在窗口内；未提供则保留为空并降低选题优先级 |
| 内容来源 | 个人参加实习面试的原帖，已经读取正文并记录证据 |
| 岗位范围 | 日常实习、暑期实习、其他实习，以及实习转正面试 |
| 暂不入库 | 转载合集、仅有摘要、日期不明、无法读取正文或无法确认实习身份的内容 |
| 过期来源 | 保留历史记录，正式选题时重新过滤 |

“个人面经”依据作者自述和原帖证据判断。搜索覆盖多个平台，但实际收录范围取决于检索结果和可访问性；受登录、积分或验证码限制的页面会记录原因。

自动去重采用保守的文本规范化；语义相似题由 Agent 核对约束后明确归并。面经原题、原帖追问和根据回答生成的补充追问分别标注。

## 评分方式

每题总分为 **10 分**。基础问答可采用以下维度，具体题目可调整分配：

| 维度 | 分值 |
| --- | ---: |
| 技术正确性 | 5 |
| 关键点覆盖 | 2 |
| 原理、边界和取舍 | 2 |
| 表达清晰度 | 1 |

Agent 先核对技术资料，保存本题评分要点，再开始提问。回答后逐项说明得分和扣分原因，接受正确的等价表述。算法题另考虑正确性、复杂度及边界条件。

Python 脚本校验评分维度和分值范围并计算总分，技术评价由 Agent 完成。原帖作者的回答仅作参考；提示后答对、独立答对和主动跳过分别记录。提前结束时，尚未回答的题不计零分。

## 命令行与维护

从仓库根目录运行：

```bash
python scripts/interview_bank.py window
python scripts/interview_bank.py catalog
python scripts/interview_bank.py plan --role 后端开发 --direction Java
python scripts/interview_bank.py sessions --profile default
```

`plan` 输出供 Agent 执行的检索建议。完整命令与 JSON 格式见[数据约定与命令](references/data-and-cli.md)。

| 文件 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | 技能入口、模式选择和核心约束 |
| [references/collection.md](references/collection.md) | 检索、来源核验和收录流程 |
| [references/interview.md](references/interview.md) | 选题、面试交互和评分规则 |
| [references/data-and-cli.md](references/data-and-cli.md) | 数据字段、输入格式和命令说明 |
| [scripts/interview_bank.py](scripts/interview_bank.py) | 题库与练习会话管理 |
| [tests/test_interview_bank.py](tests/test_interview_bank.py) | 日期、去重、评分和会话流程测试 |

运行测试：

```bash
python -X utf8 -m unittest discover -s tests -v
```

代码注释和文档字符串使用英文，技能说明和交互默认使用简体中文。
