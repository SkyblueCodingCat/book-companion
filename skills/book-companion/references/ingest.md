# 阶段一衔接 — 让 AI 真正读懂这本书

阶段一整体委托 vendored 的 `../deep-reader`（tronghieu/agent-skills，MIT）。
本文件只讲两件本 skill 要管的事：**怎么把它跑对**，以及**依赖缺失时怎么降级**。

不要在这一阶段自己另写一套读书流程。deep-reader 的多遍读 + 页码锚定笔记
已经解决了长上下文的 lost-in-the-middle 问题，重写只会退化。

---

## 必须用 study 模式

deep-reader 有 overview 和 study 两个模式。**阶段二只能建立在 study 模式之上。**

overview 模式只产出全书地图和目标导向摘要，不写逐章笔记。没有 `notes/`，
阶段二的讲解就没有素材来源，agent 只能靠模型先验编——直接违反 SKILL.md 第一条硬规则。

读者说"先大概看看"时，可以先跑 overview 给个概览，但要说清：
这不算开始陪读，真要一章章讲完需要回来跑 study。

---

## 阅读目的的转换

deep-reader 的 Step 1 会问"你想从这本书里得到什么"。这个答案有双重用途：

1. 给 deep-reader 决定哪些章精读、哪些略读
2. 给 book-companion 写进 `companion/learner.md` 的「本书阅读目的」

所以问的时候一次问全，顺便把读者的职业/领域和相邻已知也问掉——
这三项是 `learner.md`「背景」区块的内容，也是后面每章「桥接」的唯一素材。
阶段一问了，阶段二就不用再打断读者。

---

## 标准流程

**Step 0 一律走 `scripts/prepare_source.py`，不要直接调 deep-reader 的
`prepare-text.sh`**——原因见下面「中文书的分页陷阱」。它内部会把 PDF 委托回
deep-reader，其余格式走 CJK 感知分页。

```bash
cd skills/book-companion

# Step 0 转换与分页（幂等，同一本书每次会话开头都可以安全重跑）
python3 scripts/prepare_source.py ../../books/<书>.pdf

# Step 2 结构种子 → 人工核对目录 → 写确认后的 chapters.tsv → 切章
bash ../deep-reader/scripts/extract-structure.sh ../../books/<slug>-notes/source.txt
printf 'ch01\t9\t34\t阅读的活动\n' > ../../books/<slug>-notes/chapters.tsv
bash ../deep-reader/scripts/split-chapters.sh \
  ../../books/<slug>-notes/source.txt ../../books/<slug>-notes/chapters.tsv

# Step 3–5 逐章笔记 → 综合 → 引文校验（照 deep-reader 的 SKILL.md 走）
bash ../deep-reader/scripts/verify-quotes.sh ../../books/<slug>-notes
```

`extract-structure.sh` 的输出是**噪声很大的猜测**，不是 ground truth。
必须拿真实目录核对后再写 `chapters.tsv`——这份文件是阶段二推进顺序的唯一依据，
错了会一路错下去。

跑完用机械判据自查：

```bash
python3 scripts/companion_router.py init \
  --workspace ../../books/<slug>-notes --book "书名"
```

`init` 会先校验阶段一判据，不过关就**退出码 3** 并列出缺什么，不会建出半残的工作区。

退出码约定：`0` 成功 / `1` 状态错误 / `2` 参数写错（argparse 产生，输出不是 JSON）/
`3` 阶段一未完成。注意 `3` 和下面 `prepare-text.sh` 自己的 `2` 不是一回事。

---

## 依赖缺失时的降级

`prepare-text.sh` 需要 `pdftotext`（PDF）或 `pandoc`（EPUB/DOCX）。
缺失时它退出码 2。

先装，别急着降级。

**先跑 `./install.sh --check`**，它按当前平台给出具体安装命令，
并区分「没装」和「装了但不在 PATH」——这两种的修复动作完全不同。

多数平台直接装即可：

```bash
brew install poppler pandoc              # macOS 15+
sudo apt install poppler-utils pandoc    # Debian / Ubuntu
```

