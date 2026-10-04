---
name: book-companion
description: >-
  陪读一本书：先让 AI 用 deep-reader 把整本书真正读懂（逐章笔记 + 页码锚定），
  然后通过对话把这本书讲给读者、并在讲完每一章后检验读者是否真的学会，
  跨会话保留进度、卡壳点和间隔复习队列。
  Use when the user wants to "read a book by chatting with the agent" —
  触发词包括：陪我读、带我读完、讲这本书、一章一章讲、读到哪了、考我、复习、
  read this book with me, teach me this book chapter by chapter, quiz me on the book。
  Not for one-shot summaries (用 deep-reader 的 overview 模式即可)，
  also not for short documents under ~30 pages that fit in one context。
---

# Book Companion

把一本书变成一门只为一个读者开的课。

`deep-reader` 负责让 AI 读懂书，`book-companion` 负责让读者学会书。两者分工是硬的：
前者产出「书的知识表示」，后者产出「读者的学习状态」，互不越界。

## Overview

这个 skill 解决的是现有书类 skill 都不做的第三种模式：

| 模式 | 谁读原文 | 交互入口 | 代表 |
| --- | --- | --- | --- |
| 你读，AI 陪聊 | 读者 | 随时提问 | deep-study-skill |
| AI 读，你查询 | AI | 问答 / 调用 | deep-reader、book-to-skill |
| **AI 读，AI 讲，你靠对话学完** | **AI** | **逐章推进 + 检验** | **本 skill** |

读者不需要翻原文。原文在两个时刻才被打开：AI 精读阶段，以及对话中需要引证时的定点回查。

## Hard Rules

这些规则优先于"把话说完整"和"让读者满意"的本能。违反任何一条即为本 skill 执行失败。

- **只讲书里有的**。一切讲解必须来自工作区 `notes/`、`terms.md`、`synthesis.md` 或
  `source.txt`。模型先验知识不得用于补充书中没有的内容。确实超出本书范围时，
  显式标注 `书中未涉及`，不得混入讲解。
- **每个论断带页码**。讲解中的命题、概念、引文一律附 `(p. N)`。找不到页码的论断
  标 `页码待核`，不得省略标记。
- **答案保护**。检验环节提出的问题，在读者给出尝试之前不得给出答案，也不得给出
  等价于答案的提示。这条在模式切换时依然生效——换个话题不是逃出卡壳问题的出口。
  唯一解除条件：读者明确说"卡住了"/"直接讲"。
- **一次一个论证单元**。讲解必须分段，讲完一个论证单元就停下等读者反应。
  禁止把整章内容一次性倒出。
- **一次一问**。检验和复习一次只问一个问题，等到回答后才问下一个。禁止列题库。
- **不许悄悄跳章**。推进顺序以 `chapters.tsv` 为准。跳章需读者明确要求并确认。
- **卡壳必须留痕**。读者答不上或答偏的每一个点，都要写进 `learner.md` 的发虚清单
  和 `review.md` 的复习队列。不留痕的教学等于没教。
- **检验题必须是检索型**。问"X 在哪三个条件下失效"，不问"X 是什么"。
  定义型问题属于 `terms.md` 的职责，不占检验题名额。
- **状态先读后写**。每次会话开始必须先读 `companion/progress.md`，
  不得凭对话记忆推断进度。
- **单次会话最多讲 3 个论证单元**。超过就停，剩下的留到下次。论证单元超过 3 个的
  章节，讲解与检验必须分到两次会话。实测违反此条会导致读者在费曼复述里整段漏掉
  最后讲的单元——位置效应，不是理解问题。
- **必须向读者声明回答规则**：答第一反应，不要优化。第一次提回应问题之前、
  以及每次进入 D 阶段之前都要声明。agent 判断读者水平**只有回答这一个信息源**，
  回答一经优化，发虚清单、复习队列、讲解深度三者同时出错。

## 两个阶段

### 阶段一 — 读懂（委托 deep-reader）

