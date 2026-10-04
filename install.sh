#!/bin/bash
# install.sh [--codex] [--check] [--force]
#
# 把 skills/book-companion 和 skills/deep-reader 软链到 agent 的 skills 目录。
# 用软链而不是复制，这样改这个仓库就等于改生效的 skill，不需要重装。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ROOT="$HOME/.claude/skills"
CHECK_ONLY=false
FORCE=false

while [ $# -gt 0 ]; do
  case "$1" in
    --codex)  TARGET_ROOT="${CODEX_HOME:-$HOME/.codex}/skills" ;;
    --check)  CHECK_ONLY=true ;;
    --force)  FORCE=true ;;
    --target) shift; TARGET_ROOT="${1:?--target 需要一个路径}" ;;
    -h|--help)
      echo "Usage: install.sh [--codex] [--target DIR] [--check] [--force]"
      exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
  shift
done

# ---------- 依赖检查 ----------
#
# 区分三种状态，因为修复动作完全不同：
#   OK    可用
#   PATH  装了但不在当前 PATH —— 改 PATH，别重装
#   MISS  真的没装 —— brew install
SEARCH_PATHS=(
  /opt/homebrew/bin
  /usr/local/bin
  "$HOME/.local/bin"
  /opt/local/bin
  "$HOME/.cabal/bin"
)

probe() {
  local tool="$1" purpose="$2"
  if command -v "$tool" >/dev/null 2>&1; then
    printf '  OK    %-11s %s\n' "$tool" "$purpose"
    return 0
  fi
  local dir
  for dir in "${SEARCH_PATHS[@]}"; do
    if [ -x "$dir/$tool" ]; then
      printf '  PATH  %-11s 已装于 %s 但不在当前 PATH\n' "$tool" "$dir/$tool"
      return 2
    fi
  done
  printf '  MISS  %-11s %s\n' "$tool" "$purpose"
  return 1
}

echo "== 依赖 =="

if command -v python3 >/dev/null 2>&1; then
  printf '  OK    %-11s %s\n' "python3" "$(python3 --version 2>&1 | awk '{print $2}')（必需）"
else
  echo "  FAIL  python3     未安装（必需）" >&2
  exit 1
fi

probe pdftotext "PDF 转文本（poppler）" && have_pdf=ok || have_pdf=$?
probe pandoc "EPUB / DOCX 转文本" && have_pandoc=ok || have_pandoc=$?

echo
echo "== 可读格式 =="
if [ "$have_pdf" = "ok" ]; then
  echo "  PDF            可以（文字版）"
else
  echo "  PDF            不可以 —— 需要 pdftotext"
fi
if [ "$have_pandoc" = "ok" ]; then
  echo "  EPUB / DOCX    可以"
else
  echo "  EPUB / DOCX    不可以 —— 需要 pandoc"
fi
echo "  TXT / MD       可以（无需外部工具，页码为合成页码）"

