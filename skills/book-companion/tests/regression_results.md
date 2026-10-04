# book-companion 回归结果

> 本文件由 `tests/run_regression.py` **每次运行自动重写**，不要手改。

- 运行时间: 2026-10-04T11:55:42
- 通过: 67
- 失败: 0
- 跳过: 0

| 结果 | 用例 | 说明 |
| --- | --- | --- |
| PASS | markdown 表格 round-trip | — |
| PASS | find_section 取正文 | — |
| PASS | replace_section 只改目标区块 | — |
| PASS | 缺分隔行应报错 | — |
| PASS | 列数不匹配应报错 | — |
| PASS | 模板齐全 | 缺少 set() |
| PASS | progress 模板含脚本依赖的三个区块 | — |
| PASS | review 模板含脚本依赖的两个区块 | — |
| PASS | references 齐全 | 缺少 set() |
| PASS | SKILL.md 引用了全部 references | 未被引用 [] |
| PASS | teaching-loop 含会话密度上限规则 | — |
| PASS | teaching-loop 含回答规则声明要求 | — |
| PASS | SKILL.md 硬规则同步了这两条 | — |
| PASS | 导读稿模板提示拆章判断与场景题比例 | — |
| PASS | deep-reader 已 vendor | skills/deep-reader |
| PASS | deep-reader LICENSE 保留 | — |
| PASS | deep-reader 关键脚本齐全 | 缺少 [] |
| PASS | deep-reader 脚本可执行 | 不可执行 [] |
| PASS | measure 计中文字符 | cjk=5 latin=0 |
| PASS | measure 计拉丁词 | cjk=0 latin=3 |
| PASS | measure 处理中英混排 | cjk=4 latin=1 |
| PASS | 锚定上游缺陷：中文段落按空白分词只算 1 词 | NF=1 |
| PASS | CJK 感知计量还原真实体量 | units=640 |
| PASS | 中文分出多页而非 1 页 | pages=10 |
| PASS | 页标记格式匹配 deep-reader 的正则 | markers=10 pages=10 |
| PASS | 页码从 1 连续编号 | 首尾 [1, 2, 3]...[8, 9, 10] |
| PASS | 分页不改动任何原文字符 | 原 2641 vs 后 2641 |
| PASS | 超长单段落被内部切分 | pages=5 |
| PASS | 超长段落切分后字符无损 | 原 2400 vs 后 2400 |
| PASS | prepare 端到端产出多页与 CJK 统计 | {"pages": 10, "cjk_ratio": 0.996, "units": 2640, "pager": "book-companion/CJK 感知"} |
| PASS | 工作区命名与 deep-reader 一致（<书名>-notes） | 中文测试书-notes |
| PASS | prepare 幂等（不重复转换） | — |
| PASS | units-per-page 可调且生效 | upp=900 -> 4 页；upp=500 -> 10 页 |
| PASS | 不支持的格式应报错 | — |
| PASS | EPUB 经 pandoc 后同样多页 | {"pages": 10, "format": "epub"} |
| PASS | PDF 仍委托给 deep-reader（真实分页不能被覆盖） | — |
| PASS | notes/ 为空时阶段一判据不通过 | ['notes/ 下没有逐章笔记'] |
| PASS | init 在阶段一未完成时退出码 3（与 argparse 的 2 区分） | {"ok": false, "reason": "阶段一未完成，不能开始导读", "detail": {"ok": false, "missing": ["notes/ 下没有逐章笔记"], "notes_count": 0, "chapters_count": 3}, "next_action": "回到 deep-reader 跑完 study 模式，见 references/ingest.md"} |
| PASS | 完整工作区判据通过 | {'ok': True, 'missing': [], 'notes_count': 3, 'chapters_count': 3} |
| PASS | init 建立三个状态文件 | {"companion_dir": "/private/var/folders/_w/_d1wp5w10970tky7kg9v4m700000gn/T/book-companion-test-j43gw76i/flow/synthetic-notes/companion", "created": ["progress.md", "learner.md", "review.md"], "skipped": [], "chapters": 3, "ok": true, "book": "合成书"} |
| PASS | init 建立 briefs/ 与 sessions/ | — |
| PASS | init 无缺笔记告警 | — |
| PASS | init 幂等（已存在不覆盖） | {"companion_dir": "/private/var/folders/_w/_d1wp5w10970tky7kg9v4m700000gn/T/book-companion-test-j43gw76i/flow/synthetic-notes/companion", "created": [], "skipped": ["progress.md", "learner.md", "review.md"], "chapters": 3, "ok": true, "book": "合成书"} |
| PASS | where 指向 ch01 | {"id": "ch01", "title": "阅读的活动", "state": "pending"} |
| PASS | next 给出笔记与页码 | {"id": "ch01", "title": "阅读的活动", "state": "pending", "pages": [1, 10]} |
| PASS | mark 推进到 passed 并记录费曼 | {"章节": "ch01", "标题": "阅读的活动", "状态": "passed", "费曼": "已做", "首答正确率": "4/5", "最后动作": "2026-10-04"} |
| PASS | 状态回退需 --allow-regress | ch01 当前是 passed，回退到 taught 需要 --allow-regress |
| PASS | 显式允许后可回退 | — |
| PASS | ch01 达标后 where 指向 ch02 | {"id": "ch02", "title": "阅读的层次", "state": "pending"} |
| PASS | 卡壳摘要写盘 | — |
| PASS | checked 章节不阻塞推进（where 跳过它指向下一个待讲章） | {"id": "ch03", "title": "检视阅读", "state": "pending"} |
| PASS | checked 章节仍出现在 awaiting_recheck 里不被丢失 | [{"id": "ch02", "first_try": "—"}] |
| PASS | next 同样跳过 checked | {"id": "ch03", "title": "检视阅读", "state": "pending", "pages": [21, 30]} |
| PASS | status 覆盖度与未达标清单 | {"ok": true, "total_chapters": 3, "teachable": 3, "no_notes_count": 0, "no_notes": [], "skipped": 0, "passed": 1, "coverage": "1/3", "counts": {"pending": 1, "briefed": 0, "taught": 0, "checked": 1, "passed": 1, "skipped": 0}, "not_passed": [{"id": "ch02", "title": "阅读的层次", "state": "checked"}, {"id": "ch03", "title": "检视阅读", "state": "pending"}], "missing_feynman": ["ch02"], "review_pending": 0, "review_due": 0, "review_graduated": 0, "honest_line": "可讲授 3 单元，达标 1，未达标 2；另有 0 章无笔记（阶段一未覆盖）、0 章已跳过；全书共 3 章。复习队列 0 项"} |
| PASS | status 分母排除无笔记章节 | {"coverage": "1/2", "no_notes": ["ch03"], "total_chapters": 3} |
| PASS | honest_line 区分可讲授与无笔记 | 可讲授 2 单元，达标 1，未达标 1；另有 1 章无笔记（阶段一未覆盖）、0 章已跳过；全书共 3 章。复习队列 0 项 |
| PASS | 入队首档为 1天 | {"点": "检视阅读与略读的区别", "章节": "ch02", "页码": "p. 41", "档位": "1天", "下次到期": "2026-10-05", "连续答对": "0"} |
| PASS | 当天不到期 | {"ok": true, "date": null, "count": 0, "items": [], "take": []} |
| PASS | 次日之后到期 | — |
| PASS | 答对升档到 3天 | {"点": "检视阅读与略读的区别", "章节": "ch02", "页码": "p. 41", "档位": "3天", "下次到期": "2026-10-07", "连续答对": "1"} |
| PASS | 答错退档并把连续答对归零 | {"点": "检视阅读与略读的区别", "章节": "ch02", "页码": "p. 41", "档位": "1天", "下次到期": "2026-10-05", "连续答对": "0"} |
| PASS | 走完 21天档后毕业 | {"点": "检视阅读与略读的区别", "章节": "ch02", "毕业时间": "2026-10-04"} |
| PASS | 给不存在的点评分应报错 | 复习队列里没有 '不存在的点' |
| PASS | 重复入队等于退档处理，不产生重复行 | {"ok": true, "action": "add", "row": {"点": "甲", "章节": "ch03", "页码": "p. 50", "档位": "1天", "下次到期": "2026-10-05", "连续答对": "0"}} |
| PASS | 非法章节状态被拒绝而非静默跳过 | progress.md 中 ch01 的状态 '完事了' 非法，合法取值: pending, briefed, taught, checked, passed, skipped |
| PASS | 缺失区块被拒绝 | 找不到区块「章节状态」 |
| PASS | 恢复后可正常读取 | — |