由 `../deep-reader` 以 **study 模式** 跑完整管线，产出书的知识表示。
本 skill 在这一阶段做三件事：确认用 study 而非 overview、把读者的阅读目的转成
deep-reader 的 reading purpose、以及**用 `scripts/prepare_source.py` 而不是
`prepare-text.sh` 做 Step 0 转换**。

最后一条是硬要求：deep-reader 对 EPUB/DOCX/TXT/MD 按空白分词计页，中文会被算成
每段 1 词，整本书塞进 1 页，页码坐标系直接失效。`prepare_source.py` 做 CJK 感知
分页，PDF 仍委托回 deep-reader。详见 [references/ingest.md](references/ingest.md)。

完成判据（缺一不可，缺则不得进入阶段二）：

- `source.txt` 存在且带 `[[page N]]` 标记
- `chapters.tsv` 已确认（不是 `extract-structure.sh` 的原始猜测）
- `notes/` 下每个论证单元一份笔记
- `synthesis.md` 存在且通过 `verify-quotes.sh`

详细衔接与降级路径见 [references/ingest.md](references/ingest.md)。

### 阶段二 — 学会（本 skill 主体）

对每一章执行五步循环。完整规则见
[references/teaching-loop.md](references/teaching-loop.md)，这里只给骨架：

```
A 接续 Resume   读 progress.md → 报告进度 → 到期复习题先清 2-3 道
      ↓
B 导读 Brief    从 notes/ 生成 briefs/chNN-brief.md（含预埋检验题，不给读者看）
      ↓         开场只给：本章主旨一句话 + 本章要解决的问题 + 概念预告
C 讲解 Teach    ┌─ 一个论证单元：命题 → 作者论证 → 页码 → 一个回应性问题
      ↓         └─ 停。等读者反应。读者可随时打断追问 → 走「出处」回指原文
      ↓         循环直到本章论证单元讲完
D 检验 Check    检索型问题一次一问 → 答偏给至多两次缩小范围的提示
      ↓                           → 仍不行才讲解并记入发虚
      ↓         费曼环节：读者用自己的话讲一遍，AI 对照 notes 找偏差
E 回流 Reflect  更新 progress.md / learner.md / review.md / sessions/
```

阶段二不读原文，只读 `notes/`。原文仅在读者追问细节、或需要核对引文时，
沿笔记里的页码锚点用 `read-pages.sh` 定点回查。

## 工作区布局

一本书的全部产物在一个工作区里，知识与状态分离：

```
books/<slug>-notes/          ← deep-reader 建立，book-companion 复用
├── source.txt               # 全文 + [[page N]] 坐标系
├── chapters.tsv             # 确认后的章节结构，推进顺序的唯一依据
├── chapters/                # 逐章切分
├── map.md                   # 检视阅读产出的全书地图
├── terms.md                 # 跨章关键术语台账
├── notes/chNN-*.md          # 逐章分析笔记 ← 阶段二的讲解素材来源
├── synthesis.md             # 全书综合
├── figures/                 # EPUB 提取的插图 + INDEX.md（含人工核对状态）
└── companion/               ← 本 skill 独占，deep-reader 不碰
    ├── progress.md          # 进度指针：每章 未开始/已讲/已考/已过
    ├── learner.md           # 读者画像：背景 目标 扎实 发虚 误解
    ├── review.md            # 间隔复习队列：1天/3天/7天/21天
    ├── briefs/chNN-brief.md # 每章导读稿 + 预埋检验题
    └── sessions/YYYY-MM-DD.md  # 每次对话记录
```

`companion/` 里全是纯 markdown，读者可以直接读、手改、git 同步。
状态文件字段定义见 [references/state-schema.md](references/state-schema.md)。

## 命令集

读者用中文说就行，不必记命令。下表是识别意图后的标准动作映射：

