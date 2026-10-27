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
- 选择下面的 Skills CLI 安装方式时，另需 Node.js **22.20 或更新版本**及 Git；手动安装无需 Node.js。

题库按需建立，仓库中不附带真实面经题库或个人练习记录。

## 安装

### 方式一：一条命令安装（推荐）

在终端运行 [Vercel Skills CLI](https://github.com/vercel-labs/skills) 的安装命令，按提示选择使用的 Agent：

```bash
npx skills add Asuka01124/internship-interview --skill internship-interview -g
```

`-g` 表示安装到用户级目录，跨项目可用；去掉它则只安装到当前项目。安装器会识别本仓库根目录的 `SKILL.md`，下载技能及配套文件并处理目标目录，无需手动挑选文件。

也可以直接指定 Agent。

**Codex：**

```bash
npx skills add Asuka01124/internship-interview --skill internship-interview -g -a codex
```

**Claude Code：**

```bash
npx skills add Asuka01124/internship-interview --skill internship-interview -g -a claude-code
```

需要同时安装时，可使用 `-a codex claude-code`。Windows 中若符号链接不可用，可在命令末尾加 `--copy`。

私有仓库的安装者需要仓库访问权限，并配置 Git、GitHub CLI 或 SSH 认证。仓库当前为私有；出现访问失败时先检查权限，安装命令不能替代仓库授权。详见 Skills CLI 的[安装与认证说明](https://github.com/vercel-labs/skills/blob/main/docs/commands.md#private-repositories)。

已经通过 Git 或 ZIP 下载到本机时，也可以直接让安装器读取本地目录。例如在下载的仓库根目录运行：

```bash
npx skills add . --skill internship-interview -g
```

本地来源安装适用于已下载的副本；后续有新版本时先更新这份本地副本，再重新安装。

### 方式二：让 Codex 安装

在 Codex 中输入：

```text
使用 $skill-installer，从 https://github.com/Asuka01124/internship-interview 安装根目录下的 internship-interview 技能。
```

Codex 会调用自带的安装器。此方式无需手动运行 Python 安装脚本；私有仓库同样需要访问权限。安装完成后检查技能是否可见，若未出现再重启会话。

### 方式三：手动安装（备用）

将**完整仓库**克隆或解压到下面的目标目录，确保 `SKILL.md` 直接位于 `internship-interview/` 内，不再嵌套同名文件夹：

| Agent | 个人技能目录 | 调用方式 |
| --- | --- | --- |
| Codex | `~/.agents/skills/internship-interview/` | `$internship-interview` |
| Claude Code | `~/.claude/skills/internship-interview/` | `/internship-interview` |
| 其他 Agent | 使用其支持的技能加载位置 | 让 Agent 读取 `SKILL.md` 并按指令执行 |

Windows PowerShell 中，直接安装到 Codex 用户级目录的示例：

```powershell
$interviewUserHome = [Environment]::GetFolderPath('UserProfile')
$interviewSkillsParent = Join-Path $interviewUserHome '.agents\skills'
$interviewSkillTarget = Join-Path $interviewSkillsParent 'internship-interview'
if (Test-Path -LiteralPath $interviewSkillTarget) { throw 'Skill already exists; update its current installation.' }
New-Item -ItemType Directory -Path $interviewSkillsParent -Force | Out-Null
git clone --depth 1 https://github.com/Asuka01124/internship-interview.git $interviewSkillTarget
```

macOS/Linux 的 Codex 示例：

```bash
mkdir -p ~/.agents/skills
git clone --depth 1 https://github.com/Asuka01124/internship-interview.git ~/.agents/skills/internship-interview
```

Claude Code 对应使用 `~/.claude/skills/`，Windows 示例中的 `.agents` 换为 `.claude`。同一 Agent 已有同名技能时，应更新现有安装，避免在多个目录重复安装。`agents/openai.yaml` 是 Codex 的展示元数据，核心流程由 `SKILL.md`、参考文档和 Python 脚本组成。

以上目录对应[当前 Codex 官方文档](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)、[Claude Code 官方文档](https://code.claude.com/docs/zh-CN/skills)和 [Skills CLI 的 Agent 路径表](https://github.com/vercel-labs/skills/blob/main/docs/agents.md)。具体位置也可能受 Agent 配置或安装器版本影响，安装后以实际输出为准。

### 检查安装与更新

通过 Skills CLI 安装后，可以检查用户级安装列表：

```bash
npx skills list -g
```

按 Agent 筛选，例如 `npx skills list -g -a codex`。后续只更新本技能：

```bash
npx skills update internship-interview -g
```

手动安装的副本由所用下载或 Git 工作流更新。安装方式只影响技能文件的位置；题库和练习记录仍独立保存在 `~/.interview-data`。

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
