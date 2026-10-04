# 接手说明

新接手这个项目，先读本文件，再按需深入。

**为什么需要它**：进度信息全在 `books/<slug>-notes/companion/` 第四层，
而 `.gitignore` 排除整个 `books/`（书有版权、工作区是高度个人化的学习状态）。
克隆仓库的人看不到任何状态，本文件补这一跳。

---

## 这是什么

把一本书变成一门只为一个读者开的课。AI 先精读全书产出知识表示，再通过对话
逐章讲授并检验，跨会话保留进度、卡壳点与间隔复习队列。**读者不翻原文。**

完整说明见 [README.md](README.md)。规则见
[skills/book-companion/SKILL.md](skills/book-companion/SKILL.md)。

**项目定位：公开发布（MIT），框架验证阶段。**
GitHub: [SkyblueCodingCat/book-companion](https://github.com/SkyblueCodingCat/book-companion)

核心流程可用，但规则与脚本接口仍在随实践调整。只被一本书、一个读者
完整验证过。vendor 基线见 [VENDOR.md](VENDOR.md)。

---

## 当前状态（2026-10-04）

> 唯一权威是 `books/思考快与慢-notes/companion/progress.md`。
> 本节是快照，与之冲突时以 progress.md 为准。

案例书：**《思考，快与慢》**中文版（中信 2012），TXT + EPUB 双格式。
847 页（合成页码），42 个推进单元。

```
阶段一精读范围   ch00–ch09（序言 + 第一部分）  ← 方案 D，定义见 map.md
                 ch10–ch38 无笔记，阶段二讲不了
                 ch40/ch41（两篇附录论文）已 skipped

ch00 序言        checked  费曼已做  首答 1/6  未达标
ch01 第1章       briefed  已讲 2/5 单元（主动停讲做密度控制）
ch02–ch39        pending

复习队列         5 项  全部属 ch00  到期 2026-10-03（已逾期）
达标章节         0
插图             17 张已提取，6 张已人工核对
回归             73 PASS / 0 FAIL
引文校验         94/94 clean
```

### 下一步三件事（顺序不能换）

1. **清 5 道逾期复习**。换题型，不原样重问（`question-design.md` 规定）。
   重点复验两处误解：「盘前计划 = 专家直觉」、「闲谈 = 放轻松」。
   素材在 `companion/briefs/ch00-brief.md` 的预埋题表里。
2. **讲 ch01 单元 3–5**。素材 `notes/ch01-two-systems.md`，
   导读稿与桥接策略 `companion/briefs/ch01-brief.md`，插图 `figures/fig03.jpeg`
   （**讲到前须先打开核对**，`INDEX.md` 里它还是 no）。
3. **ch01 检验**。6 题已预埋，但**须按新诊断提高场景题比例**（见下）。

### 接手前必读的两条约束

**进 D 阶段前必须声明两件事**：回答规则（答第一反应，不要优化）、
判据与计分方式。原因见 `framework-gaps.md` 缺口 6——这条被违反过一次，
导致一个不存在的理解缺陷被写进档案。

**单次会话最多讲 3 个论证单元**。ch01 有 5 个，所以讲解与检验必须分两次会话。
原因见缺口 4。

---

## 读者

- BSP 软件工程师（板级支持包，底层驱动／固件）
- 有基金／股票／期货交易经验，偏技术分析与交易心法
- 阅读目的原话："这本书很有名，我先以这本书为案例看下这套系统能否跑通"
  —— **即验证系统本身，不是首要求知**

完整画像、12 条交易桥接点、答题模式诊断、反馈偏好，全在
`books/思考快与慢-notes/companion/learner.md`。**接手前必读。**

两条最重要的个性化发现：

- **概念性内容必须先落到交易场景再提问。** 纯概念题他倾向标签式作答，
  落在经验领域的题他做实质机制分析——四次回应的分界线很清楚。
- **他明确要求批判性反馈**，不要一味肯定。但也不要为了显得批判而否认真实答对的
  事实，那是另一种失真。

---

## 自研 vs 外部：实际占比

| 部分 | 规模 | 归属 |
| --- | --- | --- |
| `skills/deep-reader/` | 16 文件 · 1308 行 shell · 989 行文档 | **外部**，MIT，[tronghieu/agent-skills](https://github.com/tronghieu/agent-skills)，版权 Hieu T. Luu。未改动 |
| `skills/book-companion/scripts/` | 1929 行 Python | 自研 |
| `skills/book-companion/` 规则文档 | 1220 行（SKILL.md + 5 篇 references） | 自研 |
| `skills/book-companion/tests/` | 772 行 · 73 用例 | 自研 |
| `skills/book-companion/templates/` | 140 行 | 自研 |
| 项目级（README + install.sh） | 355 行 | 自研 |

代码量上自研约 2700 行 Python vs vendor 1300 行 shell。但**行数不等于贡献比例**，
真实的分工是：

**直接复用 deep-reader 的**（不重写，这是刻意决定）：
- 多遍读方法论（检视阅读 → 逐章分析 → 综合），源头是 Adler《如何阅读一本书》
- `[[page N]]` 页码坐标系这个设计
- 笔记模板格式（`note-templates.md`）、体裁策略（`genre-strategies.md`）
- PDF 转换路径（`pdftotext` 真实 form feed 分页，那条路本来就对）
- Recite 校验步骤（SQ3R）、论文三遍法（Keshav）

**借鉴设计思路但自己实现的**：
- 间隔复习档位 1/3/7/21 天 — 参考 [SebastianElvis/hammer](https://github.com/SebastianElvis/hammer) 的 `teach` skill
- 命令形状（where / next / review / 进度查询）— 参考 [orhoncan/deep-study-skill](https://github.com/orhoncan/deep-study-skill)
- 持久化学习者状态的概念 — 同样来自 hammer

**完全自研的**（这是项目的实际价值所在）：
- **五步循环 A→E** 及其全部规则（`teaching-loop.md` 247 行）——
  这是本项目的核心，生态里没有现成的"AI 读、AI 讲、你靠对话学完"的教学循环
- **章节状态机** pending→briefed→taught→checked→passed(+skipped) 及达标判据
- **答案保护、两级提示降级、费曼环节**的具体规则
- **出题规则**（`question-design.md`）：检索型而非识别型、五种题型、答案要点写判定
  标准而非标准答案
- **反模式清单**（`anti-patterns.md`）12 条
- 全部状态文件的字段定义（`state-schema.md`）
- **四个补 vendor 缺口的工具**：CJK 感知分页、CJK 引文校验、EPUB 提图、
  静默缺字审计。这四个都是 deep-reader 在中文书上失效的位置，见 `framework-gaps.md`

一句话概括：**读书那一半是别人的，教学那一半是自己的；而中文适配是自己补的。**

---

## 关键文件地图

```
HANDOFF.md              ← 你在这里
framework-gaps.md       10 个框架缺口的完整登记（项目主要产出之一）
README.md               项目说明、架构、安装、设计取舍

skills/book-companion/
├── SKILL.md            硬规则 14 条 + 两阶段 + 命令集
├── references/
│   ├── teaching-loop.md      五步循环完整规则（执行阶段二前必读）
│   ├── ingest.md             阶段一衔接、格式选择、提图、降级路径
│   ├── question-design.md    出题规则
│   ├── state-schema.md       状态文件字段定义
│   └── anti-patterns.md      12 条反模式（觉得"这样对读者更友好"时读）
├── scripts/
│   ├── companion_router.py   状态调度（init/where/next/mark/review/status）
│   ├── prepare_source.py     阶段一转换入口（CJK 感知分页 + 缺字审计）
│   ├── extract_figures.py    EPUB 提图 + 图号关联
│   ├── verify_quotes_cjk.py  CJK 引文校验（替代 vendor 失效的版本）
│   └── utils/                markdown / workspace / state
└── tests/run_regression.py   自包含，不依赖真实书

books/思考快与慢-notes/
├── source.txt chapters.tsv chapters/ map.md terms.md notes/ synthesis.md
│                           ← deep-reader 产出，书的知识表示
├── figures/                ← 提取的插图 + INDEX.md（含核对状态）
└── companion/              ← book-companion 产出，读者的学习状态
    ├── progress.md         唯一权威的进度来源
    ├── learner.md          读者画像 + 诊断（接手必读）
    ├── review.md           间隔复习队列
    ├── briefs/             每章导读稿 + 预埋检验题（不给读者看）
    └── sessions/           每次会话的判断记录
```

---

## 常用命令

```bash
# 状态查询（只读）
python3 skills/book-companion/scripts/companion_router.py where  --workspace "books/思考快与慢-notes"
python3 skills/book-companion/scripts/companion_router.py status --workspace "books/思考快与慢-notes"
python3 skills/book-companion/scripts/companion_router.py review list --workspace "books/思考快与慢-notes"

# 测试（自包含，不碰项目目录）
python3 skills/book-companion/tests/run_regression.py

# 引文校验（在工作区内运行）
cd "books/思考快与慢-notes" && python3 ../../skills/book-companion/scripts/verify_quotes_cjk.py .
```

注意：`zsh` 不对未加引号的变量做词分割，把命令存进变量再 `$VAR args` 会把整个
变量当成命令名。写完整命令或用数组。

---

## 未决决策

需要项目所有者决定，接手的 agent 不要代为决定。

| 项 | 卡在哪 |
| --- | --- |
| **ch10–ch38 的精读粒度** | `map.md` 明确写着"待读者体验五步循环后决定"。全书逐章 42 份笔记约需 60–80 万 token；按部分合并则每单元过大 |
| **ch00 是否重考** | 三处记录都写"由复习结果决定"，复习尚未做 |
| **ch01 原文曝露** | 读者在 ch01 讲解前打开过 `chapters/ch01-1-1-2.txt`，经询问未答复。首答数据的可解释性受影响，`ch01-brief.md` 已标注 |
| **`review.md` 的「已用题面」字段** | 复习要求换题型，但用过的题面无处存放。加列 vs 另起区块各有代价，见 `framework-gaps.md`「设计分叉」 |
| **`regression_results.md` 是否保留** | 已改为自动重生成，但文件本身意义有限，可考虑改为 CI 产物 |

已闭合（原在本表，定位确定为公开发布后解决）：git init 与 vendor 基线 SHA、
自研部分许可、`最后动作` 列语义。经过见 `framework-gaps.md`
「发布准备中闭合的项」。

---

## 一条结构性限制

**阶段二的 D（检验）和 E（回流）两步，没有真实读者在场就无法推进。**

`teaching-loop.md` 写得很明确：agent 对读者理解水平的判断**完全依赖回答本身，
没有第二个信息源**。可以写导读稿、可以出题，但不能代答、不能伪造判断——
一旦伪造，发虚清单、复习队列、讲解深度三者同时失真，而这正是项目自己标记为
"系统要害"的失效模式。

读者不在场时，可做的是文档与工具侧的工作（见「未决决策」与
`framework-gaps.md` 的「未修／待决」）。