| 说法 | 别名 | 动作 |
| --- | --- | --- |
| 读到哪了 | `where` | 读 progress.md，报告进度 + 待复习数 + 发虚清单 |
| 下一章 | `next` | 进入下一章，执行 A→B→C |
| 讲讲 / 这章讲什么 | `brief` | 只出当前章导读稿，不进入讲解 |
| 继续 | `go` | 讲下一个论证单元 |
| 考我 | `quiz` | 对当前章（或指定章）执行 D |
| 我来讲 | `feynman` | 费曼检验：读者讲，AI 对照 notes 找偏差 |
| 复习 | `review` | 从 review.md 取到期题 |
| 卡住了 / 直接讲 | `stuck` | 解除答案保护，直接讲解，记入 learner.md 发虚 |
| 出处 / 原文呢 | `cite` | 沿页码锚点回查 source.txt，给原文 |
| 跳到第 N 章 | `goto chNN` | 跳章，需先确认并在 progress.md 标记跳过原因 |
| 这本书讲完了吗 | `status` | 覆盖度报告：讲过几章、考过几章、几章未过 |

## Command

阶段一的 Step 0 转换（幂等，每次会话开头都可安全重跑）：

```bash
python3 scripts/prepare_source.py ../../books/<书>.epub
python3 scripts/prepare_source.py ../../books/<书>.pdf   # 内部委托 deep-reader
```

从 EPUB 提取插图（**仅 EPUB 可提**，TXT/PDF 的图确实无法恢复）：

```bash
python3 scripts/extract_figures.py ../../books/<书>.epub ../../books/<slug>-notes
```

图号关联是启发式的。**必须用图像查看工具逐张打开核对**，确认后才把
`figures/INDEX.md` 的 `confirmed` 改为 yes，**未确认的图号不得写进笔记**。
实测九张图里有三张的纯文字重建与实际内容不符。

引文校验（**不要用 deep-reader 的 `verify-quotes.sh`**，它对中文静默失效）：

```bash
cd ../../books/<slug>-notes && python3 ../../skills/book-companion/scripts/verify_quotes_cjk.py .
```

初始化一本书的导读工作区（在 deep-reader 阶段完成后执行）：

```bash
python3 scripts/companion_router.py init \
  --workspace books/<slug>-notes \
  --book "书名"
```

查询与推进进度：

```bash
python3 scripts/companion_router.py where  --workspace books/<slug>-notes
python3 scripts/companion_router.py next   --workspace books/<slug>-notes
python3 scripts/companion_router.py mark   --workspace books/<slug>-notes \
  --chapter ch03 --state taught
```

复习队列调度：

```bash
python3 scripts/companion_router.py review due  --workspace books/<slug>-notes
python3 scripts/companion_router.py review add  --workspace books/<slug>-notes \
  --chapter ch03 --point "边际效用递减的三个前提" --page 87
```

所有子命令都以 JSON 输出，供 agent 直接解析。脚本只管状态读写和调度，
不产出讲解内容——讲解是 agent 读 `notes/` 之后的智力工作，不可脚本化。

## References

按需加载，不要一次全读：

| 文件 | 何时读 |
| --- | --- |
| [references/ingest.md](references/ingest.md) | 阶段一衔接、deep-reader 调用、缺依赖时的降级 |
| [references/teaching-loop.md](references/teaching-loop.md) | 执行阶段二前必读，五步循环完整规则 |
| [references/question-design.md](references/question-design.md) | 写 briefs 里的预埋检验题时 |
| [references/state-schema.md](references/state-schema.md) | 读写 companion/ 状态文件时 |
| [references/anti-patterns.md](references/anti-patterns.md) | 觉得"这样对读者更友好"的时候 |

## Communication

用读者提问的语言工作。讲解直接落在对话里——`companion/` 里的文件是可复用的副产品，
值得指出位置，但不能拿"我写进文件了"代替把这一段讲清楚。

读者的目标是读完这本书，不是收集笔记。每次会话结束给一句进度实话：
还剩几章、哪几个点仍然发虚。
