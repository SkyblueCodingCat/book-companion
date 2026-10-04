# book-companion

把一本书变成一门只为一个读者开的课。

AI 先把整本书真正读懂，然后通过对话一章一章讲给你，每章讲完检验你是否真的学会，
跨会话保留进度、卡壳点和间隔复习队列。你不需要翻原文。

## 为什么自己搭

GitHub 上的书类 skill 都在做两件事之一，没有一个做第三件：

| 模式 | 谁读原文 | 交互入口 | 代表 |
| --- | --- | --- | --- |
| 你读，AI 陪聊 | 你 | 随时提问 | [deep-study-skill](https://github.com/orhoncan/deep-study-skill) |
| AI 读，你查询 | AI | 问答 / 调用 | [deep-reader](https://github.com/tronghieu/agent-skills)、[book-to-skill](https://github.com/weitzu-com/book-to-skill) |
| **AI 读，AI 讲，你靠对话学完** | **AI** | **逐章推进 + 检验** | **本项目** |

deep-study-skill 的 README 第一句就声明它不替代阅读；book-to-skill 系的产物是给
agent 干活时调用的能力，入口不是陪你读。所以第三种模式只能自己拼。

拼法是：**读书这一半不重写，教学这一半自己写。**

## 架构

```
book-companion/
├── HANDOFF.md                  # 接手入口：当前状态、下一步、未决决策
├── framework-gaps.md           # 框架缺口登记（本项目主要产出之一）
├── books/                      # 你的书和工作区放这里（已 gitignore）
├── skills/
│   ├── deep-reader/            # vendored, MIT (tronghieu/agent-skills)
│   │   └── …                   # 阶段一：让 AI 读懂 → 产出书的知识表示
│   └── book-companion/         # 自研
│       ├── SKILL.md            # 阶段二：让你学会 → 产出你的学习状态
│       ├── manifest.json       # 版本、命令、状态机、vendor 依赖声明
│       ├── references/         # 五步循环、阶段一衔接、出题规则、状态字段、反模式
│       ├── scripts/
│       │   ├── companion_router.py   # 状态调度（不产出讲解内容）
│       │   ├── prepare_source.py     # 阶段一转换入口 + CJK 分页 + 缺字审计
│       │   ├── extract_figures.py    # EPUB 提图 + 图号关联
│       │   ├── verify_quotes_cjk.py  # CJK 引文校验（vendor 版对中文失效）
│       │   └── utils/
│       ├── templates/          # 状态文件与导读稿骨架
│       └── tests/              # 自包含回归，不依赖真实书
└── install.sh
```

后三个脚本都是补 vendor 在中文书上的失效位置，原因逐条记在
[framework-gaps.md](framework-gaps.md)。

分工是硬的：deep-reader 产出「书的知识表示」，book-companion 产出「读者的学习状态」，
互不越界。一本书的两类产物同处一个工作区：

```
books/<slug>-notes/
├── source.txt          # 全文 + [[page N]] 坐标系   ← deep-reader
├── chapters.tsv        # 确认后的章节结构，推进顺序的唯一依据
├── chapters/           # 逐章切片
├── map.md              # 全书地图 + 体裁策略 + 精读计划
├── terms.md            # 跨章术语台账（科学类著作最关键的文件）
├── notes/chNN-*.md     # 逐章分析笔记（讲解素材来源）
├── synthesis.md        # 全书综合 + 概念图 + 验证日志
├── figures/            # 从 EPUB 提取的插图 + INDEX.md（含人工核对状态）
└── companion/          #                              ← book-companion
    ├── progress.md     # 每章 pending→briefed→taught→checked→passed
    ├── learner.md      # 你的背景、扎实的点、发虚的点、误解原话
    ├── review.md       # 间隔复习队列 1天→3天→7天→21天
    ├── briefs/         # 每章导读稿 + 预埋检验题
    └── sessions/       # 每次对话的判断记录
```

全是纯 markdown，你可以直接读、手改、git 同步。

## 五步循环

每章走一遍：

```
A 接续   读 progress.md → 报进度 → 到期复习题先清 2-3 道
B 导读   从 notes/ 生成导读稿（含预埋检验题，不给你看）
C 讲解   一个论证单元 → 命题/论证/页码/一个问题 → 停，等你说话
D 检验   检索型问题一次一问 → 答偏给两级提示 → 费曼环节你来讲
E 回流   卡壳点写进 learner.md 和复习队列，更新进度
```

阶段二不读原文，只读 `notes/`。原文仅在你追问细节或需要核对引文时，
沿页码锚点定点回查。

## 状态

**框架验证阶段**（v0.1）。核心流程可用，但规则和脚本接口仍在随实践调整。

它目前只被一本书、一个读者完整验证过（《思考，快与慢》中文版）。那次验证暴露的
十个框架缺口逐条记在 [framework-gaps.md](framework-gaps.md)——其中四个是
vendor 在中文书上的失效位置，修法都是旁路而非改 vendor。

如果你打算用它读书，预期会遇到未被发现的问题。如果你打算基于它改，
先读 [HANDOFF.md](HANDOFF.md)。

## 安装

用软链而非复制，所以改仓库就等于改生效的 skill，不用重装。

```bash
./install.sh --check                      # 先检查依赖，按平台给出安装命令
./install.sh                              # 链到 ~/.claude/skills/
./install.sh --codex                      # 链到 $CODEX_HOME/skills/（默认 ~/.codex/skills/）
./install.sh --target ~/path/to/skills    # 其他 agent 的 skills 目录
```

遵循开放 Agent Skills 标准（`SKILL.md` + YAML frontmatter），理论上任何读这个
格式的 agent 都能加载。**实测只在 Claude Code 上跑过**，其他 host 未验证。

**Python 3.11+** 是唯一的硬依赖。转换工具按你要读的格式二选一：

| 要读的格式 | 需要 | 装法 |
| --- | --- | --- |
| EPUB / DOCX / FB2 / RTF / ODT / HTML | `pandoc` | 见下 |
| PDF | `pdftotext` | `brew install poppler` / `apt install poppler-utils` |
| TXT / Markdown | 无 | — |

先跑 `./install.sh --check`，它会分格式报告缺什么，并区分「没装」和
「装了但不在 PATH」——这两种的修复动作完全不同。

### 装 pandoc

多数平台直接装就行：

```bash
brew install pandoc          # macOS 15+
apt install pandoc           # Debian / Ubuntu
```

**macOS 14 及更早例外。** 这些版本已出 Homebrew 的 bottle 支持窗口（被判
Tier 3），`brew install pandoc` 会退化成 cabal 源码编译，先拉约 2.1G 的 GHC
工具链再编译本体，耗时几十分钟。这种情况用官方预编译包：

```bash
# 把 arm64 换成 x86_64 适配 Intel Mac；版本号见 releases 页面
curl -fsSL -o /tmp/pandoc.zip \
  https://github.com/jgm/pandoc/releases/download/3.12/pandoc-3.12-arm64-macOS.zip
unzip -q -d /tmp /tmp/pandoc.zip
cp /tmp/pandoc-3.12-arm64/bin/pandoc ~/.local/bin/
```

最新版本见 <https://github.com/jgm/pandoc/releases>。
不需要 sudo，删文件即卸载。

**MOBI / AZW 系列不支持**，pandoc 也不支持。先用 Calibre 转：

```bash
ebook-convert 书.mobi 书.epub
```

### 不装会怎样

都不装也能跑 TXT 和 Markdown，但会失去对应格式的处理能力。降级代价见
`skills/book-companion/references/ingest.md`。

## 开始读一本书

把书放进 `books/`，然后跟 agent 说：

```
用 book-companion 陪我读 books/如何阅读一本书.pdf
```

它会先问你三件事（你的领域、相邻已知、想从这本书得到什么），
然后跑阶段一，完成后 `init` 导读工作区，接着开始第一章。

之后每次会话直接说：

| 你说 | 会发生什么 |
| --- | --- |
| 读到哪了 | 报进度、待复习数、仍然发虚的点 |
| 下一章 | 进入下一章的导读和讲解 |
| 继续 | 讲下一个论证单元 |
| 考我 | 当前章检验 |
| 我来讲 | 费曼检验，你讲 AI 找偏差 |
| 卡住了 | 解除答案保护直接讲，但照样记入发虚 |
| 出处 | 回指原文页码 |
| 这本书讲完了吗 | 覆盖度报告 |

## 手动操作状态

正常用不着，agent 会调。需要自己查时：

```bash
cd skills/book-companion
python3 scripts/companion_router.py where  --workspace ../../books/<slug>-notes
python3 scripts/companion_router.py status --workspace ../../books/<slug>-notes
python3 scripts/companion_router.py review list --workspace ../../books/<slug>-notes
```

所有子命令输出 JSON。脚本只管状态读写和调度，不产出讲解内容——
讲解是 agent 读 `notes/` 之后的智力工作，脚本化就会退化成模板套话。

## 测试

```bash
cd skills/book-companion
python3 tests/run_regression.py
```

自包含：在临时目录造一个合成工作区跑全链路，不依赖真实书，不写项目目录。

## 设计取舍

**为什么状态放在 deep-reader 的工作区里而不是独立目录**
一本书的知识和你对这本书的学习状态应该一起搬迁、一起备份。
`companion/` 作为子目录，deep-reader 不碰它，两边互不干扰。

**为什么讲解不脚本化**
把一章 `notes/` 转成能被学会的导读稿需要判断哪些是论证主链、哪些概念该桥接到
读者的背景上。这是智力工作，写成模板就变成了摘要复述——那读者自己读摘要就行。

**为什么达标判据这么严**
`progress.md` 一旦不可信，跨会话机制就废了。宁可进度慢，不要进度假。

**为什么自己写了一个转换入口**
deep-reader 对 EPUB / DOCX / TXT / MD 用 awk 的 `NF` 按空白分词，每 500 词一页。
中文没有空格分词，一整段中文 `NF = 1`，于是「500 词一页」退化成「500 段一页」——
实测 5325 字符的中文 EPUB 被算成 209 words、**1 页**。

页码是整个方法论的坐标系，只有 1 页意味着定点回查、引文校验、`(p. N)` 引用全部失效。
`scripts/prepare_source.py` 做 CJK 感知分页（中文字符与拉丁词各计 1 单位），
同一本书从 1 页变 12 页，且不改动任何原文字符（回归里有字符序列逐一比对）。
PDF 仍委托回 deep-reader，因为 `pdftotext` 用真实 form feed 分页，那条路本来就对。

选择包装而不是改 vendor，是为了让上游 deep-reader 更新时还能直接合并。

## 许可与出处

本项目 **MIT**，见 [LICENSE](LICENSE)。第三方组件与设计借鉴的完整归属见
[NOTICE](NOTICE)。

`skills/deep-reader/` 是 vendored 的外部组件，**未作任何修改**，单独授权：
MIT，来自 [tronghieu/agent-skills](https://github.com/tronghieu/agent-skills)，
版权 Hieu T. Luu，许可全文见 `skills/deep-reader/LICENSE`。
基线 commit 与同步步骤见 [VENDOR.md](VENDOR.md)。

### 自研与复用的边界

代码量上自研约 2700 行 Python（含 73 个回归用例）、1220 行规则文档；
vendor 约 1300 行 shell。但行数不说明分工，实际是三层：

**直接复用 deep-reader 的**（刻意不重写）：多遍读方法论、`[[page N]]` 页码
坐标系、笔记模板、体裁策略、PDF 转换路径、Recite 校验步骤。

**借思路自己实现的**：间隔复习档位 1/3/7/21 天参考
[hammer](https://github.com/SebastianElvis/hammer) 的 `teach` skill；
命令形状参考 [deep-study-skill](https://github.com/orhoncan/deep-study-skill)。

**完全自研的**——项目的实际价值所在：五步循环 A→E 及全套规则、章节状态机与
达标判据、答案保护与两级提示降级、费曼环节、出题规则、12 条反模式清单，
以及四个补中文缺口的工具（CJK 分页、CJK 引文校验、EPUB 提图、静默缺字审计）。

一句话：**读书那一半是别人的，教学那一半是自己的，中文适配是自己补的。**

### 致谢与具体借用

| 借用了什么 | 来自 | 形式 |
| --- | --- | --- |
| 阶段一全部实现：多遍读管线、`[[page N]]` 坐标系、笔记模板、体裁策略、Recite 校验 | [tronghieu/agent-skills](https://github.com/tronghieu/agent-skills) 的 `deep-reader`（MIT） | **vendored 代码**，未修改 |
| 检视阅读、分析阅读、四个基本问题 | Adler《如何阅读一本书》 | 方法论（经 deep-reader 实现） |
| Recite 步骤 | SQ3R 阅读法 | 方法论，公共领域 |
| 论文三遍法 | Keshav, *How to Read a Paper* | 方法论（经 deep-reader 实现） |
| 间隔复习档位 1/3/7/21 天、跨会话持久化学习者状态 | [SebastianElvis/hammer](https://github.com/SebastianElvis/hammer) 的 `teach`（MIT） | **设计思路**，未用其代码 |
| 命令形状（`where` / `next` / `review` 等） | [orhoncan/deep-study-skill](https://github.com/orhoncan/deep-study-skill)（MIT） | **设计思路**，未用其代码 |
| 「检索优于识别」原则 | retrieval practice / testing effect，认知心理学既有结论 | 公共知识 |
| 费曼环节 | 费曼学习法 | 公共知识 |

规则文件内部也各自标了来源：`references/teaching-loop.md` 与
`references/question-design.md` 的开头都有「来源说明」段，区分哪些是自拟的、
哪些是借的。

本项目不包含任何书籍内容。你需要自备你有权阅读的书。