**macOS 14 及更早对 pandoc 是个已知例外**：这些版本已出 Homebrew 的 bottle
支持窗口（判为 Tier 3），`brew install pandoc` 会退化成 `cabal v2-install`
源码编译，先拉约 2.1G 的 GHC 工具链再编译本体，耗时几十分钟。这种情况改用
官方预编译包（<https://github.com/jgm/pandoc/releases>），解压后把二进制放进
`~/.local/bin` 即可——不需要 sudo，删文件即卸载。

若曾跑过 `brew install pandoc` 并中断，`ghc` 与 `cabal-install` 可能残留约 2.2G
且无人依赖，可用 `brew uninstall ghc cabal-install` 回收。

**MOBI / AZW 系列** pandoc 不支持，需先用 Calibre 的 `ebook-convert` 转成 EPUB。

装不了才降级，代价要说清楚：

- **降级路径**：用 Read 工具分批直接读 PDF/EPUB，人工在笔记里标页码。
- **丢失的能力**：`verify-quotes.sh` 的机械引文校验失效。这个脚本是防编造引文和
  防页码错位的唯一自动手段，失去它意味着**每一条引文都要靠手动回查补偿**。
- **补偿动作**：阶段二每次引用原文前，用 `read-pages.sh`（它不依赖外部工具，
  只读已生成的 `source.txt`）回查一次。降级下宁可少引原文，不要引不确定的原文。

脚本行为可疑时先跑 `bash ../deep-reader/scripts/self-test.sh`，
它能区分是环境问题还是用法问题。

---

## 源文件格式的选择

实测结论（同一份中文内容转成各格式后过管线，对比正文汉字保真度）：

| 格式 | 正文保真 | 章节标题 | 页码 | 工具 | 评价 |
| --- | --- | --- | --- | --- | --- |
| **EPUB** | 100% | 保留 | 合成 | pandoc | **首选**，无需验证 |
| **PDF（规范）** | 100% | 保留 | **真实** | pdftotext | 并列首选，但须抽检 |
| FB2 / DOCX / ODT / RTF / HTML | 100% | 保留 | 合成 | pandoc | 可用，但书源罕见 |
| Markdown | 100% | 保留（`#`） | 合成 | 直读 | 可用 |
| TXT | 100% | **无结构** | 合成 | 直读 | 可用，但章节定位要手工 |
| PDF（字体有问题） | **低至 68%** | 丢失 | 真实 | pdftotext | **静默缺字，最危险** |
| MOBI / AZW / AZW3 | — | — | — | 不支持 | 先用 Calibre 转 EPUB |

几个要点：

**EPUB 优于 PDF，这与直觉相反。** 陪读需要的是干净文本和可靠的章节边界，
而不是与纸书对应的页码——合成页码可验证，定点回查完全够用。EPUB 是结构化
XHTML，不受渲染字体影响；PDF 的提取质量取决于生成方式，方差极大。

**PDF 的分水岭是字体是否正确嵌入。** 实测对比：Chrome 打印生成的中文 PDF
保真 100%；macOS `cupsfilter` 生成的同内容 PDF 只有 68%，丢的是"文""用""子"
"页"这类常用字。失败方式是**静默缺字**——字体缺字形时渲染留空白，提取出来
是空格，句子读着依然通顺，不报错、不留标记。比乱码危险得多。

`prepare_source.py` 已内建审计，输出里的 `quality` 字段给出判定：

```json
"quality": {"cjk_gaps": 281, "gaps_per_1k_cjk": 129.9, "verdict": "可疑：疑似字体缺字，务必抽查原文"}
```

判据是汉字之间不应出现空格。定标：正常样本（EPUB / 规范 PDF / TXT）均在
**1.0/千字**以下，缺字样本为 **129.9/千字**，相差两个数量级。阈值 3 为留意、
10 为可疑。判为可疑时必须抽查原文再决定是否继续，不要直接进精读。

**TXT 的隐性成本是没有结构。** 本项目处理的《思考，快与慢》就是 TXT：38 章
标题必须用正则定位、拿真实目录核对、再用 `--break-before` 对齐边界，中途还踩了
目录区与正文同形导致误匹配的坑。EPUB 省掉这一整步。

**图像：EPUB 可以提取，其余格式会丢。**

`prepare_source.py` 统一转纯文本，图像一律丢失。但 EPUB 本质是 zip，插图原样
躺在里面，用 `scripts/extract_figures.py` 可以取出来并关联图号：

