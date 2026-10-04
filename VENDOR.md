# Vendored 依赖基线

`skills/deep-reader/` 是从外部项目整体拷入的，**未作任何修改**。
本文件记录基线版本与同步步骤——没有这个记录，「包装而不改 vendor，
以便上游更新时还能合并」这个设计取舍就无法兑现。

## deep-reader

| 项 | 值 |
| --- | --- |
| 来源 | https://github.com/tronghieu/agent-skills |
| 子路径 | `skills/deep-reader/` |
| 许可 | MIT，版权 Hieu T. Luu |
| 拷入日期 | 2026-09-29 |
| **基线 commit** | `40cc59c097204457d06a115797324525d47fbd40` |
| 基线查询日期 | 2026-10-04 |
| 本地改动 | **无** |

> 基线 commit 是 2026-10-04 查询上游 `HEAD` 得到的值。拷入日期（09-29）早于
> 查询日期，所以严格说这是「拷入后至查询时点之间上游未变动」的假设下的基线。
> 若日后发现不一致，以 `scripts/` 下八个 shell 脚本的内容比对为准。

### 为什么包装而不改

deep-reader 在中文书上有若干失效位置（见 `framework-gaps.md` 缺口 1–3、7），
但全部通过在 `skills/book-companion/scripts/` 下新增旁路工具解决，
**没有改动 vendor 一行代码**。这样上游更新可以直接覆盖，不必处理冲突。

旁路工具与其对应的 vendor 缺口：

| 旁路工具 | 替代／补充的 vendor 行为 |
| --- | --- |
| `verify_quotes_cjk.py` | `verify-quotes.sh` 的 `normalize()` 删除所有非 ASCII 字符，对中文静默失效 |
| `prepare_source.py` | `prepare-text.sh` 对非 PDF 格式按空白分词计页，中文退化为「500 段一页」 |
| `extract_figures.py` | vendor 管线统一转纯文本，丢弃全部插图 |

PDF 路径仍然委托回 `prepare-text.sh`，因为 `pdftotext` 用真实 form feed 分页，
那条路本来就是对的。

## 同步上游的步骤

```bash
# 1. 确认当前上游 HEAD
git ls-remote https://github.com/tronghieu/agent-skills.git HEAD

# 2. 与本文件记录的基线比较。相同则无需同步

# 3. 取新版本
git clone --depth 1 https://github.com/tronghieu/agent-skills.git /tmp/dr-new

# 4. 先 diff，确认上游改了什么
diff -ru skills/deep-reader /tmp/dr-new/skills/deep-reader

# 5. 覆盖（因为本地无改动，可以直接覆盖）
rm -rf skills/deep-reader
cp -R /tmp/dr-new/skills/deep-reader skills/deep-reader
cp /tmp/dr-new/LICENSE skills/deep-reader/LICENSE
chmod +x skills/deep-reader/scripts/*.sh

# 6. 跑回归，确认旁路工具仍然工作
python3 skills/book-companion/tests/run_regression.py

# 7. 更新本文件的基线 commit 与日期
```

**同步后必须检查的事**：上游是否修复了缺口 1–3。回归里有一条用例专门锚定
缺口 2（断言「中文段落按空白分词只算 1 词」），**如果它失败，说明上游修好了，
对应的旁路工具可以考虑退役**。
