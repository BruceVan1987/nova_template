#!/usr/bin/env python3
"""
网文写作工作区维护脚本。零依赖（只用标准库），不需要 pip install。

子命令：
    new-chapter <卷号> <标题>   在 chapters/drafts/<卷>/ 下创建下一章草稿骨架文件
    confirm-chapter <章号>      把草稿去头（去 frontmatter + 控制卡）生成正稿到 chapters/final/<卷>/，
                                 并把该章 status 改成"已确认"（正稿只能由此命令生成，不要手工复制/编辑）
    wordcount [--write]         统计每章字数（--write 写回草稿 frontmatter 与 chapters/_index.md）
    catalog [--refresh]         构建/检查增量章节元数据缓存
    stats                       从章节元数据快速查看分卷与总进度
    reindex                     重建 characters/worldbuilding/plot/chapters 各 _index.md 表格
    lint                        轻量一致性检查（含"已确认章节的正稿是否存在/是否与草稿同步"）
    compile [--out FILE]        按章节号顺序拼出所有"已确认"章节的正稿为完整稿件
    context ...                 按任务生成可解释、有字符预算的上下文包
    context-audit               检查常驻上下文体积与归档边界
    review-start <章号> --stage overall|language  输出独立冷读正文并开始一轮记录
    review-finish <章号> --stage overall|language 核验本轮记录并绑定正文版本
    review-check <章号>         只读核验两轮记录、版本和问题处置
    ready-chapter <章号>        记录核验及 lint 后置为待审核，不生成正稿

用法示例：
    python3 scripts/story.py new-chapter 1 第一章标题
    python3 scripts/story.py wordcount --write
    python3 scripts/story.py catalog
    python3 scripts/story.py stats
    python3 scripts/story.py lint
    python3 scripts/story.py confirm-chapter 1
    python3 scripts/story.py reindex
    python3 scripts/story.py compile --out manuscript.md
    python3 scripts/story.py context --task review --chapter 1 --focus 主角名
    python3 scripts/story.py context --task direction
    python3 scripts/story.py context --task direction --focus 方向冷人物名
    python3 scripts/story.py context-audit
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIR = ROOT / "chapters"
CHAPTERS_DRAFTS_DIR = CHAPTERS_DIR / "drafts"
CHAPTERS_FINAL_DIR = CHAPTERS_DIR / "final"
CHAPTERS_INDEX_PATH = CHAPTERS_DIR / "_index.md"
CHARACTERS_DIR = ROOT / "characters"
WORLDBUILDING_DIR = ROOT / "worldbuilding"
PLOT_ARCS_DIR = ROOT / "plot" / "arcs"
CHARACTER_PIPELINE_PATH = ROOT / "plot" / "character-pipeline.md"
PROMISES_INDEX = ROOT / "continuity" / "promises" / "_index.md"
STATE_PATH = ROOT / "continuity" / "state.md"
RELATIONSHIPS_PATH = ROOT / "continuity" / "relationships.md"
GEOGRAPHY_PATH = ROOT / "worldbuilding" / "geography.md"
QUESTIONS_INDEX = ROOT / "continuity" / "questions" / "_index.md"
ARCHIVE_DIR = ROOT / "continuity" / "archive"
CHARACTER_ARCHIVE_DIR = ARCHIVE_DIR / "characters"
CONTINUITY_ARCHIVE = ARCHIVE_DIR / "history.md"
PROMISES_ARCHIVE = ARCHIVE_DIR / "promises.md"
QUESTIONS_ARCHIVE = ARCHIVE_DIR / "questions.md"
MIGRATION_MAP = ARCHIVE_DIR / "migration-map.md"
QUALITY_RULES = ROOT / "references" / "style-guide.md"
CONTEXT_CACHE_DIR = ROOT / ".story-cache"
PROJECT_CONFIG_PATH = ROOT / "novel-project.json"
CHAPTER_CATALOG_PATH = CONTEXT_CACHE_DIR / "chapter-catalog-v1.json"
REVIEW_STAGES = ("overall", "language")

DEFAULT_PROJECT_CONFIG = {
    "schema_version": 1,
    "template_version": "1.1.0",
    "mode": "template",
    "context": {
        "default_max_chars": 35000,
        "p2_reserve_plan_chars": 1000,
        "p2_reserve_other_chars": 3000,
        "previous_ending_chars": 1800,
        "voice_sample_chars": 4500,
    },
    "limits": {
        "story_bytes": 10000,
        "state_bytes": 15000,
        "promises_bytes": 10000,
        "questions_bytes": 6000,
        "style_guide_bytes": 12000,
        "core_total_bytes": 50000,
        "character_source_protagonist_bytes": 12000,
        "character_source_other_bytes": 10000,
        "character_hot_protagonist_bytes": 8500,
        "character_hot_other_bytes": 6000,
    },
    "writing": {"target_total_words": 0},
}


def _deep_merge(base, override):
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_project_config():
    """读取项目级配置；缺少新字段时使用兼容默认值。"""
    if not PROJECT_CONFIG_PATH.exists():
        return _deep_merge({}, DEFAULT_PROJECT_CONFIG)
    try:
        supplied = json.loads(PROJECT_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 {PROJECT_CONFIG_PATH.name}: {exc}") from exc
    if not isinstance(supplied, dict):
        raise RuntimeError(f"{PROJECT_CONFIG_PATH.name} 顶层必须是 JSON 对象")
    return _deep_merge(DEFAULT_PROJECT_CONFIG, supplied)


PROJECT_CONFIG = load_project_config()
CONTEXT_CONFIG = PROJECT_CONFIG["context"]
LIMIT_CONFIG = PROJECT_CONFIG["limits"]

CONTEXT_TASKS = ("plan", "write", "revise", "review", "direction")
CONTEXT_PRIORITIES = ("P0", "P1", "P2")
CHARACTER_CONTEXT_SCOPES = {"standard", "direction-only"}
DIRECTION_PIPELINE_SECTION = "方向冷人物候选池"
ACTIVE_PROMISE_STATUSES = {"待回收", "阶段性推进", "长线", "待确认归档"}
ACTIVE_QUESTION_STATUSES = {"未解答", "阶段性推进", "长线", "待确认归档"}

# state.md 的表头可能随项目演进改名。上下文与 lint 同时兼容现行标题和
# 旧版模板标题；否则 Markdown 仍然存在，脚本却会把整张表静默漏掉。
STATE_SECTION_ALIASES = {
    "人物位置、目标与边界": ("人物位置、目标与边界", "人物状态"),
    "活跃物品与文书": ("活跃物品与文书", "活跃物品与资源", "物品状态"),
    "关键知情范围": ("关键知情范围", "知识状态（谁知道什么秘密）"),
}

OPPOSITE_DIRECTION = {
    "东": "西", "西": "东", "南": "北", "北": "南",
    "东南": "西北", "西北": "东南", "东北": "西南", "西南": "东北",
}
DIRECTION_WORDS = ["东南", "东北", "西南", "西北", "东", "南", "西", "北"]

FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n?", re.DOTALL)

# 人工审阅已经明确判定为“不通过”的正文写法。这里只收可稳定机械识别的
# 负面样例；更依赖语境的省略、指代和因果问题仍由 style-guide.md 的五道门检查。
PROSE_STYLE_LINT_RULES = (
    (
        "叙事层级穿帮",
        re.compile(r"(?:第[一二三四五六七八九十百0-9]+章|本章|上一章|下一章)"),
        "正文人物和旁白不能直接读取稿件的章节编号；请改成剧情内的日期、先后或事件",
    ),
    (
        "工作台措辞穿帮",
        re.compile(
            r"(?:本章控制卡|章节控制卡|单元卡|人物弧|情绪落点|信息落点|叙事功能|"
            r"反转节点|节奏点|阶段目标|推进(?:主线|支线|剧情)|关系(?:升级|变化)|"
            r"风险上升|爽点|高光镜头|伏笔(?:回收|埋设)|回收伏笔)"
        ),
        "这是控制卡或章纲语言；请还原为具体人物的动作、信息入口和当场后果",
    ),
    (
        "编辑标记残留",
        re.compile(
            r"(?:【|\[)\s*(?:TODO|待补|待写|待改|此处(?:补|写|扩写)|转场|扩写|删改)"
            r"[^】\]\n]{0,40}(?:】|\])",
            re.IGNORECASE,
        ),
        "正文中遗留了编辑或占位标记；请完成、删除或移回控制卡",
    ),
)

# 下列词语可以出现在人物固定声口、引文或正式文书中，所以不作硬错。
# 只在同一段落高密度出现时提醒人工冷读，避免全局搜索替换误伤历史语域。
PROSE_ARCHAIC_MARKER_RE = re.compile(
    r"(?:少顷|未几|遂|乃|旋即|言罢|闻言|其人|彼时|此番|若非|何故|莫要|休得|未应)"
)
PROSE_ARCHAIC_PARAGRAPH_THRESHOLD = 3
PROSE_ELLIPSIS_WARNING_THRESHOLD = 5
PROSE_SHORT_SENTENCE_MAX_CHARS = 9
PROSE_SHORT_SENTENCE_RUN = 5


# ---------------------------------------------------------------------------
# 极简 frontmatter 解析（YAML 子集：标量 / 行内列表 [a, b] / 块列表 "- x"）
# ---------------------------------------------------------------------------

def split_frontmatter(text):
    """返回 (frontmatter_raw, body)。若无 frontmatter，frontmatter_raw 为 ''。"""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return "", text
    return m.group(1), text[m.end():]


def _parse_scalar(raw):
    raw = raw.strip()
    if raw == "" or raw in ("null", "~"):
        return None
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1]
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def parse_frontmatter(raw):
    """解析 frontmatter 原始文本为 dict。支持标量、[a, b] 行内列表、"- x" 块列表。"""
    data = {}
    lines = raw.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1), m.group(2)
        if value == "":
            # 可能是块列表
            items = []
            j = i + 1
            while j < n and re.match(r"^\s*-\s*(.*)$", lines[j]):
                item_m = re.match(r"^\s*-\s*(.*)$", lines[j])
                items.append(_parse_scalar(item_m.group(1)))
                j += 1
            if items:
                data[key] = items
                i = j
                continue
            data[key] = None
            i += 1
            continue
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [] if not inner else [_parse_scalar(x) for x in inner.split(",")]
        else:
            data[key] = _parse_scalar(value)
        i += 1
    return data


def read_doc(path):
    text = path.read_text(encoding="utf-8")
    raw_fm, body = split_frontmatter(text)
    return parse_frontmatter(raw_fm), body, text


def _story_is_setup():
    """story.md 是否仍处于未初始化状态。

    `novel-project.json` 的 mode 表示工作区用途，不能代替故事合同状态；
    开写门禁只信 story.md frontmatter 中的显式 `status: setup`。
    """
    path = ROOT / "story.md"
    if not path.exists():
        return True
    fm, _, _ = read_doc(path)
    return str(fm.get("status") or "").strip() == "setup"


def _reject_if_story_setup(action):
    if not _story_is_setup():
        return False
    print(
        f"错误：故事尚未初始化（story.md status: setup），不能{action}。"
        "请先与作者确认故事合同，再使用 story-init 完成初始化。",
        file=sys.stderr,
    )
    return True


def _atomic_write_text(path, text):
    """在目标目录写完临时文件后原子替换。

    reindex 会同时重建多份索引；单份索引即使在写入中断时，
    也必须保留旧的完整版本，不得留下半张人物表。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            handle.write(text)
            temp_path = Path(handle.name)
        temp_path.replace(path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


@dataclass
class ContextCandidate:
    priority: str
    label: str
    path: Path
    content: str
    reason: str

    @property
    def size(self):
        return len(self.content)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def iter_entity_files(directory):
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.md")):
        if path.name == "_index.md":
            continue
        yield path


def iter_chapter_files():
    """遍历 chapters/drafts/ 下所有卷文件夹里的章节草稿文件（drafts 是唯一的元数据来源）。"""
    if not CHAPTERS_DRAFTS_DIR.exists():
        return
    for path in sorted(CHAPTERS_DRAFTS_DIR.rglob("*.md")):
        if path.name == "_index.md":
            continue
        yield path


_CN_DIGITS = "零一二三四五六七八九"


def chinese_number(n):
    """把 1-99 的整数转换成中文数字，用于卷文件夹命名（如 1 -> 一，11 -> 十一）。
    超出范围或非整数则原样转字符串兜底，不报错。"""
    if not isinstance(n, int) or n <= 0 or n >= 100:
        return str(n)
    if n < 10:
        return _CN_DIGITS[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + _CN_DIGITS[n - 10]
    if n % 10 == 0:
        return _CN_DIGITS[n // 10] + "十"
    return _CN_DIGITS[n // 10] + "十" + _CN_DIGITS[n % 10]


def volume_folder_name(volume):
    """卷号（frontmatter 里的 volume 字段）-> 卷文件夹名，如 1 -> '卷一'。"""
    if isinstance(volume, int):
        return f"卷{chinese_number(volume)}"
    return f"卷{volume}"


def chapter_filename(chapter, title):
    if isinstance(chapter, int):
        return f"{chapter:04d}-{title}.md"
    return f"{chapter}-{title}.md"


def final_chapter_path(fm):
    """由 frontmatter 推算出这一章"应该"对应的正稿路径（草稿是唯一真相来源，正稿路径是派生的）。"""
    return CHAPTERS_FINAL_DIR / volume_folder_name(fm.get("volume")) / chapter_filename(fm.get("chapter"), fm.get("title", ""))


def extract_final_prose(body):
    """提取用于"正稿"的干净正文：跳过控制卡（第一个 '---' 之前的部分）和 HTML 注释，
    但**保留**章末历史注释——那是写给读者看的内容，不是编辑用的元数据。"""
    lines = body.split("\n")
    first_sep = None
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            first_sep = idx
            break
    prose_lines = lines[first_sep + 1:] if first_sep is not None else lines
    text = "\n".join(prose_lines)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return text.strip()


def build_final_content(fm, body):
    return f"# 第{fm.get('chapter')}章 {fm.get('title', '')}\n\n{extract_final_prose(body)}\n"


def extract_prose_lines(body):
    """从章节 body 中提取正文行：
    - 跳过"章节控制卡"区块，取**第一个** '---' 分隔符之后的内容；
    - 若正文末尾有"章末历史注释"区块（'---' 后紧跟"注："/"注:" 开头的行），予以剔除，
      不计入正文/字数（这个区块是给读者的旁注，不是正文本身）。
    找不到控制卡分隔符则取整个 body。
    """
    lines = body.split("\n")
    first_sep = None
    for idx, line in enumerate(lines):
        if line.strip() == "---":
            first_sep = idx
            break
    prose_lines = lines[first_sep + 1:] if first_sep is not None else lines

    footnote_start = None
    for idx, line in enumerate(prose_lines):
        if line.strip() == "---":
            j = idx + 1
            while j < len(prose_lines) and not prose_lines[j].strip():
                j += 1
            if j < len(prose_lines) and re.match(r"^注[：:]", prose_lines[j].strip()):
                footnote_start = idx
                break
    if footnote_start is not None:
        prose_lines = prose_lines[:footnote_start]

    return prose_lines


def count_prose_words(body):
    """启发式字数统计：提取正文（见 extract_prose_lines），
    再去掉标题行、注释与空白字符后按字符数统计。
    """
    prose_lines = extract_prose_lines(body)
    prose_lines = [l for l in prose_lines if not l.strip().startswith("#")]
    prose_text = "\n".join(prose_lines)
    prose_text = re.sub(r"<!--.*?-->", "", prose_text, flags=re.DOTALL)
    stripped = re.sub(r"\s", "", prose_text)
    return len(stripped)


def find_prose_style_issues(body):
    """返回可机械确认的正文声口问题：(正文行号, 类别, 命中内容, 修改提示)。"""
    issues = []
    for line_no, line in enumerate(extract_prose_lines(body), start=1):
        for category, pattern, advice in PROSE_STYLE_LINT_RULES:
            match = pattern.search(line)
            if match:
                issues.append((line_no, category, match.group(0), advice))
    return issues


def find_prose_style_warnings(body):
    """返回需要语义冷读的正文声口风险。

    这些特征在追逐、窒息、真实迟疑、文书引用或人物固定声口中可能成立，
    因此只作每章汇总的非阻塞提示，不自动替换，也不单词判错。
    """
    prose_lines = extract_prose_lines(body)
    warnings = []

    dense_archaic = []
    for line_no, line in enumerate(prose_lines, start=1):
        matches = [match.group(0) for match in PROSE_ARCHAIC_MARKER_RE.finditer(line)]
        if len(matches) >= PROSE_ARCHAIC_PARAGRAPH_THRESHOLD:
            dense_archaic.append((line_no, matches))
    if dense_archaic:
        total = sum(len(matches) for _, matches in dense_archaic)
        samples = "、".join(
            f"第{line_no}行：{'/'.join(matches[:3])}"
            for line_no, matches in dense_archaic[:3]
        )
        warnings.append((
            dense_archaic[0][0],
            "半文半白密度风险",
            f"{total}处（{samples}）",
            "请核对是否为文书引用或人物固定声口；若不是，把承载古意的句法改回现代白话",
        ))

    ellipses = []
    for line_no, line in enumerate(prose_lines, start=1):
        ellipses.extend((line_no, match.group(0)) for match in re.finditer(r"(?:……|\.{3,})", line))
    if len(ellipses) >= PROSE_ELLIPSIS_WARNING_THRESHOLD:
        sample_lines = "、".join(str(line_no) for line_no, _ in ellipses[:5])
        warnings.append((
            ellipses[0][0],
            "省略号密度风险",
            f"全章{len(ellipses)}处（前五处在第{sample_lines}行）",
            "省略号只保留真正的迟疑、欲言又止或声音消失；中断用破折号，普通停顿用动作或句号",
        ))

    short_run = []
    current_run = []
    for line_no, line in enumerate(prose_lines, start=1):
        for raw_sentence in re.split(r"(?<=[。！？!?])", line):
            sentence = re.sub(r"[\s“”‘’。！？!?]", "", raw_sentence)
            if not sentence:
                continue
            if len(sentence) <= PROSE_SHORT_SENTENCE_MAX_CHARS:
                current_run.append((line_no, sentence))
                if len(current_run) >= PROSE_SHORT_SENTENCE_RUN:
                    short_run = list(current_run)
                    break
            else:
                current_run = []
        if short_run:
            break
        # Markdown 换行不一定等于场景断开，因此连续短句可以跨普通段落计数。
    if short_run:
        sample = " / ".join(sentence for _, sentence in short_run[:5])
        warnings.append((
            short_run[0][0],
            "短句堆叠风险",
            sample,
            "请核对是否为有意加速；若不是，用动作因果、感官变化或转折关系合并部分句子",
        ))

    return warnings


def set_frontmatter_field(text, field, new_value):
    """在 frontmatter 中设置某个标量字段的值（保留其余内容原样）。字段不存在则追加。"""
    raw_fm, body = split_frontmatter(text)
    if not raw_fm:
        return text
    pattern = re.compile(rf"^{re.escape(field)}:.*$", re.MULTILINE)
    new_line = f"{field}: {new_value}"
    if pattern.search(raw_fm):
        new_fm = pattern.sub(new_line, raw_fm, count=1)
    else:
        new_fm = raw_fm.rstrip("\n") + f"\n{new_line}\n"
    return f"---\n{new_fm}---\n{body}"


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_new_chapter(args):
    if _reject_if_story_setup("创建章节草稿"):
        return 2
    volume = int(args.volume) if re.fullmatch(r"-?\d+", args.volume) else args.volume
    title = args.title
    max_chapter = 0
    for chapter in _load_chapters(full=False):
        ch = chapter["fm"].get("chapter")
        if isinstance(ch, int) and ch > max_chapter:
            max_chapter = ch
    next_chapter = max_chapter + 1
    filename = chapter_filename(next_chapter, title)
    out_dir = CHAPTERS_DRAFTS_DIR / volume_folder_name(volume)
    out_path = out_dir / filename
    if out_path.exists():
        print(f"错误：{out_path} 已存在", file=sys.stderr)
        return 1
    content = f"""---
schema-version: 1
chapter: {next_chapter}
volume: {volume}
title: "{title}"
pov: ""
status: draft
word-count: 0
characters: []
locations: []
objects: []
mentions: []
summary: ""
state-changes: []
promises-planted: []
promises-paid: []
---

<!-- 章节控制卡（beat outline），确认通过后保留在此处作为记录 -->
## 本章控制卡

- 普通愿望：
- 物件与动作：
- 阻力／关系卡点：
- 选择与代价：
- 落点：

---

"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"已创建 {out_path.relative_to(ROOT)}")
    return 0


def _read_chapter_catalog():
    if not CHAPTER_CATALOG_PATH.exists():
        return {}
    try:
        payload = json.loads(CHAPTER_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if payload.get("version") != 1 or not isinstance(payload.get("entries"), dict):
        return {}
    return payload["entries"]


def _load_chapters(full=True, refresh=False, with_stats=False):
    """读取章节。

    `full=False` 只读取 frontmatter，并用文件尺寸与纳秒修改时间复用缓存；
    正文在真正需要时由 `_hydrate_chapter` 单章加载。缓存只保存派生元数据，
    删除即可重建，不是事实源。
    """
    chapters = []
    old_entries = {} if full or refresh else _read_chapter_catalog()
    new_entries = {}
    stats = {"total": 0, "reused": 0, "refreshed": 0, "pruned": 0}
    for path in iter_chapter_files():
        stats["total"] += 1
        rel = path.relative_to(ROOT).as_posix()
        if full:
            fm, body, text = read_doc(path)
        else:
            stat = path.stat()
            cached = old_entries.get(rel)
            if (
                cached
                and cached.get("mtime_ns") == stat.st_mtime_ns
                and cached.get("size") == stat.st_size
                and isinstance(cached.get("frontmatter"), dict)
            ):
                fm = cached["frontmatter"]
                stats["reused"] += 1
            else:
                fm, _, _ = read_doc(path)
                stats["refreshed"] += 1
            new_entries[rel] = {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "frontmatter": fm,
            }
            body = text = None
        chapters.append({"path": path, "fm": fm, "body": body, "text": text})
    chapters.sort(key=lambda c: (c["fm"].get("chapter") if isinstance(c["fm"].get("chapter"), int) else 0))
    if not full:
        stats["pruned"] = len(set(old_entries) - set(new_entries))
        payload = {"version": 1, "entries": new_entries}
        _atomic_write_text(
            CHAPTER_CATALOG_PATH,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    return (chapters, stats) if with_stats else chapters


def _hydrate_chapter(chapter):
    """按需为元数据章节补齐正文，避免上下文任务先扫完整章库。"""
    if chapter.get("body") is None or chapter.get("text") is None:
        fm, body, text = read_doc(chapter["path"])
        chapter.update({"fm": fm, "body": body, "text": text})
    return chapter


def cmd_catalog(args):
    _, stats = _load_chapters(full=False, refresh=args.refresh, with_stats=True)
    print(
        "章节目录缓存："
        f"{stats['total']} 章，复用 {stats['reused']}，刷新 {stats['refreshed']}，"
        f"清理 {stats['pruned']}"
    )
    return 0


def cmd_stats(args):
    """用 frontmatter 快速汇总进度；精确字数先运行 `wordcount --write`。"""
    chapters = _load_chapters(full=False)
    total_words = sum(
        c["fm"].get("word-count")
        for c in chapters
        if isinstance(c["fm"].get("word-count"), int)
    )
    confirmed = sum(c["fm"].get("status") == "已确认" for c in chapters)
    drafts = len(chapters) - confirmed
    by_volume = {}
    for chapter in chapters:
        volume = str(chapter["fm"].get("volume") or "未分卷")
        bucket = by_volume.setdefault(volume, {"chapters": 0, "words": 0})
        bucket["chapters"] += 1
        words = chapter["fm"].get("word-count")
        bucket["words"] += words if isinstance(words, int) else 0
    print(f"进度：{len(chapters)} 章（已确认 {confirmed}，未确认 {drafts}），登记字数 {total_words}")
    for volume, bucket in sorted(by_volume.items()):
        print(f"- 卷 {volume}: {bucket['chapters']} 章，{bucket['words']} 字")
    target = PROJECT_CONFIG.get("writing", {}).get("target_total_words") or 0
    if isinstance(target, int) and target > 0:
        percent = min(100.0, total_words / target * 100)
        print(f"- 全书目标: {total_words}/{target}（{percent:.1f}%）")
    print("提示：这是 frontmatter 登记值；需精确刷新时运行 `wordcount --write`。")
    return 0


def cmd_wordcount(args):
    chapters = _load_chapters()
    total = 0
    rows = []
    for c in chapters:
        wc = count_prose_words(c["body"])
        total += wc
        fm = c["fm"]
        if args.write:
            new_text = set_frontmatter_field(c["text"], "word-count", wc)
            if new_text != c["text"]:
                c["path"].write_text(new_text, encoding="utf-8")
            fm["word-count"] = wc
        else:
            fm = dict(fm)
            fm["word-count"] = wc
        rows.append((fm.get("chapter"), fm.get("volume"), fm.get("title", ""), wc, fm.get("status", "")))
        print(f"第{fm.get('chapter')}章《{fm.get('title', '')}》: {wc} 字")
    print(f"合计：{len(chapters)} 章，{total} 字")
    if args.write:
        _write_chapters_index(chapters)
        print("已写回 chapters/_index.md")
    return 0


def _write_chapters_index(chapters):
    lines = [
        "---",
        "schema-version: 1",
        "---",
        "",
        "# 章节登记表",
        "",
        "由 `scripts/story.py reindex` / `wordcount --write` 自动重建。草稿在 `drafts/<卷>/`；"
        "`已确认` 状态的章节会在 `final/<卷>/` 下有对应正稿，正稿只能用 "
        "`scripts/story.py confirm-chapter <章号>` 生成，不要手工复制/编辑。",
        "",
        "| 章号 | 卷 | 标题 | 字数 | 状态 | 摘要 | 草稿文件 |",
        "|---|---|---|---|---|---|---|",
    ]
    if not chapters:
        lines.append("| _(暂无)_ | | | | | | |")
    for c in chapters:
        fm = c["fm"]
        rel = c["path"].relative_to(CHAPTERS_DIR).as_posix()
        lines.append(
            f"| {fm.get('chapter', '')} | {fm.get('volume', '')} | {fm.get('title', '')} | "
            f"{fm.get('word-count', 0)} | {fm.get('status', '')} | {fm.get('summary', '') or ''} | {rel} |"
        )
    lines.append("")
    lines.append("状态取值：`draft`（初稿，正在写/改）/ `待审核`（写完等待确认）/ `已确认`（已用 `confirm-chapter` 生成正稿）。")
    lines.append("")
    _atomic_write_text(CHAPTERS_INDEX_PATH, "\n".join(lines))


# 冷读记录是执行证据，不是故事事实或语义质量判定。流程见
# references/chapter-review-workflow.md；质量仍只由 style-guide.md 定义。
def _review_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _review_prose(chapter):
    return build_final_content(chapter["fm"], chapter["body"])


def _review_dir(chapter):
    return ROOT / ".story-cache" / "reviews" / f"{chapter['fm']['chapter']:04d}"


def _review_target(number):
    matches = [c for c in _load_chapters(full=False) if c["fm"].get("chapter") == number]
    if len(matches) != 1:
        raise ValueError(f"第 {number} 章必须有且只有一份草稿，实际找到 {len(matches)} 份")
    chapter = _hydrate_chapter(matches[0])
    if not extract_final_prose(chapter["body"]):
        raise ValueError("目标章没有正文，不能开始或完成冷读")
    return chapter


def _read_review_record(chapter, create=False):
    path = _review_dir(chapter) / "record.json"
    if not path.exists() and create:
        return {"schema_version": 1, "chapter": chapter["fm"]["chapter"],
                "stages": {}, "findings": [], "history": []}
    if not path.exists():
        raise ValueError("缺少冷读记录；先执行 review-start，不得补写虚构的已完成记录")
    record = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or record.get("schema_version") != 1
            or record.get("chapter") != chapter["fm"]["chapter"]
            or not isinstance(record.get("stages"), dict)
            or not isinstance(record.get("findings"), list)
            or not isinstance(record.get("history"), list)):
        raise ValueError("冷读记录格式或章号错误；保留文件并修复，不得当作缺失记录覆盖")
    return record


def _write_review_record(chapter, record):
    _atomic_write_text(_review_dir(chapter) / "record.json",
                       json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def _review_snapshot(chapter, digest):
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("正文指纹格式错误")
    text = (_review_dir(chapter) / "snapshots" / f"{digest}.md").read_text(encoding="utf-8")
    if _review_hash(text) != digest:
        raise ValueError("正文快照被改动；不得修改原始快照")
    return text


def _review_text(value):
    return isinstance(value, str) and bool(value.strip())


def _review_finding_errors(chapter, record):
    errors = []
    current = _review_prose(chapter)
    for index, finding in enumerate(record["findings"], 1):
        label = f"问题 {index}"
        if not isinstance(finding, dict):
            errors.append(f"{label} 必须是对象")
            continue
        if finding.get("stage") not in REVIEW_STAGES:
            errors.append(f"{label} 缺少有效 stage")
        if not all(_review_text(finding.get(k)) for k in ("quote", "problem")):
            errors.append(f"{label} 缺少原句或问题说明")
            continue
        try:
            source = _review_snapshot(chapter, finding.get("source_sha256"))
            if finding["quote"] not in source:
                errors.append(f"{label} 原句不在指定快照中")
        except (ValueError, OSError) as exc:
            errors.append(f"{label} 原始证据无效：{exc}")
        decision = finding.get("decision")
        if decision not in ("fixed", "retained"):
            errors.append(f"{label} 尚未处置（decision 应为 fixed 或 retained）")
            continue
        if not _review_text(finding.get("reason")):
            errors.append(f"{label} 缺少处置理由")
        if decision == "retained":
            if finding["quote"] not in current:
                errors.append(f"{label} 声明保留的原句已不在当前正文中")
        else:
            replacement = finding.get("replacement")
            if not isinstance(replacement, str):
                errors.append(f"{label} 缺少改句 replacement（删除时填空字符串）")
            elif replacement == finding["quote"]:
                errors.append(f"{label} 改句与原句相同，不能记为已修改")
            elif replacement.strip():
                if replacement not in current:
                    errors.append(f"{label} 改句不在当前正文中，须复核后更新记录")
                elif finding["quote"] in current.replace(replacement, ""):
                    errors.append(f"{label} 改句之外仍有原句；请补足定位上下文，核对是否真正改完")
            elif finding["quote"] in current:
                errors.append(f"{label} 声明删除的原句仍在当前正文中")
    return errors


def _review_receipt(record, stage):
    check = {k: v for k, v in record["stages"][stage].items() if k != "receipt"}
    findings = [f for f in record["findings"] if isinstance(f, dict) and f.get("stage") == stage]
    return _review_hash(json.dumps({"check": check, "findings": findings},
                                   ensure_ascii=False, sort_keys=True))


def _review_stage_errors(chapter, record, stage, completed=True):
    check = record["stages"].get(stage)
    if not isinstance(check, dict):
        return [f"缺少 {stage} 冷读步骤；先执行 review-start --stage {stage}"]
    errors = []
    prose = _review_prose(chapter)
    if check.get("prose_sha256") != _review_hash(prose):
        errors.append(f"{stage} 记录已过期：正文或标题已修改")
    if check.get("rules_sha256") != _review_hash(QUALITY_RULES.read_text(encoding="utf-8")):
        errors.append(f"{stage} 记录已过期：质量规范已修改")
    try:
        _review_snapshot(chapter, check.get("prose_sha256"))
    except (OSError, ValueError) as exc:
        errors.append(f"{stage} 快照无效：{exc}")
    notes = check.get("notes")
    if not isinstance(notes, list) or not notes:
        errors.append(f"{stage} 缺少原句与判断依据；不接受仅勾选完成")
    else:
        for index, note in enumerate(notes, 1):
            if (not isinstance(note, dict)
                    or not all(_review_text(note.get(k)) for k in ("quote", "reason"))):
                errors.append(f"{stage} 读记 {index} 缺少原句或判断理由")
            elif note["quote"] not in prose:
                errors.append(f"{stage} 读记 {index} 的原句不在当前正文中")
    if completed:
        if check.get("status") != "complete":
            errors.append(f"{stage} 尚未完成 review-finish")
        elif check.get("receipt") != _review_receipt(record, stage):
            errors.append(f"{stage} 记录在完成后被修改，须复核并重新 review-finish")
    return errors


def _review_errors(chapter):
    try:
        record = _read_review_record(chapter)
        errors = _review_finding_errors(chapter, record)
        for stage in REVIEW_STAGES:
            errors.extend(_review_stage_errors(chapter, record, stage))
        return errors
    except (OSError, ValueError) as exc:
        return [str(exc)]


def _print_review_errors(errors):
    for error in errors:
        print(f"[冷读记录未就绪] {error}", file=sys.stderr)
    return 1


def _reader_review_target(number):
    """直接定位草稿，不经过会写缓存的章节加载器；其他章节只读 frontmatter。"""
    matches = []
    for path in iter_chapter_files():
        header = []
        with path.open(encoding="utf-8") as source:
            if source.readline().rstrip("\n") == "---":
                for line in source:
                    if line.rstrip("\n") == "---":
                        break
                    header.append(line)
        fm = parse_frontmatter("".join(header))
        filename_number = re.match(r"^(\d+)-", path.name)
        if fm.get("chapter") == number or (
                filename_number and int(filename_number.group(1)) == number):
            matches.append(path)
    if len(matches) != 1:
        raise ValueError(f"第 {number} 章必须有且只有一份草稿，实际找到 {len(matches)} 份")
    fm, body, text = read_doc(matches[0])
    raw_fm, _ = split_frontmatter(text)
    if not raw_fm or fm.get("chapter") != number:
        raise ValueError("目标章 frontmatter 缺失、损坏或章号与文件名不一致")
    keys = []
    for line in raw_fm.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        field = re.match(r"^([A-Za-z0-9_-]+):", line)
        if field:
            keys.append(field.group(1))
        elif not re.match(r"^\s*-\s+", line):
            raise ValueError("目标章 frontmatter 格式损坏，不能导出读者正文")
    if len(keys) != len(set(keys)):
        raise ValueError("目标章 frontmatter 有重复字段，不能导出读者正文")
    if fm.get("status") == "已确认":
        raise ValueError("目标章已确认；请改走修订检查，不使用待审草稿冷读导出")
    if fm.get("status") not in ("draft", "待审核"):
        raise ValueError("review-text 仅用于 status 为 draft 或 待审核 的草稿")
    title = fm.get("title")
    if not isinstance(title, str) or not title.strip() or "<!--" in title or "-->" in title:
        raise ValueError("目标章标题缺失或格式损坏，不能导出读者正文")
    clean_body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    if "<!--" in clean_body or "-->" in clean_body:
        raise ValueError("目标章 HTML 工作注释未闭合或格式损坏，不能导出读者正文")
    lines = clean_body.strip().splitlines()
    if not lines or lines[0].strip() != "## 本章控制卡":
        raise ValueError("目标章缺少合法的本章控制卡区块，不能确定正文边界")
    if not any(line.strip() == "---" for line in lines[1:]):
        raise ValueError("目标章缺少控制卡与正文之间的 --- 分隔，不能导出读者正文")
    prose = extract_final_prose(clean_body)
    if not prose or re.match(r"^注[：:]", prose):
        raise ValueError("目标章没有正文，不能导出读者正文")
    if re.search(r"^\s*## 本章控制卡\s*$", prose, re.MULTILINE):
        raise ValueError("正文分隔后仍有控制卡，章节格式损坏，不能导出读者正文")
    return fm, clean_body


def cmd_review_text(args):
    """给独立读者的纯输出入口；不创建上下文包、缓存、快照或审阅记录。"""
    try:
        fm, body = _reader_review_target(args.chapter)
        print(build_final_content(fm, body), end="")
        return 0
    except (OSError, ValueError) as exc:
        print(f"[读者正文导出失败] {exc}", file=sys.stderr)
        return 1


def cmd_review_start(args):
    try:
        chapter = _review_target(args.chapter)
        record = _read_review_record(chapter, create=True)
        if args.stage == "language":
            errors = _review_stage_errors(chapter, record, "overall")
            errors.extend(_review_finding_errors(chapter, record))
            if errors:
                return _print_review_errors(errors)
        # 重开整体冷读时，后续语言轮也须重新执行。历史及已发现的问题不清空。
        reset = REVIEW_STAGES if args.stage == "overall" else ("language",)
        for stage in reset:
            previous = record["stages"].pop(stage, None)
            if previous is not None:
                record["history"].append({"stage": stage, "check": previous})
        prose = _review_prose(chapter)
        digest = _review_hash(prose)
        snapshot = _review_dir(chapter) / "snapshots" / f"{digest}.md"
        if snapshot.exists():
            _review_snapshot(chapter, digest)
        else:
            _atomic_write_text(snapshot, prose)
        record["stages"][args.stage] = {
            "prose_sha256": digest,
            "rules_sha256": _review_hash(QUALITY_RULES.read_text(encoding="utf-8")),
            "status": "reading", "notes": [],
        }
        _write_review_record(chapter, record)
        print(f"开始 {args.stage} 冷读；以下为完整读者正文，不含控制卡及台账。")
        print(f"快照：{snapshot}")
        print(f"记录：{_review_dir(chapter) / 'record.json'}")
        print("仅填写 notes 和 findings；读完再执行 review-finish。\n")
        print(prose, end="")
        return 0
    except (OSError, ValueError) as exc:
        return _print_review_errors([str(exc)])


def cmd_review_finish(args):
    try:
        chapter = _review_target(args.chapter)
        record = _read_review_record(chapter)
        errors = _review_stage_errors(chapter, record, args.stage, completed=False)
        errors.extend(_review_finding_errors(chapter, record))
        if args.stage == "language":
            errors.extend(_review_stage_errors(chapter, record, "overall"))
        if errors:
            return _print_review_errors(errors)
        record["stages"][args.stage]["status"] = "complete"
        record["stages"][args.stage]["receipt"] = _review_receipt(record, args.stage)
        _write_review_record(chapter, record)
        print(f"{args.stage} 记录已绑定当前正文；这不是语义质量通过证明。")
        return 0
    except (OSError, ValueError) as exc:
        return _print_review_errors([str(exc)])


def cmd_review_check(args):
    try:
        errors = _review_errors(_review_target(args.chapter))
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        return _print_review_errors(errors)
    print("两轮记录与当前正文一致，无未处置问题；不代表语义质量或作者确认。")
    return 0


def cmd_ready_chapter(args):
    if _reject_if_story_setup("交付待审核草稿"):
        return 2
    # 先核对记录，再运行既有机械检查；任何失败均不改章节状态。
    if cmd_review_check(args):
        return 1
    if cmd_lint(args):
        return 1
    try:
        chapter = _review_target(args.chapter)
        errors = _review_errors(chapter)
        if errors:
            return _print_review_errors(errors)
        if chapter["fm"].get("status") not in ("draft", "待审核"):
            raise ValueError("ready-chapter 仅用于未确认草稿，不能把已确认章节降级")
        _atomic_write_text(chapter["path"], set_frontmatter_field(chapter["text"], "status", "待审核"))
        _write_chapters_index(_load_chapters(full=False))
        print(f"第 {args.chapter} 章已置为待审核；未生成正稿。")
        return 0
    except (OSError, ValueError) as exc:
        return _print_review_errors([str(exc)])


def cmd_confirm_chapter(args):
    if _reject_if_story_setup("确认章节或生成正稿"):
        return 2
    target = args.chapter
    chapters = _load_chapters(full=False)
    matches = [c for c in chapters if c["fm"].get("chapter") == target]
    if not matches:
        print(f"错误：chapters/drafts/ 下没有找到第 {target} 章", file=sys.stderr)
        return 1
    if len(matches) > 1:
        paths = ", ".join(str(m["path"].relative_to(ROOT)) for m in matches)
        print(f"错误：第 {target} 章有重复文件（{paths}），请先处理重复再确认", file=sys.stderr)
        return 1

    c = _hydrate_chapter(matches[0])
    fm, body, text = c["fm"], c["body"], c["text"]

    review_errors = _review_errors(c)
    if review_errors:
        return _print_review_errors(review_errors)

    final_path = final_chapter_path(fm)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(build_final_content(fm, body), encoding="utf-8")

    new_text = set_frontmatter_field(text, "status", "已确认")
    if new_text != text:
        c["path"].write_text(new_text, encoding="utf-8")

    _write_chapters_index(_load_chapters(full=False))

    print(f"已生成正稿 {final_path.relative_to(ROOT)}")
    print(f"已将 {c['path'].relative_to(ROOT)} 的 status 改为 已确认")
    return 0


def _write_generic_index(directory, index_path, header_md, columns, row_builder, empty_row):
    entries = []
    for path in iter_entity_files(directory):
        fm, _, _ = read_doc(path)
        entries.append((path, fm))
    lines = header_md.rstrip("\n").split("\n")
    lines.append("")
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")
    if not entries:
        lines.append(empty_row)
    for path, fm in entries:
        lines.append(row_builder(path, fm))
    lines.append("")
    _atomic_write_text(index_path, "\n".join(lines))


def cmd_reindex(args):
    _write_chapters_index(_load_chapters(full=False))
    print("已重建 chapters/_index.md")

    _write_generic_index(
        CHARACTERS_DIR,
        CHARACTERS_DIR / "_index.md",
        "---\nschema-version: 1\n---\n\n# 人物登记表\n\n由 `scripts/story.py reindex` 自动重建，请勿手工维护表格内容。新建人物文件模板见 [`references/entity-templates.md`](../references/entity-templates.md)。",
        ["姓名", "文件", "身份", "首次出场", "状态", "上下文范围"],
        lambda p, fm: f"| {fm.get('name', p.stem)} | {p.name} | {fm.get('role', '')} | {fm.get('first-appearance', '')} | {fm.get('status', '')} | {fm.get('context-scope') or 'standard'} |",
        "| _(暂无)_ | | | | | |",
    )
    print("已重建 characters/_index.md")

    worldbuilding_meta = {
        "locations": (["名称", "文件", "简述"], "地点登记表"),
        "systems": (["名称", "文件", "简述"], "力量体系 / 规则系统登记表"),
        "factions": (["名称", "文件", "立场", "与主角关系"], "势力 / 组织登记表"),
    }
    worldbuilding_rows = {
        "locations": lambda p, fm: f"| {fm.get('name', p.stem)} | {p.name} | |",
        "systems": lambda p, fm: f"| {fm.get('name', p.stem)} | {p.name} | |",
        "factions": lambda p, fm: f"| {fm.get('name', p.stem)} | {p.name} | {fm.get('stance', '')} | |",
    }
    for sub, (cols, title) in worldbuilding_meta.items():
        d = WORLDBUILDING_DIR / sub
        _write_generic_index(
            d,
            d / "_index.md",
            f"---\nschema-version: 1\n---\n\n# {title}\n\n由 `scripts/story.py reindex` 自动重建。新建文件模板见 [`references/entity-templates.md`](../../references/entity-templates.md)。",
            cols,
            worldbuilding_rows[sub],
            "| " + " | ".join(["_(暂无)_"] + [""] * (len(cols) - 1)) + " |",
        )
        print(f"已重建 worldbuilding/{sub}/_index.md")

    _write_generic_index(
        PLOT_ARCS_DIR,
        PLOT_ARCS_DIR / "_index.md",
        "---\nschema-version: 1\n---\n\n# 故事线（Arc）登记表\n\n一条 arc 通常对应一卷或一条贯穿全书的主线/支线。由 `scripts/story.py reindex` 自动重建。新建文件模板见 [`references/entity-templates.md`](../../references/entity-templates.md)。",
        ["名称", "文件", "类型", "状态"],
        lambda p, fm: f"| {fm.get('name', p.stem)} | {p.name} | {fm.get('type', '')} | {fm.get('status', '')} |",
        "| _(暂无)_ | | | |",
    )
    print("已重建 plot/arcs/_index.md")
    return 0


def _parse_table_lines(lines):
    """解析一段行列表里的第一个 markdown 表格，返回 (headers, rows)。"""
    table_lines = [l for l in lines if l.strip().startswith("|")]
    if len(table_lines) < 2:
        return [], []
    headers = [c.strip() for c in table_lines[0].strip("|").split("|")]
    rows = []
    for line in table_lines[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(cells)
    return headers, rows


def _parse_markdown_table(path):
    """解析文件里的第一个 markdown 表格，返回 (headers, rows)。"""
    if not path.exists():
        return [], []
    return _parse_table_lines(path.read_text(encoding="utf-8").split("\n"))


def _extract_section(text, heading):
    """返回 markdown 标题 `heading`（任意 # 级别）下、到下一个同级或更高级标题之前的行列表。"""
    lines = text.split("\n")
    start, level = None, None
    for i, line in enumerate(lines):
        m = re.match(r"^(#+)\s+" + re.escape(heading) + r"\s*$", line.strip())
        if m:
            start, level = i + 1, len(m.group(1))
            break
    if start is None:
        return []
    end = len(lines)
    for j in range(start, len(lines)):
        m2 = re.match(r"^(#+)\s+", lines[j])
        if m2 and len(m2.group(1)) <= level:
            end = j
            break
    return lines[start:end]


def _quality_rules_view(task):
    """按工作阶段读取同一份质量规范。

    开写时只给模型正向的声口、人物关系与叙事发动机，避免把知情审计、
    禁用项和交稿清单提前写成正文里的自证句。改稿与冷读仍读取全文。
    """
    source = QUALITY_RULES.read_text(encoding="utf-8")
    if task != "write":
        return source

    parts = [
        "# 写作质量规范（开写视图）",
        "",
        "> 本视图从同一份 `style-guide.md` 提取，只负责把场景写活。",
        "> 人物事实与知情范围在此阶段静默生效，不要把‘谁不知道什么、什么没有发生、这不代表什么’写进正文。",
        "> 完稿后另用 `context --task review` 载入完整规范做冷读审计。",
    ]
    for heading in ("1. 基本声口", "2. 对话与人物关系", "5. 叙事发动机与节奏"):
        section = _extract_section(source, heading)
        if section:
            parts.extend(["", f"## {heading}", "", *section])
    return "\n".join(parts).strip() + "\n"


def _control_card_view(body):
    """提取草稿控制卡，不把正文或整份卷纲带回 write 包。"""
    marker = "## 本章控制卡"
    if marker not in body:
        return ""
    card = body.split(marker, 1)[1]
    card = card.split("\n---\n", 1)[0].strip()
    return f"# 本章控制卡\n\n{card}\n" if card else ""


def _extract_direction(text):
    for word in DIRECTION_WORDS:
        if word in text:
            return word
    return None


def _chapter_by_number(chapters, number):
    return next((c for c in chapters if c["fm"].get("chapter") == number), None)


def _markdown_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row.get(h, "") for h in headers) + " |")
    return "\n".join(lines)


def _character_context_scope(path):
    fm, _, _ = read_doc(path)
    return fm.get("context-scope") or "standard"


def _character_file_map(context_scope=None):
    result = {}
    for path in iter_entity_files(CHARACTERS_DIR):
        fm, _, _ = read_doc(path)
        scope = fm.get("context-scope") or "standard"
        if context_scope is not None and scope != context_scope:
            continue
        names = [fm.get("name") or path.stem, path.stem] + list(fm.get("aliases") or [])
        for name in names:
            if name:
                result[name] = path
    return result


_CHAPTER_REF_RE = re.compile(r"第(\d+)(?:[—–至-](\d+))?章")
_BARE_CHAPTER_RANGE_RE = re.compile(r"(?<!\d)(\d{4})(?:[—–-](\d{4}))")
_CHARACTER_HISTORY_SECTIONS = {
    "人物关系",
    "当前关系细节",
    "当前认知变化",
    "当前可推进矛盾",
    "当前阶段与旧史",
    "已兑现的恶作剧物资",
    "成长弧光",
    "成长弧光（本卷）",
    "成长弧光（本卷/全书）",
}


def _archived_through():
    if not CONTINUITY_ARCHIVE.exists():
        return 0
    fm, _, _ = read_doc(CONTINUITY_ARCHIVE)
    value = fm.get("archived-through") or 0
    return value if isinstance(value, int) else 0


def _character_cold_profile_info(path):
    """返回人物冷档的 (path, archived_through, issue)。

    有冷档时，热档只能裁掉冷档已明确覆盖的章节。冷档
    元数据不完整时返回 0 作为安全裁剪线，宁可多载，不得在
    全局归档线与人物冷档之间造成静默断层。
    """
    cold_path = CHARACTER_ARCHIVE_DIR / path.name
    if not cold_path.exists():
        return cold_path, None, None
    fm, _, _ = read_doc(cold_path)
    cutoff = fm.get("archived-through")
    if not isinstance(cutoff, int) or cutoff < 0:
        return cold_path, 0, "缺少有效 archived-through"
    source_fm, _, _ = read_doc(path)
    source_name = source_fm.get("name") or path.stem
    cold_name = fm.get("name") or cold_path.stem
    if source_name != cold_name:
        return cold_path, 0, f"人物名不匹配（源档 {source_name}／冷档 {cold_name}）"
    return cold_path, cutoff, None


def _character_hot_cutoff(path, global_cutoff):
    """无冷档时用全局归档线；有冷档时严格用该人物自己的覆盖线。"""
    _, cold_cutoff, _ = _character_cold_profile_info(path)
    return global_cutoff if cold_cutoff is None else cold_cutoff


def _chapter_refs(text):
    refs = []
    for match in _CHAPTER_REF_RE.finditer(text):
        refs.append(int(match.group(1)))
        if match.group(2):
            refs.append(int(match.group(2)))
    for match in _BARE_CHAPTER_RANGE_RE.finditer(text):
        refs.extend((int(match.group(1)), int(match.group(2))))
    return refs


def _character_hot_profile(path, cutoff):
    """生成默认上下文使用的人物热档案。

    源文件仍可保留历史证据，但成长弧光中的逐章复述不进入默认写作包；
    当前事实应由人物档案的当前边界、state 与时间线承载。带姓名的当前
    关系总述会保留；其他历史区段按归档线省略。
    """
    text = path.read_text(encoding="utf-8")
    raw_fm, body = split_frontmatter(text)
    heading = ""
    kept = []
    omitted = 0

    for line in body.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            heading = match.group(1)
            kept.append(line)
            continue

        if heading in {"成长弧光", "成长弧光（本卷）", "成长弧光（本卷/全书）"} and line.strip():
            if line.startswith("总线："):
                kept.append(line)
            else:
                omitted += 1
            continue

        if heading in _CHARACTER_HISTORY_SECTIONS and line.strip():
            refs = _chapter_refs(line)
            if refs and max(refs) <= cutoff:
                named = re.match(r"^- \*\*([^*]+)\*\*", line)
                # 带时地限定的关系条目与无名逐章段落都是阶段证据；
                # 不带限定的基础关系总述仍留在热档案。
                if not named or "（" in named.group(1) or "(" in named.group(1):
                    omitted += 1
                    continue
        kept.append(line)

    while kept and not kept[-1].strip():
        kept.pop()
    if omitted:
        kept.extend([
            "",
            f"> 已省略 {omitted} 条截至第{cutoff}章的逐章关系记录；需要追溯时读取人物冷档案（如已迁移）、人物源文件或章节时间线。",
        ])
    frontmatter = f"---\n{raw_fm}---\n\n" if raw_fm else ""
    return frontmatter + "\n".join(kept).strip() + "\n"


def _character_write_profile(path):
    """生成正文开写用的正向人物卡。

    这里只提供身份、性格、欲望和声口。能力禁区、知情禁区、逐章关系史
    与审阅结论留给成稿后的 review 包，避免人物一出场便替设定自证。
    """
    text = path.read_text(encoding="utf-8")
    raw_fm, body = split_frontmatter(text)
    wanted = (
        "身份与外貌", "身份与经历", "身份", "外貌", "性格", "目标与动机", "说话方式",
    )
    parts = []
    for heading in wanted:
        section = _extract_section(body, heading)
        if section:
            parts.extend([f"## {heading}", *section, ""])
    if not parts:
        parts = body.splitlines()[:24]
    frontmatter = f"---\n{raw_fm}---\n\n" if raw_fm else ""
    return frontmatter + "\n".join(parts).strip() + "\n"


def _worldbuilding_write_view(path):
    """正文开写只取地点的可见环境，不带主线职责与禁写说明。"""
    text = path.read_text(encoding="utf-8")
    raw_fm, body = split_frontmatter(text)
    parts = []
    for heading in ("概况", "环境细节", "环境细节（供正文描写引用，保持前后一致）"):
        section = _extract_section(body, heading)
        if section:
            parts.extend([f"## {heading}", *section, ""])
    if not parts:
        parts = body.splitlines()[:24]
    frontmatter = f"---\n{raw_fm}---\n\n" if raw_fm else ""
    return frontmatter + "\n".join(parts).strip() + "\n"


def _voice_sample(chapters, chapter_number, max_chars=None):
    """从一章已确认正文中截取限长声口样本，不把它当作事实来源。"""
    if chapter_number is None:
        return None, ""
    chapter = _chapter_by_number(chapters, chapter_number)
    if not chapter:
        raise ValueError(f"声口样章不存在：第{chapter_number}章")
    if chapter["fm"].get("status") != "已确认":
        raise ValueError(f"声口样章必须已经确认：第{chapter_number}章")
    _hydrate_chapter(chapter)
    max_chars = max_chars or CONTEXT_CONFIG["voice_sample_chars"]
    prose = extract_final_prose(chapter["body"]).strip()
    if not prose:
        raise ValueError(f"声口样章没有可读取正文：第{chapter_number}章")
    if len(prose) > max_chars:
        prose = prose[:max_chars]
        paragraph = prose.rfind("\n\n")
        if paragraph > max_chars // 2:
            prose = prose[:paragraph]
    title = chapter["fm"].get("title") or chapter["path"].stem
    note = (
        "> 只参照场景发动、叙述密度、对白温度与幽默节奏；"
        "其中人物位置、物品、知识和剧情结果均不是目标章事实。"
    )
    return chapter["path"], f"{note}\n\n## 第{chapter_number}章《{title}》节选\n\n{prose}\n"


def _entity_files_under(directory):
    if not directory.exists():
        return []
    return [p for p in sorted(directory.rglob("*.md")) if p.name != "_index.md"]


def _matching_files(directory, terms):
    matches = []
    for path in _entity_files_under(directory):
        fm, _, _ = read_doc(path)
        identifiers = [path.stem, str(fm.get("name") or "")]
        identifiers.extend(str(x) for x in (fm.get("aliases") or []))
        identifiers.extend(str(x) for x in (fm.get("tags") or []))
        if any(
            term and any(identifier == term or (identifier and identifier in term) for identifier in identifiers)
            for term in terms
        ):
            matches.append(path)
    return matches


def _matching_table(path, terms, label, key_only=False):
    headers, rows = _parse_markdown_table(path)
    if not headers:
        return None
    selected = [
        dict(zip(headers, row))
        for row in rows
        if any(term and term in (row[0] if key_only else " ".join(row)) for term in terms)
    ]
    if not selected:
        return None
    return f"## {label}\n\n{_markdown_table(headers, selected)}\n"


def _section_table(path, heading):
    if not path.exists():
        return [], []
    lines = _extract_section(path.read_text(encoding="utf-8"), heading)
    return _parse_table_lines(lines)


def _current_arc(chapter):
    candidates = []
    for path in iter_entity_files(PLOT_ARCS_DIR):
        fm, _, _ = read_doc(path)
        if fm.get("status") not in ("进行中", "active"):
            continue
        nums = [int(x) for x in re.findall(r"\d+", str(fm.get("chapter-range") or ""))]
        if not nums:
            continue
        start = nums[0]
        end = nums[1] if len(nums) > 1 else 10**9
        if start <= chapter <= end:
            candidates.append((end - start, path))
    return min(candidates, default=(None, None), key=lambda x: x[0])[1]


def _story_core(task=None):
    path = ROOT / "story.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    raw, body = split_frontmatter(text)
    keep = ["# 故事圣经", ""]
    # 开写包只提供“这是什么故事”的核心，不把整份合同和禁写项当成
    # 场景素材。完整边界仍在 plan/revise/review 阶段载入并做事后审计。
    headings = (
        ("一句话简介", "核心冲突", "基调与文风")
        if task == "write"
        else (
            "一句话简介", "世界/时代边界（硬约束）", "历史边界（硬约束）", "主角核心",
            "核心冲突", "人物关系原则", "基调与文风", "禁忌/边界",
        )
    )
    for heading in headings:
        section = _extract_section(body, heading)
        if section:
            keep.extend([f"## {heading}", *section, ""])
    if len(keep) <= 2:
        return text
    return f"---\n{raw}---\n\n" + "\n".join(keep).strip() + "\n"


def _key_matches_terms(key, terms):
    key = str(key or "").strip().strip("`")
    return any(
        term and (key == term or term in key or key in term)
        for term in (str(x).strip().strip("`") for x in terms)
    )


def _state_section_table(text, canonical_heading):
    """按现行／旧版标题读取 state 表，并返回实际标题、表头和行。"""
    for heading in STATE_SECTION_ALIASES[canonical_heading]:
        headers, rows = _parse_table_lines(_extract_section(text, heading))
        if headers:
            return heading, headers, rows
    return None, [], []


def _state_extract(person_terms, object_terms, knowledge_terms, include_all_knowledge=False, write_view=False):
    text = STATE_PATH.read_text(encoding="utf-8") if STATE_PATH.exists() else ""
    parts = []
    section_terms = {
        "人物位置、目标与边界": person_terms,
        "活跃物品与文书": object_terms,
        "关键知情范围": knowledge_terms,
    }
    for heading, terms in section_terms.items():
        _, headers, rows = _state_section_table(text, heading)
        if not headers:
            aliases = "／".join(STATE_SECTION_ALIASES[heading])
            raise ValueError(f"continuity/state.md 缺少可识别的「{aliases}」表，已停止生成上下文")
        # 当前状态按主键召回。人物名或地点名不能因为出现在持有者、备注
        # 或边界说明里，把整张人物／物品／知识表重新捞入。
        alias_idx = headers.index("对应 objects") if heading == "活跃物品与文书" and "对应 objects" in headers else None

        def row_matches(row):
            if _key_matches_terms(row[0], terms):
                return True
            if alias_idx is None:
                return False
            aliases = [x.strip() for x in re.split(r"[、；;]", row[alias_idx]) if x.strip()]
            return any(_key_matches_terms(alias, terms) for alias in aliases)

        picked = [
            dict(zip(headers, row)) for row in rows
            if (include_all_knowledge and heading == "关键知情范围")
            or row_matches(row)
        ]
        if picked:
            output_heading = heading
            output_headers = list(headers)
            if write_view:
                # 开写只看正面事实：人在哪里、物品是什么、谁已经知道什么。
                # “不得越界/边界/不得写成”在冷读时恢复，避免正文先替规则答辩。
                dropped = {"不得越界", "边界", "不得写成"}
                output_headers = [h for h in headers if h not in dropped]
                picked = [{h: row.get(h, "") for h in output_headers} for row in picked]
                output_heading = {
                    "人物位置、目标与边界": "人物位置与当前目标",
                    "关键知情范围": "当前知情事实",
                }.get(heading, heading)
            parts.append(f"## {output_heading}\n\n{_markdown_table(output_headers, picked)}")
    return "\n\n".join(parts) + ("\n" if parts else "")


def _parse_chapter_span(raw):
    """把关系卡中的 0001-0010 / 0011- / 0011 解析为闭区间。"""
    match = re.fullmatch(r"\s*(\d{1,4})(?:\s*([-—–])\s*(\d{1,4})?)?\s*", str(raw or ""))
    if not match:
        return None
    start = int(match.group(1))
    if not match.group(2):
        return start, start
    end = int(match.group(3)) if match.group(3) else 10**9
    if end < start:
        return None
    return start, end


def _relationship_extract(character_names, chapter, character_map, write_view=False):
    """只召回目标人物对在目标章生效的关系声口卡。"""
    headers, rows = _parse_markdown_table(RELATIONSHIPS_PATH)
    required = {"人物A", "人物B", "适用章节"}
    if not headers or not required.issubset(headers):
        return ""

    canonical = set()
    for name in character_names:
        path = character_map.get(str(name))
        canonical.add(path.stem if path else str(name))

    idx_a = headers.index("人物A")
    idx_b = headers.index("人物B")
    idx_span = headers.index("适用章节")
    selected = []
    for row in rows:
        if row[idx_a].strip() not in canonical or row[idx_b].strip() not in canonical:
            continue
        span = _parse_chapter_span(row[idx_span])
        if span and span[0] <= chapter <= span[1]:
            selected.append(dict(zip(headers, row)))
    if not selected:
        return ""
    if write_view:
        output_headers = [h for h in headers if h != "冲突与禁止捷径"]
        selected = [{h: row.get(h, "") for h in output_headers} for row in selected]
        note = "> 以下卡片只提供双方当前称呼、熟悉程度、说话温度和共同经历。"
    else:
        output_headers = headers
        note = (
            "> 以下卡片按人物对和目标章号筛选。它约束双方当时可用的称呼、亲密权限与公开边界；"
            "不能把后续阶段倒灌旧章，也不能把关系类型当作单一好感度。"
        )
    return f"# 关系声口卡\n\n{note}\n\n{_markdown_table(output_headers, selected)}\n"


def _matching_history(terms):
    parts = []
    for heading in ("历史人物", "历史物品", "历史知识边界"):
        headers, rows = _section_table(CONTINUITY_ARCHIVE, heading)
        if not headers:
            continue
        selected = [
            dict(zip(headers, row))
            for row in rows
            if _key_matches_terms(row[0], terms)
        ]
        if selected:
            parts.append(f"## {heading}\n\n{_markdown_table(headers, selected)}")
    return "\n\n".join(parts) + ("\n" if parts else "")


def _recent_summaries(chapters, chapter, count=2):
    rows = [c for c in chapters if isinstance(c["fm"].get("chapter"), int) and c["fm"]["chapter"] < chapter]
    rows = sorted(rows, key=lambda c: c["fm"]["chapter"])[-count:]
    if not rows:
        return ""
    lines = ["## 最近章节摘要", ""]
    for c in rows:
        fm = c["fm"]
        lines.append(f"- 第{fm.get('chapter')}章《{fm.get('title')}》：{fm.get('summary') or '（无摘要）'}")
    return "\n".join(lines) + "\n"


def _recent_ending(chapters, chapter, max_chars=None):
    """保留上一章的收束语气和人物动作。

    摘要只能说明“发生了什么”，不能代替正文中已经建立的情绪、
    称呼和关系强度。只取最后一章、最多数个段落，不回热整章。
    """
    rows = [c for c in chapters if isinstance(c["fm"].get("chapter"), int) and c["fm"]["chapter"] < chapter]
    if not rows:
        return ""
    previous = max(rows, key=lambda c: c["fm"]["chapter"])
    _hydrate_chapter(previous)
    max_chars = max_chars or CONTEXT_CONFIG["previous_ending_chars"]
    prose = extract_final_prose(previous["body"]).strip()
    if not prose:
        return ""
    if len(prose) > max_chars:
        prose = prose[-max_chars:]
        paragraph = prose.find("\n\n")
        if paragraph != -1:
            prose = prose[paragraph + 2:]
    fm = previous["fm"]
    return f"## 第{fm.get('chapter')}章结尾原文\n\n{prose}\n"


def _characters_mentioned_in_text(text, character_map):
    """从当前 arc 中召回已经点名的人物热档。

    这里只识别登记姓名和别名，不根据“皇帝”“护卫”等普通词猜人。
    """
    found = []
    seen_paths = set()
    for identifier, path in sorted(character_map.items(), key=lambda item: len(item[0]), reverse=True):
        if len(identifier) < 2 or identifier not in text or path in seen_paths:
            continue
        seen_paths.add(path)
        found.append(path.stem)
    return found


def _pipeline_extract(character_names, context_text):
    """只载入已点名人物或触发条件真正命中的调度行。"""
    if not CHARACTER_PIPELINE_PATH.exists():
        return ""
    source = CHARACTER_PIPELINE_PATH.read_text(encoding="utf-8")
    parts = [
        "# 角色调度候选（非待办）",
        "",
        "> 下列内容只是候选入口，不要求本章必须推进人物或制造冲突。人物事实以热档和当前状态为准。",
    ]
    matched = False
    for heading in ("待引入人物", "活跃人物待深化", "阶段性人物"):
        headers, rows = _parse_table_lines(_extract_section(source, heading))
        if not headers:
            continue
        name_idx = headers.index("人物") if "人物" in headers else 0
        trigger_indices = [
            headers.index(label)
            for label in ("进入触发", "适合触发")
            if label in headers
        ]
        selected = []
        for row in rows:
            named = row[name_idx] in character_names
            triggered = False
            for idx in trigger_indices:
                chunks = [x.strip() for x in re.split(r"[、，,/／；;]", row[idx]) if len(x.strip()) >= 2]
                if any(chunk in context_text for chunk in chunks):
                    triggered = True
                    break
            if named or triggered:
                selected.append(dict(zip(headers, row)))
        if selected:
            matched = True
            parts.extend(["", f"## {heading}", "", _markdown_table(headers, selected)])
    return "\n".join(parts).strip() + "\n" if matched else ""


def _direction_pipeline_extract():
    """载入方向规划使用的轻量候选卡，不展开任何人物完整档案。"""
    if not CHARACTER_PIPELINE_PATH.exists():
        return ""
    source = CHARACTER_PIPELINE_PATH.read_text(encoding="utf-8")
    headers, rows = _parse_table_lines(_extract_section(source, DIRECTION_PIPELINE_SECTION))
    if not headers:
        return ""
    return "\n".join([
        "# 方向冷人物候选（仅供中长期方向规划）",
        "",
        "> 本表只提供选项与准入门槛，不表示人物已经进入近期章节。选定已有方向冷档的人物后，再用 `--focus <人物>` 读取完整档案。",
        "",
        _markdown_table(headers, [dict(zip(headers, row)) for row in rows]),
        "",
    ])


def _render_context_package(task, chapter, focuses, candidates, targets, max_chars):
    unique, seen = [], set()
    for candidate in candidates:
        key = (candidate.label, str(candidate.path))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)

    required_size = sum(c.size for c in unique if c.priority == "P0")
    if required_size > max_chars:
        raise ValueError(f"P0 必需上下文 {required_size} 字符超过预算 {max_chars}；请提高 --max-chars 或收窄 --focus")

    selected, omitted = [], []
    used = 0
    for priority in CONTEXT_PRIORITIES:
        p2_reserve = (
            CONTEXT_CONFIG["p2_reserve_plan_chars"]
            if task in ("plan", "direction")
            else CONTEXT_CONFIG["p2_reserve_other_chars"]
        )
        priority_limit = (
            max_chars - p2_reserve
            if priority == "P2"
            else max_chars
        )
        for candidate in [c for c in unique if c.priority == priority]:
            if used + candidate.size <= priority_limit:
                selected.append(candidate)
                used += candidate.size
            else:
                omitted.append(candidate)

    chapter_label = f" 第{chapter}章" if chapter is not None else ""
    lines = [
        f"# 任务上下文：{task}{chapter_label}", "",
        f"- 辅助上下文：{used}/{max_chars} 字符",
        f"- 显式焦点：{', '.join(focuses) if focuses else '（无）'}", "",
        "## 纳入清单", "",
    ]
    for candidate in selected:
        rel = candidate.path.relative_to(ROOT)
        lines.append(f"- {candidate.priority} `{rel}` · {candidate.label} · {candidate.size}字符 · {candidate.reason}")
    for candidate in targets:
        rel = candidate.path.relative_to(ROOT)
        lines.append(f"- {candidate.priority} `{rel}` · {candidate.label} · {candidate.size}字符（不计辅助预算） · {candidate.reason}")
    if omitted:
        lines.extend(["", "## 因预算省略", ""])
        for candidate in omitted:
            rel = candidate.path.relative_to(ROOT)
            lines.append(f"- {candidate.priority} `{rel}` · {candidate.label} · {candidate.size}字符 · {candidate.reason}")
    for candidate in selected + targets:
        rel = candidate.path.relative_to(ROOT)
        lines.extend([
            "", "---", "",
            f"# [{candidate.priority}] {candidate.label}", "",
            f"来源：`{rel}`；原因：{candidate.reason}", "",
            candidate.content.rstrip(),
        ])
    return "\n".join(lines).rstrip() + "\n", selected, omitted


def _build_direction_context(chapter, focuses, includes, max_chars):
    if includes:
        raise ValueError("--task direction 不接受 --include；请用 --focus 选择已有方向冷人物")

    candidates = []
    pipeline = _direction_pipeline_extract()
    if pipeline:
        candidates.append(ContextCandidate(
            "P0", "方向冷人物候选", CHARACTER_PIPELINE_PATH, pipeline,
            "方向规划首次只读取轻量候选卡",
        ))

    all_chars = _character_file_map()
    loaded_paths = set()
    notes = []
    for focus in focuses:
        path = all_chars.get(str(focus).strip())
        if path and _character_context_scope(path) == "direction-only":
            if path not in loaded_paths:
                loaded_paths.add(path)
                candidates.append(ContextCandidate(
                    "P0", f"人物：{path.stem}", path,
                    path.read_text(encoding="utf-8"), "方向规划显式选择；完整方向冷档",
                ))
        elif path:
            notes.append(f"- {focus} 当前为 `standard`，不属于方向冷人物；章节任务会按相关性读取其档案。")
        else:
            notes.append(f"- {focus} 只有轻量候选卡或尚未登记人物档；确认长期名额前不展开完整档案。")
    if notes:
        candidates.append(ContextCandidate(
            "P0", "方向焦点提示", CHARACTER_PIPELINE_PATH,
            "# 方向焦点提示\n\n" + "\n".join(notes) + "\n",
            "显式焦点没有可展开的方向冷档",
        ))
    return _render_context_package("direction", chapter, focuses, candidates, [], max_chars)


def _frontmatter_profile_order(fm, character_map):
    """按 POV → characters 原顺序 → mentions 原顺序返回规范人物名。

    集合只用于去重，不参与顺序生成。同一人即使分别以别名和
    规范名写入 frontmatter，也只按第一次出现的位置加载一次。
    """
    ordered = []
    seen_paths = set()
    raw_groups = ([fm.get("pov")], fm.get("characters") or [], fm.get("mentions") or [])
    for group in raw_groups:
        for raw_name in group:
            name = str(raw_name or "").strip()
            path = character_map.get(name)
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            ordered.append(path.stem)
    return ordered


def build_context(task, chapter, focuses=None, includes=None, max_chars=None, voice_chapter=None):
    max_chars = max_chars or CONTEXT_CONFIG["default_max_chars"]
    chapters = _load_chapters(full=False)
    target = _chapter_by_number(chapters, chapter)
    focuses = list(focuses or [])
    includes = list(includes or [])
    if task == "direction":
        return _build_direction_context(chapter, focuses, includes, max_chars)

    all_chars = _character_file_map()
    chars = _character_file_map("standard")
    direction_focus_paths = {
        all_chars[focus]
        for focus in focuses
        if focus in all_chars and _character_context_scope(all_chars[focus]) == "direction-only"
    }
    active_focuses = [
        focus for focus in focuses
        if not (focus in all_chars and _character_context_scope(all_chars[focus]) == "direction-only")
    ]
    active_focus_paths = {
        chars[str(focus).strip()]
        for focus in active_focuses
        if str(focus).strip() in chars
    }
    terms = set(active_focuses)
    character_terms = set()
    object_terms = set()
    location_terms = set()
    mention_terms = set()
    clue_terms = set()
    profile_order = []

    def add_profiles(names):
        for name in names:
            name = str(name or "").strip()
            path = chars.get(name)
            canonical = path.stem if path else ""
            if canonical and canonical not in profile_order:
                profile_order.append(canonical)

    def absorb_frontmatter(fm, include_profiles):
        ordered_profiles = _frontmatter_profile_order(fm, chars)
        characters = set(ordered_profiles)
        objects = {str(x) for x in (fm.get("objects") or []) if x}
        mentions = {
            str(x) for x in (fm.get("mentions") or [])
            if x and (str(x) not in all_chars or str(x) in chars)
        }
        clues = {
            str(x)
            for key in ("promises-planted", "promises-paid")
            for x in (fm.get(key) or [])
            if x
        }
        character_terms.update(characters)
        object_terms.update(objects)
        mention_terms.update(mentions)
        clue_terms.update(clues)
        terms.update(characters | objects | mentions | clues)
        locations = {str(x) for x in (fm.get("locations") or []) if x}
        location_terms.update(locations)
        terms.update(locations)
        if include_profiles:
            add_profiles(ordered_profiles)

    arc = _current_arc(chapter)
    arc_text = arc.read_text(encoding="utf-8") if arc else ""
    arc_characters = _characters_mentioned_in_text(arc_text, chars)
    # 卷纲覆盖数十章，里面点名的人物不等于下一章都会出场。把整卷人物
    # 一律当作热档，会在长篇后期挤掉真正必须承接的上章结尾。显式焦点
    # 与目标／上章人物仍是 P1；仅在卷纲出现的人物降为预算允许时再取。
    character_terms.update(arc_characters)
    terms.update(arc_characters)

    # 历史归档只由显式焦点、物品与线索激活。普通在场人物（尤其主角）
    # 不能自动成为归档关键词，否则长篇后期会重新捞出大量旧案。
    archive_terms = set(active_focuses)
    if target:
        fm = target["fm"]
        absorb_frontmatter(fm, include_profiles=True)
        # mentions 多为“本章顺带提到的人”，不能因此把人物旧史和卷级归档
        # 自动装回热上下文。需要追溯某人的旧关系时，用 --focus 明确召回。
        archive_terms.update(object_terms | clue_terms)
    elif task in ("plan", "write"):
        previous = _chapter_by_number(chapters, chapter - 1)
        if previous:
            fm = previous["fm"]
            # 下一章的人物关系不能只靠上章摘要猜。默认召回热档，
            # 但不因此召回旧卷逐章史。
            absorb_frontmatter(fm, include_profiles=True)
            archive_terms.update(object_terms | clue_terms)
    add_profiles(active_focuses)
    terms.discard("")
    archive_terms.discard("")

    story_label = "故事核心" if task == "write" else "故事硬约束"
    candidates = [ContextCandidate("P0", story_label, ROOT / "story.md", _story_core(task), "所有任务必读")]
    if direction_focus_paths:
        names = "、".join(sorted(path.stem for path in direction_focus_paths))
        candidates.append(ContextCandidate(
            "P0", "方向冷人物提示", CHARACTER_PIPELINE_PATH,
            f"> {names} 当前为 `direction-only`。普通 `{task}` 上下文不展开人物档；"
            "请改用 `context --task direction --focus <人物>` 做方向规划，或经作者确认进入近期三章后先转为 `standard`。\n",
            "普通任务点到方向冷人物时只提示，不展开档案",
        ))
    if (task == "plan" or (not target and task == "write")) and STATE_PATH.exists():
        # state 已是压缩后的当前快照。新章定方向时，秘密边界、物品位置
        # 和分线人物不能受上一章 frontmatter 的偶然名单限制。
        state = STATE_PATH.read_text(encoding="utf-8")
        state_reason = "新章规划需要完整的当前快照与知情边界"
    else:
        state = _state_extract(
            character_terms | mention_terms | set(active_focuses),
            object_terms | set(active_focuses),
            character_terms | object_terms | clue_terms | set(active_focuses),
            include_all_knowledge=task in ("revise", "review"),
            write_view=task == "write",
        )
        state_reason = "人物/物品/知情命中"
        if target and task in ("revise", "review"):
            state_fm, _, _ = read_doc(STATE_PATH)
            state_chapter = state_fm.get("last-updated-chapter")
            if isinstance(state_chapter, int) and state_chapter > chapter:
                state = (
                    f"> 时点警告：这是第{state_chapter}章末的最新快照。修订第{chapter}章时，"
                    "只可据此执行长期边界和“不得越界”；人物当时的位置、伤情、物品状态与知情进度，"
                    "必须以目标正文、时间线和截至该章的归档事实为准，不得从未来倒灌。\n\n"
                    + state
                )
                state_reason += f"；最新快照晚于目标章，仅供边界核验"
    if state:
        candidates.append(ContextCandidate("P0", "当前状态", STATE_PATH, state, state_reason))
    voice_path, voice_text = _voice_sample(chapters, voice_chapter)
    if voice_text:
        candidates.append(ContextCandidate(
            "P0", f"声口样章：第{voice_chapter}章", voice_path, voice_text,
            "显式指定；只作 HOW 参照，不作事实来源",
        ))
    relationship_cards = _relationship_extract(profile_order, chapter, chars, write_view=task == "write")
    if relationship_cards:
        candidates.append(ContextCandidate(
            "P0", "关系声口卡", RELATIONSHIPS_PATH, relationship_cards,
            "直接人物对与目标章阶段命中；防止不同关系写成同一温度",
        ))
    # 台账按本章显式承接的物品／线索召回。人物名可能出现在大量长线条目
    # 中，不能因为本章有人物在场就把整张伏笔表塞回上下文。
    # 若作者确实要按某个台账关键词追溯，可用非人物 --focus 显式点名。
    ledger_focus_terms = {term for term in active_focuses if term not in all_chars}
    ledger_terms = clue_terms | object_terms | ledger_focus_terms
    for path, label in ((PROMISES_INDEX, "活跃伏笔"), (QUESTIONS_INDEX, "活跃悬念")):
        part = _matching_table(path, ledger_terms, label)
        if part:
            candidates.append(ContextCandidate("P0", label, path, part, "显式关键词/章节元数据命中"))

    targets = []
    if target and task in ("revise", "review"):
        _hydrate_chapter(target)
        targets.append(ContextCandidate("TARGET", "目标章节全文", target["path"], target["text"], "目标正文，不计辅助预算"))
    elif target and task == "write":
        _hydrate_chapter(target)
        control_card = _control_card_view(target["body"])
        if control_card:
            candidates.append(ContextCandidate(
                "P0", "目标章正向控制卡", target["path"], control_card,
                "正文开写只读取已确认场景材料，不载入整份卷纲",
            ))

    # 正文质量只有一个事实源。write 包只取其中正向写作段；revise/review
    # 载入全文做事实、知情与去 AI 味审计。这样边界是静默过滤器，不是正文素材。
    if task in ("write", "revise", "review") and QUALITY_RULES.exists():
        candidates.append(ContextCandidate(
            "P1", "写作质量规范", QUALITY_RULES,
            _quality_rules_view(task),
            "开写只载正向写作视图" if task == "write" else "冷读/改稿载入完整规范",
        ))

    if arc and task != "write":
        candidates.append(ContextCandidate("P1", f"当前 arc：{arc.stem}", arc, arc_text, "章号落入进行中最具体 arc"))

    # 已存在目标章的场景地点属于正文直连事实，优先于仅在 mentions 中被
    # 顺带提及的人物。下一章规划仍按预算选地点，避免把上章所有场所倒灌。
    if target and task in ("write", "revise", "review"):
        for path in _matching_files(WORLDBUILDING_DIR, location_terms):
            candidates.append(ContextCandidate(
                "P1", f"设定：{path.stem}", path,
                _worldbuilding_write_view(path) if task == "write" else path.read_text(encoding="utf-8"),
                "目标章节直连地点",
            ))

    # 目标章／上章人物热档要早于调度建议和摘要入包；预算紧时也先保
    # 直接承接人物。卷纲里仅被远期节点点名的人物稍后按 P2 尝试召回。
    archive_cutoff = _archived_through()
    for term in profile_order:
        path = chars.get(term)
        if path:
            cold_path = CHARACTER_ARCHIVE_DIR / path.name
            explicit_focus = path in active_focus_paths
            needs_deep_history = explicit_focus or (
                target
                and task in ("revise", "review")
                and isinstance(target["fm"].get("chapter"), int)
                and target["fm"]["chapter"] <= archive_cutoff
            )
            if task == "write":
                candidates.append(ContextCandidate(
                    "P0" if explicit_focus else "P1", f"人物：{path.stem}", path,
                    _character_write_profile(path),
                    "显式焦点；正向人物卡" if explicit_focus else "上章人物；正向人物卡",
                ))
            elif explicit_focus and not cold_path.exists():
                # --focus 的含义是“本章确实依赖此人”。没有拆出冷档时，直接把
                # 完整人物档升为 P0；不能先塞一份热摘要，再让真正被点名的人物
                # 全档静默掉出预算。
                candidates.append(ContextCandidate(
                    "P0", f"人物：{path.stem}", path,
                    path.read_text(encoding="utf-8"), "显式焦点；完整人物档",
                ))
            else:
                hot_cutoff = _character_hot_cutoff(path, archive_cutoff)
                hot = _character_hot_profile(path, hot_cutoff)
                profile_priority = "P0" if explicit_focus else "P1"
                candidates.append(ContextCandidate(
                    profile_priority, f"人物：{path.stem}", path, hot,
                    "显式焦点；旧章流水已折叠" if explicit_focus
                    else "上章人物/当前 arc 命中；旧章流水已折叠",
                ))

            if task != "write" and needs_deep_history and cold_path.exists():
                candidates.append(ContextCandidate(
                    "P0" if explicit_focus else "P1", f"人物旧史：{path.stem}", cold_path,
                    cold_path.read_text(encoding="utf-8"), "显式人物焦点/旧章修订触发冷档案",
                ))
            elif task != "write" and needs_deep_history and not explicit_focus:
                # 旧章修订仍需要完整旧档；新章显式焦点已在上面直接载入完整档案。
                if not cold_path.exists():
                    candidates.append(ContextCandidate(
                        "P1", f"人物深档：{path.stem}", path,
                        path.read_text(encoding="utf-8"), "尚未迁移冷档案，旧章修订回退全文",
                    ))

    if task == "plan":
        pipeline = _pipeline_extract(set(profile_order) | set(arc_characters), arc_text)
        if pipeline:
            candidates.append(ContextCandidate(
                "P0", "角色调度候选", CHARACTER_PIPELINE_PATH, pipeline,
                "仅保留已点名或触发命中的候选行，不作强制待办",
            ))
    recent = _recent_summaries(chapters, chapter)
    if recent:
        candidates.append(ContextCandidate("P1", "最近两章摘要", CHAPTERS_INDEX_PATH, recent, "直接承接与发动机检查"))
    ending = _recent_ending(chapters, chapter)
    if ending and task in ("plan", "write"):
        previous = max(
            (
                c for c in chapters
                if isinstance(c["fm"].get("chapter"), int) and c["fm"]["chapter"] < chapter
            ),
            default=None,
            key=lambda c: c["fm"]["chapter"],
        )
        candidates.append(ContextCandidate(
            "P0", "上章结尾原文", previous["path"], ending,
            "保留情绪、称呼与关系强度，不用摘要代替正文",
        ))
    if task == "plan":
        direct_profiles = set(profile_order)
        for term in arc_characters:
            if term in direct_profiles:
                continue
            path = chars.get(term)
            if path:
                hot = _character_hot_profile(path, _character_hot_cutoff(path, archive_cutoff))
                candidates.append(ContextCandidate(
                    "P2", f"人物：{path.stem}", path, hot,
                    "仅在当前卷纲远期节点点名；预算允许时补充",
                ))
    for path in _matching_files(WORLDBUILDING_DIR, terms):
        candidates.append(ContextCandidate("P2", f"设定：{path.stem}", path, path.read_text(encoding="utf-8"), "地点/设定关键词命中"))
    for path in (CONTINUITY_ARCHIVE, PROMISES_ARCHIVE, QUESTIONS_ARCHIVE):
        if path == CONTINUITY_ARCHIVE:
            part = _matching_history(archive_terms) if path.exists() else None
        else:
            part = _matching_table(path, archive_terms, path.stem, key_only=True) if path.exists() else None
        if part:
            # 显式人物焦点已经由人物热档／冷档保证。通用历史表可能只是被多个
            # 焦点词宽泛命中，不能反过来挤掉被 --focus 点名的人物本身。
            archive_priority = "P1" if active_focuses else "P2"
            candidates.append(ContextCandidate(archive_priority, f"归档：{path.stem}", path, part, "历史关键词命中"))

    for raw in includes:
        path = Path(raw)
        path = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError:
            raise ValueError(f"--include 只能读取项目内文件：{raw}")
        if not path.is_file():
            raise ValueError(f"--include 文件不存在：{raw}")
        if path.parent == CHARACTERS_DIR and _character_context_scope(path) == "direction-only":
            candidates.append(ContextCandidate(
                "P0", "方向冷人物提示", CHARACTER_PIPELINE_PATH,
                f"> {path.stem} 当前为 `direction-only`。普通 `{task}` 上下文忽略对该档案的 `--include`；"
                "请改用 `context --task direction --focus <人物>`，或先确认转为 `standard`。\n",
                "--include 不能绕过方向冷档边界",
            ))
            continue
        candidates.append(ContextCandidate("P0", f"强制纳入：{path.relative_to(ROOT)}", path, path.read_text(encoding="utf-8"), "--include"))
    return _render_context_package(task, chapter, focuses, candidates, targets, max_chars)


def cmd_context(args):
    chapter = args.chapter
    if chapter is None:
        if args.task != "direction":
            print("错误：除 direction 外，context 任务必须提供 --chapter", file=sys.stderr)
            return 2
    if args.task in ("write", "revise") and _reject_if_story_setup(
        f"生成 {args.task} 上下文包"
    ):
        return 2
    try:
        output, _, _ = build_context(
            args.task, chapter, args.focus, args.include, args.max_chars,
            voice_chapter=args.voice_chapter,
        )
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    if args.out:
        out = Path(args.out)
        out = out.resolve() if out.is_absolute() else (ROOT / out).resolve()
        try:
            out.relative_to(CONTEXT_CACHE_DIR.resolve())
        except ValueError:
            print("错误：--out 必须位于 .story-cache/ 内", file=sys.stderr)
            return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
        print(f"已生成 {out.relative_to(ROOT)}")
    else:
        print(output, end="")
    return 0


def cmd_context_audit(args):
    default_context_limit = CONTEXT_CONFIG["default_max_chars"]
    limits = {
        ROOT / "story.md": LIMIT_CONFIG["story_bytes"],
        STATE_PATH: LIMIT_CONFIG["state_bytes"],
        PROMISES_INDEX: LIMIT_CONFIG["promises_bytes"],
        QUESTIONS_INDEX: LIMIT_CONFIG["questions_bytes"],
        QUALITY_RULES: LIMIT_CONFIG["style_guide_bytes"],
    }
    print("上下文体检")
    total = 0
    failed = False
    for path, limit in limits.items():
        size = len(path.read_bytes()) if path.exists() else 0
        total += size
        status = "OK" if size <= limit else "超标"
        failed |= size > limit
        print(f"- {path.relative_to(ROOT)}: {size}/{limit} 字节 [{status}]")
    core_total_limit = LIMIT_CONFIG["core_total_bytes"]
    total_status = "OK" if total <= core_total_limit else "超标"
    print(f"- 核心常驻包合计: {total}/{core_total_limit} 字节 [{total_status}]")
    failed |= total > core_total_limit

    for path, resolved_words in ((PROMISES_INDEX, ("已回收",)), (QUESTIONS_INDEX, ("已解答",))):
        headers, rows = _parse_markdown_table(path)
        if not headers or "状态" not in headers:
            continue
        status_idx = headers.index("状态")
        bad = [row[0] for row in rows if any(word in row[status_idx] for word in resolved_words)]
        if bad:
            failed = True
            print(f"- {path.relative_to(ROOT)} 活跃表误留已结项: {len(bad)}")

    # 守恒：迁移前的每条记录均被逐项冻结在显式映射中。不能依赖 git HEAD，
    # 否则瘦身提交后基线会随 HEAD 改变，审计反而失去意义。
    migration_headers, migration_rows = _parse_markdown_table(MIGRATION_MAP)
    if not MIGRATION_MAP.exists():
        print("- 台账迁移守恒: 暂无迁移基线 [跳过]")
    elif not migration_headers or not {"类型", "原条目", "主去向", "处理"}.issubset(migration_headers):
        print("- 台账迁移守恒: 映射表字段不完整 [缺项]")
        failed = True
    else:
        type_idx = migration_headers.index("类型")
        name_idx = migration_headers.index("原条目")
        target_idx = migration_headers.index("主去向")
        for kind in ("伏笔", "悬念"):
            entries = [row for row in migration_rows if row[type_idx] == kind]
            expected = len(entries)
            names = [row[name_idx] for row in entries]
            duplicate_count = len(names) - len(set(names))
            active_path = PROMISES_INDEX if kind == "伏笔" else QUESTIONS_INDEX
            archive_path = PROMISES_ARCHIVE if kind == "伏笔" else QUESTIONS_ARCHIVE
            active_headers, active_rows = _parse_markdown_table(active_path)
            archive_headers, archive_rows = _parse_markdown_table(archive_path)
            active_names = {
                row[active_headers.index(kind)] for row in active_rows
            } if active_headers and kind in active_headers else set()
            archive_names = {
                row[archive_headers.index(kind)] for row in archive_rows
            } if archive_headers and kind in archive_headers else set()
            bad_targets = [
                row[name_idx] for row in entries
                if not (
                    (row[target_idx].startswith("活跃：") and row[target_idx][3:] in active_names)
                    or (row[target_idx].startswith("归档：") and row[target_idx][3:] in archive_names)
                )
            ]
            ok = len(entries) == expected and not duplicate_count and not bad_targets
            status = "OK" if ok else "缺项"
            print(f"- {kind}迁移守恒: {len(entries)}/{expected} 条 [{status}]")
            if duplicate_count:
                print(f"  - 重复原条目: {duplicate_count}")
            for name in bad_targets:
                print(f"  - 去向非法：{name}")
            failed |= not ok

    state_text = STATE_PATH.read_text(encoding="utf-8") if STATE_PATH.exists() else ""
    long_rows = [line for line in state_text.splitlines() if line.startswith("|") and len(line) > 420]
    print(f"- state 过长表行(>420): {len(long_rows)}")
    failed |= bool(long_rows)

    oversized_source_profiles = []
    warning_source_profiles = []
    oversized_hot_profiles = []
    warning_hot_profiles = []
    cold_coverage_issues = []
    raw_profile_total = 0
    hot_profile_total = 0
    direction_profile_total = 0
    direction_profile_count = 0
    archive_cutoff = _archived_through()
    source_profile_paths = list(iter_entity_files(CHARACTERS_DIR))
    source_profile_names = {path.name for path in source_profile_paths}
    for path in source_profile_paths:
        size = len(path.read_bytes())
        raw_profile_total += size
        fm, _, _ = read_doc(path)
        limit = (
            LIMIT_CONFIG["character_source_protagonist_bytes"]
            if fm.get("role") in ("主角", "protagonist")
            else LIMIT_CONFIG["character_source_other_bytes"]
        )
        if size > limit:
            oversized_source_profiles.append((path.name, size, limit))
        elif size >= limit * 0.8:
            warning_source_profiles.append((path.name, size, limit))
        _, _, cold_issue = _character_cold_profile_info(path)
        if cold_issue:
            cold_coverage_issues.append((path.name, cold_issue))
        if (fm.get("context-scope") or "standard") == "direction-only":
            direction_profile_count += 1
            direction_profile_total += size
            continue
        hot_cutoff = _character_hot_cutoff(path, archive_cutoff)
        hot_size = len(_character_hot_profile(path, hot_cutoff).encode("utf-8"))
        hot_profile_total += hot_size
        hot_limit = (
            LIMIT_CONFIG["character_hot_protagonist_bytes"]
            if fm.get("role") in ("主角", "protagonist")
            else LIMIT_CONFIG["character_hot_other_bytes"]
        )
        if hot_size > hot_limit:
            oversized_hot_profiles.append((path.name, hot_size, hot_limit))
        elif hot_size >= hot_limit * 0.8:
            warning_hot_profiles.append((path.name, hot_size, hot_limit))
    if CHARACTER_ARCHIVE_DIR.exists():
        for cold_path in iter_entity_files(CHARACTER_ARCHIVE_DIR):
            if cold_path.name not in source_profile_names:
                cold_coverage_issues.append((cold_path.name, "冷档没有对应人物源档"))

    print(f"- 人物源档案合计: {raw_profile_total} 字节")
    print(f"- 过长人物源档案: {len(oversized_source_profiles)}")
    for name, size, limit in oversized_source_profiles:
        print(f"  - {name}: {size}/{limit}")
    failed |= bool(oversized_source_profiles)
    print(f"- 接近上限人物源档案(>=80%): {len(warning_source_profiles)}")
    for name, size, limit in warning_source_profiles:
        print(f"  - {name}: {size}/{limit} [预警]")
    print(f"- 人物热档案合计: {hot_profile_total} 字节（无冷档者使用全局归档线第{archive_cutoff}章）")
    print(f"- 方向冷人物档案: {direction_profile_count} 个／{direction_profile_total} 字节（不计入普通热档）")
    print(f"- 过长人物热档案: {len(oversized_hot_profiles)}")
    for name, size, limit in oversized_hot_profiles:
        print(f"  - {name}: {size}/{limit}")
    failed |= bool(oversized_hot_profiles)
    print(f"- 接近上限人物热档案(>=80%): {len(warning_hot_profiles)}")
    for name, size, limit in warning_hot_profiles:
        print(f"  - {name}: {size}/{limit} [预警]")
    cold_count = len([
        path for path in iter_entity_files(CHARACTER_ARCHIVE_DIR)
        if path.name != "README.md"
    ]) if CHARACTER_ARCHIVE_DIR.exists() else 0
    print(f"- 已迁移人物冷档案: {cold_count}")
    print(f"- 人物冷档覆盖缺口: {len(cold_coverage_issues)}")
    for name, issue in cold_coverage_issues:
        print(f"  - {name}: {issue}")
    failed |= bool(cold_coverage_issues)

    completed = []
    archive_fm, _, _ = read_doc(CONTINUITY_ARCHIVE) if CONTINUITY_ARCHIVE.exists() else ({}, "", "")
    archived_through = archive_fm.get("archived-through") or 0
    for path in iter_entity_files(PLOT_ARCS_DIR):
        fm, _, _ = read_doc(path)
        if fm.get("status") not in ("已完成", "已完结"):
            continue
        nums = [int(x) for x in re.findall(r"\d+", str(fm.get("chapter-range") or ""))]
        if not nums or max(nums) > archived_through:
            completed.append(path.name)
    print(f"- 已完成但尚无历史归档的 arc: {len(completed)}")
    failed |= bool(completed)

    max_chapter = max((c["fm"].get("chapter") or 0 for c in _load_chapters(full=False)), default=0)
    try:
        chapters = _load_chapters(full=False)
        _, selected, omitted = build_context("plan", max_chapter + 1, [], [], default_context_limit)
        estimate = sum(candidate.size for candidate in selected)
        previous = _chapter_by_number(chapters, max_chapter)
        chars = _character_file_map("standard")
        expected_profiles = set()
        if previous:
            for name in (previous["fm"].get("characters") or []) + (previous["fm"].get("mentions") or []):
                path = chars.get(str(name))
                if path:
                    expected_profiles.add(path.stem)
        selected_profiles = {
            candidate.path.stem for candidate in selected if candidate.label.startswith("人物：")
        }
        missing_profiles = sorted(expected_profiles - selected_profiles)
        has_state = any(candidate.label == "当前状态" for candidate in selected)
        has_ending = not previous or any(candidate.label == "上章结尾原文" for candidate in selected)
        omitted_direct_profiles = [
            candidate.path.stem for candidate in omitted
            if candidate.label.startswith("人物：") and candidate.path.stem in expected_profiles
        ]
        complete = not missing_profiles and has_state and has_ending and not omitted_direct_profiles
        status = "OK" if estimate <= default_context_limit and complete else "缺项"
        print(f"- 默认下一章计划包: {estimate}/{default_context_limit} 字符 [{status}]")
        if missing_profiles:
            print(f"  - 缺少上章人物热档: {'、'.join(missing_profiles)}")
        if omitted_direct_profiles:
            print(f"  - 预算省略上章人物热档: {'、'.join(omitted_direct_profiles)}")
        if not has_state:
            print("  - 缺少完整当前状态/知情边界")
        if not has_ending:
            print("  - 缺少上章结尾原文")
        failed |= estimate > default_context_limit or not complete
    except ValueError as exc:
        print(f"- 默认上下文包: 失败（{exc}）")
        failed = True

    latest = _chapter_by_number(_load_chapters(full=False), max_chapter) if max_chapter else None
    if latest:
        try:
            _, selected, omitted = build_context("write", max_chapter, [], [], default_context_limit)
            estimate = sum(candidate.size for candidate in selected)
            direct_characters = {str(x) for x in (latest["fm"].get("characters") or [])}
            direct_locations = {str(x) for x in (latest["fm"].get("locations") or [])}
            omitted_direct = [
                candidate
                for candidate in omitted
                if (
                    candidate.label.startswith("人物：") and candidate.path.stem in direct_characters
                ) or (
                    candidate.label.startswith("设定：") and candidate.path.stem in direct_locations
                )
            ]
            has_state = any(candidate.label == "当前状态" for candidate in selected)
            has_quality_rules = sum(candidate.label == "写作质量规范" for candidate in selected) == 1
            status = "OK" if estimate <= default_context_limit and has_state and has_quality_rules and not omitted_direct else "缺项"
            print(f"- 最近章写作包: {estimate}/{default_context_limit} 字符 [{status}]")
            if omitted_direct:
                names = "、".join(candidate.path.stem for candidate in omitted_direct)
                print(f"  - 省略章节直连资料: {names}")
            if not has_state:
                print("  - 缺少当前状态/完整知情边界")
            if not has_quality_rules:
                print("  - 写作质量规范未且仅未载入一次")
            failed |= estimate > default_context_limit or not has_state or not has_quality_rules or bool(omitted_direct)
        except ValueError as exc:
            print(f"- 最近章写作包: 失败（{exc}）")
            failed = True

        for task in ("revise", "review"):
            try:
                _, selected, _ = build_context(task, max_chapter, [], [], default_context_limit)
                has_state = any(candidate.label == "当前状态" for candidate in selected)
                has_quality_rules = sum(candidate.label == "写作质量规范" for candidate in selected) == 1
                status = "OK" if has_state and has_quality_rules else "缺项"
                print(f"- 最近章{task}包当前状态: [{status}]")
                if not has_state:
                    print("  - 缺少当前状态/完整知情边界")
                if not has_quality_rules:
                    print("  - 写作质量规范未且仅未载入一次")
                failed |= not has_state or not has_quality_rules
            except ValueError as exc:
                print(f"- 最近章{task}包: 失败（{exc}）")
                failed = True
    return 1 if failed else 0


def _character_reference_record(path):
    """构造人物正文指称：姓名/别名为强命中，自定义称呼为弱命中。"""
    fm, _, _ = read_doc(path)
    display_name = str(fm.get("name") or path.stem)
    strong = []
    for value in (display_name, path.stem, *(fm.get("aliases") or [])):
        value = str(value or "").strip()
        if len(value) >= 2 and value not in strong:
            strong.append(value)

    weak = {
        str(value).strip()
        for value in (fm.get("reference-terms") or [])
        if len(str(value).strip()) >= 2
    }
    return {"path": path, "fm": fm, "strong": tuple(strong), "weak": tuple(sorted(weak))}


def _suspected_unreferenced_characters(fm, body, character_records):
    """返回草稿 characters 中疑似没在正文出场的人物名。

    自定义称呼只在本章所列人物中能唯一指向时算作命中，避免同一称呼
    指向多人时掩盖 frontmatter 与正文不一致。
    """
    prose = "\n".join(extract_prose_lines(body))
    prose = re.sub(r"<!--.*?-->", "", prose, flags=re.DOTALL)
    if not prose.strip():
        return []

    listed = []
    seen_paths = set()
    for raw_name in fm.get("characters") or []:
        name = str(raw_name or "").strip()
        record = character_records.get(name)
        if not record or record["path"] in seen_paths:
            continue
        seen_paths.add(record["path"])
        listed.append((name, record))

    pov_record = character_records.get(str(fm.get("pov") or "").strip())
    pov_path = pov_record["path"] if pov_record else None
    weak_owners = {}
    for _, record in listed:
        for term in record["weak"]:
            weak_owners.setdefault(term, set()).add(record["path"])

    missing = []
    for name, record in listed:
        if record["path"] == pov_path:
            continue
        if any(term in prose for term in record["strong"]):
            continue
        if any(
            term in prose and len(weak_owners.get(term, ())) == 1
            for term in record["weak"]
        ):
            continue
        missing.append(name)
    return missing


def cmd_lint(args):
    problems = []
    warnings = []
    chapters = _load_chapters()

    known_characters = set()
    known_primary_characters = set()
    character_death_chapter = {}
    character_scopes = {}
    character_reference_records = {}
    for p in iter_entity_files(CHARACTERS_DIR):
        fm, _, _ = read_doc(p)
        display_name = fm.get("name") or p.stem
        scope = fm.get("context-scope") or "standard"
        if scope not in CHARACTER_CONTEXT_SCOPES:
            problems.append(
                f"[人物上下文范围非法] {p.relative_to(ROOT)} 的 context-scope 为「{scope}」，"
                f"允许值：{'、'.join(sorted(CHARACTER_CONTEXT_SCOPES))}"
            )
        known_primary_characters.add(display_name)
        known_characters.add(display_name)
        known_characters.add(p.stem)
        character_scopes[display_name] = scope
        character_scopes[p.stem] = scope
        for alias in fm.get("aliases") or []:
            known_characters.add(alias)
            character_scopes[alias] = scope
        reference_record = _character_reference_record(p)
        for identifier in (display_name, p.stem, *(fm.get("aliases") or [])):
            if identifier:
                character_reference_records[str(identifier)] = reference_record
        if fm.get("status") == "dead" and isinstance(fm.get("death-chapter"), int):
            character_death_chapter[display_name] = fm["death-chapter"]

    # 关系声口卡必须使用已登记的规范姓名，且同一人物对的阶段不能重叠。
    relationship_headers, relationship_rows = _parse_markdown_table(RELATIONSHIPS_PATH)
    relationship_required = {
        "人物A", "人物B", "适用章节", "类型与阶段", "私下／日常声口",
        "公开／正式声口", "冲突与禁止捷径",
    }
    if not relationship_headers:
        problems.append("[关系声口表缺失] continuity/relationships.md 没有可识别的关系表")
    elif not relationship_required.issubset(relationship_headers):
        missing = "、".join(sorted(relationship_required - set(relationship_headers)))
        problems.append(f"[关系声口表字段缺失] continuity/relationships.md 缺少：{missing}")
    else:
        rel_idx = {name: relationship_headers.index(name) for name in relationship_required}
        spans_by_pair = {}
        for row_number, row in enumerate(relationship_rows, start=1):
            person_a = row[rel_idx["人物A"]].strip()
            person_b = row[rel_idx["人物B"]].strip()
            if person_a not in known_primary_characters:
                problems.append(f"[关系人物未登记] 第{row_number}行人物A「{person_a}」不是 characters/ 中的规范姓名")
            if person_b not in known_primary_characters:
                problems.append(f"[关系人物未登记] 第{row_number}行人物B「{person_b}」不是 characters/ 中的规范姓名")
            if person_a == person_b:
                problems.append(f"[关系人物重复] 第{row_number}行两端都是「{person_a}」")
            for field in ("类型与阶段", "私下／日常声口", "公开／正式声口", "冲突与禁止捷径"):
                if not row[rel_idx[field]].strip():
                    problems.append(f"[关系声口缺项] 第{row_number}行「{person_a}—{person_b}」缺少{field}")
            span_raw = row[rel_idx["适用章节"]].strip()
            span = _parse_chapter_span(span_raw)
            if not span:
                problems.append(f"[关系章节范围非法] 第{row_number}行「{person_a}—{person_b}」适用章节为「{span_raw}」")
                continue
            pair = tuple(sorted((person_a, person_b)))
            for other_start, other_end, other_row in spans_by_pair.get(pair, []):
                if max(span[0], other_start) <= min(span[1], other_end):
                    problems.append(
                        f"[关系阶段重叠] 「{pair[0]}—{pair[1]}」第{other_row}行与第{row_number}行的适用章节重叠"
                    )
            spans_by_pair.setdefault(pair, []).append((span[0], span[1], row_number))

    seen_chapter_numbers = {}
    for c in chapters:
        fm = c["fm"]
        num = fm.get("chapter")
        rel = c["path"].relative_to(ROOT)

        if num in seen_chapter_numbers:
            problems.append(f"[重复章号] {rel} 与 {seen_chapter_numbers[num]} 都是第 {num} 章")
        else:
            seen_chapter_numbers[num] = rel

        for name in fm.get("characters") or []:
            if name and name not in known_characters:
                problems.append(f"[未登记人物] {rel} 引用了人物「{name}」，但 characters/ 下没有对应文件")
            elif character_scopes.get(name) == "direction-only":
                problems.append(
                    f"[方向冷人物越界] {rel} 把「{name}」列为在场人物；"
                    "作者确认其进入近期三章后，须先把人物档 context-scope 转为 standard"
                )

        for name, death_ch in character_death_chapter.items():
            if isinstance(num, int) and num > death_ch and name in (fm.get("characters") or []):
                problems.append(
                    f"[死人复活] {rel}（第{num}章）中「{name}」以在场人物出现，但该角色已在第{death_ch}章死亡；"
                    f"若为回忆/追述，请把该名字移到 mentions 字段而不是 characters 字段"
                )

        if fm.get("status") in ("draft", "待审核"):
            for name in _suspected_unreferenced_characters(fm, c["body"], character_reference_records):
                warnings.append(
                    f"[疑似多列人物] {rel} 的 characters 列出「{name}」，"
                    "但正文未命中其规范名、别名或可唯一指向的官职称呼；"
                    "请核对是否应移到 mentions，若正文确实只用固定称呼，请补入人物 aliases"
                )

        if fm.get("status") == "已确认":
            fpath = final_chapter_path(fm)
            if not fpath.exists():
                problems.append(
                    f"[正稿缺失] {rel} 状态是「已确认」，但 {fpath.relative_to(ROOT)} 不存在，"
                    f"请运行 `python3 scripts/story.py confirm-chapter {num}`"
                )
            else:
                expected = build_final_content(fm, c["body"])
                actual = fpath.read_text(encoding="utf-8")
                if actual != expected:
                    problems.append(
                        f"[正稿与草稿不同步] {fpath.relative_to(ROOT)} 与草稿 {rel} 当前内容重新生成的正稿不一致"
                        f"（草稿改完忘了重新确认，或正稿被手动改过）；"
                        f"请重新运行 `python3 scripts/story.py confirm-chapter {num}`"
                    )

        for prose_line, category, matched, advice in find_prose_style_issues(c["body"]):
            problems.append(
                f"[{category}] {rel} 正文第{prose_line}行命中「{matched}」：{advice}"
            )
        for prose_line, category, matched, advice in find_prose_style_warnings(c["body"]):
            warnings.append(
                f"[{category}] {rel} 从正文第{prose_line}行起命中「{matched}」：{advice}"
            )

    headers, rows = _parse_markdown_table(PROMISES_INDEX)
    if headers and rows:
        try:
            idx_plant = headers.index("埋下章节")
            idx_status = headers.index("状态")
            idx_name = headers.index("伏笔")
        except ValueError:
            idx_plant = idx_status = idx_name = None
        max_chapter = max([c["fm"].get("chapter") or 0 for c in chapters], default=0)
        if idx_plant is not None:
            for row in rows:
                if row[idx_status].strip() in ("待回收", "") and row[idx_plant].strip().isdigit():
                    gap = max_chapter - int(row[idx_plant].strip())
                    if gap > 40:
                        problems.append(
                            f"[伏笔可能遗忘] 「{row[idx_name]}」在第{row[idx_plant]}章埋下，"
                            f"已过去 {gap} 章仍未回收（阈值 40 章，可按需调整）"
                        )

    # 活跃/归档连续性表互斥，活跃表不得留已完成状态
    for active_path, archive_path, key_header, resolved_words in (
        (PROMISES_INDEX, PROMISES_ARCHIVE, "伏笔", ("已回收",)),
        (QUESTIONS_INDEX, QUESTIONS_ARCHIVE, "悬念", ("已解答",)),
    ):
        active_headers, active_rows = _parse_markdown_table(active_path)
        archive_headers, archive_rows = _parse_markdown_table(archive_path)
        if active_headers and key_header in active_headers:
            key_idx = active_headers.index(key_header)
            status_idx = active_headers.index("状态") if "状态" in active_headers else None
            active_names = {row[key_idx].strip() for row in active_rows}
            if status_idx is not None:
                allowed = ACTIVE_PROMISE_STATUSES if key_header == "伏笔" else ACTIVE_QUESTION_STATUSES
                for row in active_rows:
                    if any(word in row[status_idx] for word in resolved_words):
                        problems.append(f"[活跃表误留已结项] 「{row[key_idx]}」状态为「{row[status_idx]}」，应移入 {archive_path.relative_to(ROOT)}")
                    elif row[status_idx].strip() not in allowed:
                        problems.append(
                            f"[活跃表状态非法] 「{row[key_idx]}」状态为「{row[status_idx]}」，"
                            f"允许值：{'、'.join(sorted(allowed))}"
                        )
            if archive_headers and key_header in archive_headers:
                archive_idx = archive_headers.index(key_header)
                duplicates = active_names & {row[archive_idx].strip() for row in archive_rows}
                for name in sorted(duplicates):
                    problems.append(f"[活跃/归档重复] 「{name}」同时出现在 {active_path.relative_to(ROOT)} 与 {archive_path.relative_to(ROOT)}")

    # 归档章节必须已确认，不允许把待审稿提前封存
    if CONTINUITY_ARCHIVE.exists():
        archive_fm, _, _ = read_doc(CONTINUITY_ARCHIVE)
        archived_through = archive_fm.get("archived-through")
        if isinstance(archived_through, int):
            for c in chapters:
                num = c["fm"].get("chapter")
                if isinstance(num, int) and num <= archived_through and c["fm"].get("status") != "已确认":
                    problems.append(f"[归档章节未确认] 第{num}章已列入历史归档，但状态仍是「{c['fm'].get('status')}」")

    # 物品状态同步检查：正文里最后一次动过某物品的章节，是否 >= state.md 登记的"最后更新章节"
    if STATE_PATH.exists():
        _, item_headers, item_rows = _state_section_table(
            STATE_PATH.read_text(encoding="utf-8"), "活跃物品与文书"
        )
        if item_headers:
            idx_item = next(
                (item_headers.index(name) for name in ("物品／文书", "物品", "物品/文书") if name in item_headers),
                None,
            )
            idx_last_ch = item_headers.index("最后更新章节") if "最后更新章节" in item_headers else None
            idx_aliases = item_headers.index("对应 objects") if "对应 objects" in item_headers else None
            if idx_item is None or idx_last_ch is None:
                problems.append(
                    "[物品状态表字段缺失] continuity/state.md 的活跃物品表必须包含"
                    "「物品／文书」与「最后更新章节」；否则物品同步检查不会生效"
                )
            if idx_item is not None:
                registered_last_chapter = {}
                for row in item_rows:
                    name = row[idx_item].strip()
                    if name and name != "_(暂无)_":
                        val = row[idx_last_ch].strip() if idx_last_ch is not None else ""
                        last_chapter = int(val) if val.isdigit() else None
                        aliases = [name]
                        if idx_aliases is not None:
                            aliases.extend(
                                x.strip() for x in re.split(r"[、；;]", row[idx_aliases]) if x.strip()
                            )
                        for alias in aliases:
                            if alias in registered_last_chapter and registered_last_chapter[alias] != last_chapter:
                                problems.append(f"[物品别名重复] 「{alias}」在活跃物品表中映射到多个更新章节")
                            registered_last_chapter[alias] = last_chapter

                last_touched_in_chapters = {}
                archived_through = _archived_through()
                for c in chapters:
                    num = c["fm"].get("chapter")
                    # archived-through 以前已经冻结为确认历史；活跃表只负责
                    # 归档线之后的新变化。旧物若再次出现，会以新章号重新被检查。
                    if not isinstance(num, int) or num <= archived_through:
                        continue
                    for name in c["fm"].get("objects") or []:
                        if not name:
                            continue
                        if name not in last_touched_in_chapters or num > last_touched_in_chapters[name]:
                            last_touched_in_chapters[name] = num

                archived_item_headers, archived_item_rows = _section_table(CONTINUITY_ARCHIVE, "历史物品")
                archived_last_chapter = {}
                if archived_item_headers and "物品" in archived_item_headers and "最后更新章节" in archived_item_headers:
                    archived_name_idx = archived_item_headers.index("物品")
                    archived_last_idx = archived_item_headers.index("最后更新章节")
                    for row in archived_item_rows:
                        value = row[archived_last_idx].strip()
                        archived_last_chapter[row[archived_name_idx].strip()] = int(value) if value.isdigit() else None

                duplicates = set(registered_last_chapter) & set(archived_last_chapter)
                for name in sorted(duplicates):
                    problems.append(f"[活跃/归档物品重复] 「{name}」同时登记在 continuity/state.md 与 {CONTINUITY_ARCHIVE.relative_to(ROOT)}")

                for name, last_ch in last_touched_in_chapters.items():
                    if name not in registered_last_chapter and name not in archived_last_chapter:
                        problems.append(
                            f"[物品未登记] 「{name}」在章节 objects 字段中出现（最后见于第{last_ch}章），"
                            f"但活跃状态与历史归档都没有对应行"
                        )
                    elif name in registered_last_chapter and (
                        registered_last_chapter[name] is None or registered_last_chapter[name] < last_ch
                    ):
                        problems.append(
                            f"[物品状态未同步] 「{name}」在第{last_ch}章发生状态变化，"
                            f"但 continuity/state.md 登记的最后更新章节仍是"
                            f"{registered_last_chapter[name] if registered_last_chapter[name] is not None else '空'}，"
                            f"请回写当前持有者/位置并更新该列"
                        )

                # 物品若在归档所记章节之后再次变化，必须重回活跃 state
                for name, last_ch in last_touched_in_chapters.items():
                    archived_last = archived_last_chapter.get(name)
                    if name not in registered_last_chapter and archived_last is not None and last_ch > archived_last:
                        problems.append(f"[归档物品重新活跃] 「{name}」在第{last_ch}章再次变化，必须重新登记进 continuity/state.md")
        else:
            problems.append(
                "[物品状态表缺失] continuity/state.md 未找到「活跃物品与文书／物品状态」表，"
                "物品同步检查已停止"
            )

    # 地理关系矛盾检查：geography.md 内部同一对地点的方位记录是否自相矛盾
    geo_headers, geo_rows = _parse_markdown_table(GEOGRAPHY_PATH)
    if geo_headers:
        try:
            idx_a = geo_headers.index("地点A")
            idx_dir = geo_headers.index("方向")
            idx_b = geo_headers.index("地点B")
        except ValueError:
            idx_a = idx_dir = idx_b = None
        if idx_a is not None:
            implied = {}  # (地点较小者, 地点较大者) -> {较小者相对于较大者的方向}
            for row in geo_rows:
                a, b = row[idx_a].strip(), row[idx_b].strip()
                direction = _extract_direction(row[idx_dir])
                if not a or not b or a == "_(暂无)_" or not direction:
                    continue
                if a <= b:
                    key, norm_dir = (a, b), direction
                else:
                    key, norm_dir = (b, a), OPPOSITE_DIRECTION.get(direction, direction)
                implied.setdefault(key, set()).add(norm_dir)
            for (p1, p2), dirs in implied.items():
                if len(dirs) > 1:
                    problems.append(
                        f"[地理方位矛盾] 「{p1}」与「{p2}」之间在 worldbuilding/geography.md 中被记录了"
                        f"互相矛盾的方位关系：{sorted(dirs)}"
                    )

    for warning in warnings:
        print(warning)
    if not problems:
        if warnings:
            print(f"\n未发现问题。另有 {len(warnings)} 条非阻塞提示。")
        else:
            print("未发现问题。")
        return 0
    for p in problems:
        print(p)
    print(f"\n共 {len(problems)} 个问题。")
    return 1


def cmd_compile(args):
    """导出成稿：只拼"已确认"章节在 final/ 下的正稿，drafts 里未确认的章节不会被导出。"""
    chapters = [c for c in _load_chapters(full=False) if c["fm"].get("status") == "已确认"]
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    parts = []
    missing = []
    for c in chapters:
        fpath = final_chapter_path(c["fm"])
        if not fpath.exists():
            missing.append(c["fm"].get("chapter"))
            continue
        parts.append(fpath.read_text(encoding="utf-8").strip())
    out_path.write_text("\n\n\n".join(parts) + "\n", encoding="utf-8")
    try:
        shown_path = out_path.relative_to(ROOT)
    except ValueError:
        shown_path = out_path
    print(f"已导出 {len(parts)} 章到 {shown_path}")
    if missing:
        print(f"警告：以下已确认章节缺少正稿文件，未纳入导出：{missing}；请运行 confirm-chapter 重新生成", file=sys.stderr)
    return 0


def main():
    parser = argparse.ArgumentParser(description="网文写作工作区维护脚本")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new-chapter", help="创建下一章骨架文件")
    p_new.add_argument("volume", help="卷号")
    p_new.add_argument("title", help="章节标题")
    p_new.set_defaults(func=cmd_new_chapter)

    p_wc = sub.add_parser("wordcount", help="统计每章字数")
    p_wc.add_argument("--write", action="store_true", help="写回 frontmatter 与 chapters/_index.md")
    p_wc.set_defaults(func=cmd_wordcount)

    p_catalog = sub.add_parser("catalog", help="构建/检查可重建的章节元数据缓存")
    p_catalog.add_argument("--refresh", action="store_true", help="忽略旧缓存并重新解析全部章节 frontmatter")
    p_catalog.set_defaults(func=cmd_catalog)

    p_stats = sub.add_parser("stats", help="从章节 frontmatter 快速汇总进度")
    p_stats.set_defaults(func=cmd_stats)

    p_confirm = sub.add_parser("confirm-chapter", help="确认章节：从草稿生成正稿并把 status 改为 已确认")
    p_confirm.add_argument("chapter", type=int, help="章号（整数）")
    p_confirm.set_defaults(func=cmd_confirm_chapter)

    p_review_text = sub.add_parser("review-text", help="只读输出草稿正文，不写缓存或记录")
    p_review_text.add_argument("chapter", type=int)
    p_review_text.set_defaults(func=cmd_review_text)

    for name, handler in (("review-start", cmd_review_start), ("review-finish", cmd_review_finish)):
        p_review = sub.add_parser(name, help="开始/完成一轮绑定正文版本的冷读记录")
        p_review.add_argument("chapter", type=int, help="目标章号")
        p_review.add_argument("--stage", required=True, choices=REVIEW_STAGES)
        p_review.set_defaults(func=handler)

    p_review_check = sub.add_parser("review-check", help="只读核验冷读记录、正文版本及问题处置")
    p_review_check.add_argument("chapter", type=int, help="目标章号")
    p_review_check.set_defaults(func=cmd_review_check)

    p_ready = sub.add_parser("ready-chapter", help="冷读记录核验与 lint 后置为待审核，不生成正稿")
    p_ready.add_argument("chapter", type=int, help="目标章号")
    p_ready.set_defaults(func=cmd_ready_chapter)

    p_reindex = sub.add_parser("reindex", help="重建各 _index.md 表格")
    p_reindex.set_defaults(func=cmd_reindex)

    p_lint = sub.add_parser("lint", help="轻量一致性检查")
    p_lint.set_defaults(func=cmd_lint)

    p_compile = sub.add_parser("compile", help="拼出完整稿件")
    p_compile.add_argument("--out", default="manuscript.md", help="输出文件路径（相对项目根目录）")
    p_compile.set_defaults(func=cmd_compile)

    p_context = sub.add_parser("context", help="按任务生成可解释、有预算的最小上下文包")
    p_context.add_argument("--task", required=True, choices=CONTEXT_TASKS, help="任务类型")
    p_context.add_argument("--chapter", type=int, help="目标章号；direction 可省略，其他任务必填")
    p_context.add_argument("--focus", action="append", default=[], help="显式关键词，可重复")
    p_context.add_argument("--include", action="append", default=[], help="强制纳入的项目内文件，可重复")
    p_context.add_argument("--voice-chapter", type=int, help="限长载入一章已确认正文作为声口样本；不作为事实来源")
    default_max_chars = CONTEXT_CONFIG["default_max_chars"]
    p_context.add_argument(
        "--max-chars", type=int, default=default_max_chars,
        help=f"辅助上下文字符预算（项目默认 {default_max_chars}）",
    )
    p_context.add_argument("--out", help="写入 .story-cache/ 下的路径；不填则输出到终端")
    p_context.set_defaults(func=cmd_context)

    p_audit = sub.add_parser("context-audit", help="检查常驻上下文体积、过长档案与活跃/归档边界")
    p_audit.set_defaults(func=cmd_context_audit)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