```bash
python3 scripts/extract_figures.py 书.epub ../../books/<slug>-notes
```

它解包 EPUB、遍历 XHTML、在 `<img>` 标签上下文里搜「图N」字样推断图号，
按 `figures/figNN.jpeg` 命名保存，并生成 `figures/INDEX.md`。

**图号关联是启发式的，必须人工核对。** INDEX.md 每条都有 `confidence` 和
`confirmed` 两栏——前者是脚本对图号推断的自信度，**不代表内容正确**。
agent 必须用图像查看工具实际打开每张图，确认后才把 `confirmed` 改为 yes，
并且**只有确认过的图号才能写进笔记**。

这一条不是形式主义。本项目实测：九张图的纯文字重建里**有三张与实际内容不符**
——图 5 的原因项多列了一条、图 6 漏掉了中间一整框（bank 歧义演示）、
图 8 的线段是散乱而非并排。三处都只有打开看才能发现。

**只有 TXT／PDF 时**，图确实无法恢复，此时须在笔记开头用 `>` 块标注
「源文件局限」并用文字重建演示，同时注明重建未经图像核对。
若同一本书能找到 EPUB 版，优先用它补图——本项目就是先用 TXT 做完精读，
后拿到 EPUB 补齐九张图的。

## 中文书的分页陷阱

deep-reader 的 `prepare-text.sh` 对 EPUB / DOCX / TXT / MD 用 awk 的 `NF`
按空白分词，每 500 词一页。**中文没有空格分词**，一整段中文 `NF = 1`，
于是「500 词一页」退化成「500 段一页」。

实测：5325 字符的中文 EPUB 被算成 209 words、**1 页**。

这不是显示问题。页码是整个方法论的坐标系——只有 1 页意味着 `read-pages.sh`
无法定点回查、`verify-quotes.sh` 的页码校验失去意义、阶段二讲解里所有 `(p. N)`
全部指向 p.1。

`scripts/prepare_source.py` 修掉了这一点：CJK 字符各计 1 个单位、拉丁词各计
1 个单位，每页默认 500 单位，切页只发生在安全边界（CJK 字符之后或空白处），
**不改动任何原文字符**（回归里有字符序列逐一比对的用例）。同一本书从 1 页变 12 页。

PDF 不受影响，所以 PDF 仍然委托给 deep-reader——`pdftotext` 用真实的 form feed
分页，那条路本来就是对的。

每页单位数可调：

```bash
python3 scripts/prepare_source.py 书.epub --units-per-page 700
```

中文书每页 500 字偏少于纸书的一页（纸书通常 700–1000 字）。想让页码更接近
纸书观感可以调大，但**同一本书中途不要改**——改了之后已写的笔记页码全部错位。

## 合成页码的含义

EPUB / DOCX / TXT / MD 都没有真实页码，输出里 `synthetic_pages: true`。

影响：笔记里的 `(p. N)` 指向 `source.txt` 自己的分页，**可验证，但和纸书页码不一致**。

处理方式：在 `companion/progress.md` 的元信息里记一行 `页码类型: 合成`，
并在第一次向读者引用页码时说明一次。之后不必每次重复声明。

---

## 已有工作区的复用

同一本书第二次进入时，不要重跑管线。

- `notes/` 已有文件 → 直接进阶段二，走 `companion_router.py where`。
- `companion/` 不存在但 `notes/` 齐全 → 只跑 `init`。
- 只有 `source.txt`，`notes/` 是空的 → 阶段一没跑完，从 Step 2 继续。

`prepare-text.sh` 本身幂等，重跑只会报告已有统计，不会重新转换，所以每次会话
开头调用它来确认工作区状态是安全的。

---

## 大书的 fan-out

deep-reader 支持在 `mode_hint` 标记为 large 时用 subagent 分批读。
用的时候注意它自己的约束：subagent 把 `terms.md` 的行**返回给主 agent 合并**，
不要各自直接写同一个文件（并发写同一文件是 race）。

`map.md`、合并后的 `terms.md`、`synthesis.md` 都由主 agent 掌握，不下放。
本 skill 的 `companion/` 一律由主 agent 写，不交给 subagent。