if [ "$have_pdf" != "ok" ] || [ "$have_pandoc" != "ok" ]; then
  echo
  echo "== 修复 =="

  # 注意：这里必须用 if/fi 而不是 `[ ... ] && echo`。
  # 在 set -e 下，条件为假的 `[ ... ] && cmd` 整体返回 1，会直接终止脚本。
  if [ "$have_pdf" = 1 ]; then
    echo "  pdftotext（PDF 需要）:"
    case "$(uname -s)" in
      Darwin) echo "    brew install poppler" ;;
      Linux)
        if command -v apt >/dev/null 2>&1; then
          echo "    sudo apt install poppler-utils"
        elif command -v dnf >/dev/null 2>&1; then
          echo "    sudo dnf install poppler-utils"
        else
          echo "    用你的包管理器安装 poppler / poppler-utils"
        fi
        ;;
      *) echo "    安装 poppler（提供 pdftotext）" ;;
    esac
  fi

  if [ "$have_pandoc" = 1 ]; then
    echo "  pandoc（EPUB / DOCX / FB2 / RTF / ODT / HTML 需要）:"
    case "$(uname -s)" in
      Darwin)
        macos_major="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"
        if [ -n "$macos_major" ] && [ "$macos_major" -le 14 ] 2>/dev/null; then
          # macOS 14 及更早已出 Homebrew bottle 支持窗口（Tier 3），
          # brew install pandoc 会退化成 cabal 源码编译，先拉约 2.1G 的 GHC 工具链。
          arch_tag="arm64"
          [ "$(uname -m)" = "x86_64" ] && arch_tag="x86_64"
          echo "    检测到 macOS $macos_major —— 这个版本不要用 brew 装 pandoc，"
          echo "    它会退化成 cabal 源码编译（先拉约 2.1G 的 GHC 工具链）。"
          echo "    用官方预编译包（版本号见 releases 页面）:"
          echo "      curl -fsSL -o /tmp/pandoc.zip \\"
          echo "        https://github.com/jgm/pandoc/releases/download/3.12/pandoc-3.12-$arch_tag-macOS.zip"
          echo "      unzip -q -d /tmp /tmp/pandoc.zip && cp /tmp/pandoc-3.12-$arch_tag/bin/pandoc ~/.local/bin/"
        else
          echo "    brew install pandoc"
        fi
        ;;
      Linux)
        if command -v apt >/dev/null 2>&1; then
          echo "    sudo apt install pandoc"
        elif command -v dnf >/dev/null 2>&1; then
          echo "    sudo dnf install pandoc"
        elif command -v pacman >/dev/null 2>&1; then
          echo "    sudo pacman -S pandoc"
        else
          echo "    用你的包管理器安装 pandoc，或见 https://pandoc.org/installing.html"
        fi
        ;;
      *)
        echo "    见 https://pandoc.org/installing.html"
        ;;
    esac
    echo "    MOBI / AZW 不被 pandoc 支持，先用 Calibre: ebook-convert 书.mobi 书.epub"
  fi

  if [ "$have_pdf" = 2 ] || [ "$have_pandoc" = 2 ]; then
    echo "  上面标 PATH 的工具已安装，只是不在当前 PATH——把对应目录加进 PATH 即可，不要重装。"
  fi

  cat <<'EOF'
  缺少的格式走降级：用 Read 工具分批直读，并失去 verify-quotes.sh 的机械引文校验。
  降级代价见 skills/book-companion/references/ingest.md
EOF
fi

if $CHECK_ONLY; then
  echo
  echo "仅检查模式，未安装。"
  exit 0
fi

# ---------- 建链 ----------
echo
echo "== 安装到 $TARGET_ROOT =="
mkdir -p "$TARGET_ROOT"

for skill in book-companion deep-reader; do
  src="$REPO/skills/$skill"
  dst="$TARGET_ROOT/$skill"
  [ -d "$src" ] || { echo "  FAIL  源目录不存在: $src" >&2; exit 1; }

  if [ -L "$dst" ]; then
    existing="$(readlink "$dst")"
    if [ "$existing" = "$src" ]; then
      echo "  SKIP  $skill 已链到本仓库"
      continue
    fi
    if ! $FORCE; then
      echo "  FAIL  $dst 已链到别处 ($existing)，用 --force 覆盖" >&2
      exit 1
    fi
    rm "$dst"
  elif [ -e "$dst" ]; then
    if ! $FORCE; then
      echo "  FAIL  $dst 已存在且不是软链，用 --force 覆盖" >&2
      exit 1
    fi
    rm -rf "$dst"
  fi

  ln -s "$src" "$dst"
  # 回读校验：某些环境下 ln 成功但链不可用
  if [ "$(readlink "$dst")" = "$src" ]; then
    echo "  OK    $skill -> $dst"
  else
    echo "  FAIL  $skill 链接回读失败" >&2
    exit 1
  fi
done

chmod +x "$REPO/skills/deep-reader/scripts/"*.sh 2>/dev/null || true

echo
echo "完成。把书放进 $REPO/books/ ，然后跟 agent 说："
echo "  用 book-companion 陪我读 books/<书名>.epub"
echo
echo "其他 agent 的 skills 目录用 --target 指定，例如："
echo "  ./install.sh --target ~/.config/<agent>/skills"
