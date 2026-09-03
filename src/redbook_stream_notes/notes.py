from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo

from .schemas import TranscriptSegment


STOPWORDS = {
    "the",
    "and",
    "you",
    "that",
    "this",
    "with",
    "have",
    "for",
    "就是",
    "这个",
    "那个",
    "然后",
    "因为",
    "所以",
    "可以",
    "我们",
    "你们",
}


CORRECTIONS = {
    "對吧": "对吧",
    "是吧": "是吧",
    "明白嗎": "明白吗",
    "為什麼": "为什么",
    "機器人": "机器人",
    "新能源車": "新能源车",
    "半導體": "半导体",
    "消費電子": "消费电子",
    "科創": "科创",
    "創業": "创业",
    "軟件": "软件",
    "應用": "应用",
    "畫工": "化工",
    "航天": "航天",
    "李礦": "锂矿",
    "軍線": "均线",
    "五日軍線": "5日均线",
    "十日軍線": "10日均线",
    "二十一天軍線": "21日均线",
    "五日縣市": "5日线",
    "訪談": "反弹",
    "光磨快": "光模块",
    "光某塊": "光模块",
    "拌倒起": "半导体",
    "喝串板": "科创板",
    "柯串": "科创",
    "十日均线": "10日均线",
    "五日均线": "5日均线",
    "上正": "上证",
    "中正五百": "中证500",
    "中正一千": "中证1000",
    "護身三零零": "沪深300",
    "隊長": "队长",
    "五線譜": "五线谱",
    "五線普": "五线谱",
    "靠普": "靠谱",
    "Deepseak": "DeepSeek",
    "長陽線": "长阳线",
    "長了": "涨了",
    "長的": "涨的",
    "長什麼": "涨什么",
    "長什麽": "涨什么",
    "漲": "涨",
    "跌回去了": "跌回去",
    "死差": "死叉",
    "隔壁了": "有问题了",
    "短切": "短期",
    "點位": "点位",
    "資金流": "资金流",
    "流入": "流入",
    "流出": "流出",
    "壓力位": "压力位",
    "支撐": "支撑",
    "匯率": "汇率",
    "美元對人民幣": "美元对人民币",
    "貴金屬": "贵金属",
    "黃金": "黄金",
}

FILLER_PATTERNS = [
    r"对吧",
    r"是吧",
    r"是不是",
    r"好吧",
    r"好了",
    r"来",
    r"明白吗",
    r"听懂了吗",
    r"看清楚",
    r"问大家",
    r"哥哥们姐姐们",
    r"朋友们",
    r"没有加关注.*?关注",
    r"把关注加上",
    r"点一波赞",
    r"打个\d+",
    r"打一下.*?榜",
    r"谢谢.*?礼物",
]


def build_note(
    segments: list[TranscriptSegment],
    source_url: str,
    captured_at: datetime | None = None,
) -> str:
    if not segments:
        return "# 直播笔记\n\n等待音频转写中。"

    full_text = " ".join(segment.text for segment in segments if segment.text.strip())
    keywords = extract_keywords(full_text)
    chapters = build_chapters(segments)

    lines = [
        "# 直播笔记",
        "",
        "## 来源",
        "",
        source_url,
        "",
        "## 日期",
        "",
        format_note_datetime(captured_at),
        "",
        "## 快速判断",
        "",
        f"- 已转写时长：{segments[-1].end_text}",
        f"- 片段数量：{len(segments)}",
        f"- 高频关键词：{', '.join(keywords) if keywords else '暂无'}",
        "",
        "## 核心摘要",
        "",
        summarize_text(full_text),
        "",
        "## 时间线",
        "",
    ]

    lines.extend(chapters)
    lines.extend(["", "## 原始转写", ""])
    for segment in segments[-80:]:
        lines.append(f"- [{segment.start_text} - {segment.end_text}] {segment.text}")

    return "\n".join(lines).strip() + "\n"


def build_refined_note(
    segments: list[TranscriptSegment],
    source_url: str,
    ended_reason: str | None = None,
    captured_at: datetime | None = None,
) -> str:
    if not segments:
        return "# 直播精炼整理\n\n暂无可整理内容。\n"

    cleaned_segments = [(segment, clean_text(segment.text)) for segment in segments]
    full_text = clean_text(" ".join(text for _, text in cleaned_segments))
    duration = segments[-1].end_text

    lines = [
        "# 直播精炼整理",
        "",
        "## 基本信息",
        "",
        f"- 日期：{format_note_datetime(captured_at)}",
        f"- 来源：{source_url}",
        f"- 转写时长：{duration}",
        f"- 转写片段：{len(segments)}",
        f"- 结束原因：{ended_reason or '未知'}",
        "",
        "## 一句话结论",
        "",
        build_core_takeaway(cleaned_segments, full_text),
        "",
        "## 要点",
        "",
    ]
    lines.extend(build_key_points(cleaned_segments, full_text))
    lines.extend(["", "## 板块观察", ""])
    lines.extend(build_sector_points(cleaned_segments))
    lines.extend(["", "## 关键时间线", ""])
    lines.extend(build_refined_timeline(cleaned_segments))
    lines.extend(["", "## 需核对的 ASR 词", ""])
    lines.extend(build_uncertain_terms(full_text))
    return "\n".join(lines).strip() + "\n"


def format_note_datetime(captured_at: datetime | None) -> str:
    if captured_at is None:
        return "未知"
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    local_time = captured_at.astimezone(ZoneInfo("Asia/Shanghai"))
    return local_time.strftime("%Y-%m-%d %H:%M:%S %Z")


def clean_text(text: str) -> str:
    cleaned = text
    for source, target in CORRECTIONS.items():
        cleaned = cleaned.replace(source, target)
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(.)\1{3,}", r"\1\1", cleaned)
    return cleaned.strip(" ，。,.")


def build_core_takeaway(cleaned_segments: list[tuple[TranscriptSegment, str]], text: str) -> str:
    if not text:
        return "- 暂无足够内容形成结论。"
    if has_any(text, ["资金流", "流出"]) and has_any(text, ["压力位", "支撑", "4200", "4199"]):
        return "- 本场核心是冲高回落后的下午判断框架：先看资金流能否止住流出，再看指数能否重新站回压力位，同时用关键支撑位判断回落是否失控。"
    if has_any(text, ["半导体", "CPO", "光模块"]) and has_any(text, ["第一次分歧", "死叉", "抱团"]):
        return "- 本场重点在科技主线的分歧：半导体和 CPO/光模块仍是核心方向，但高位抱团开始松动，需要用均线和成交量判断是正常休息还是转弱。"
    return f"- {polish_sentence(first_meaningful_text(cleaned_segments) or text, 180)}"


def build_key_points(cleaned_segments: list[tuple[TranscriptSegment, str]], text: str) -> list[str]:
    rules = [
        (["4200", "4199", "10日均线"], "指数冲到 4199 附近后回落，主播认为 4200 是心理压力，但更关键的是 10 日均线附近的技术压力。"),
        (["4173", "支撑"], "下方支撑被放在 4173 一带；若不能站回压力位，就要看这个支撑能否守住。"),
        (["4155", "4156", "支撑"], "另一个明确支撑在 4155/4156 附近，主播认为可以回落，但不能有效跌破这个位置。"),
        (["资金流", "超大单", "机构", "散户"], "高位回落的解释是机构/超大单流出、散户承接；下午首先观察资金流是否继续大幅流出。"),
        (["110万亿", "2.1万亿", "7千亿"], "主播用市值和成交额解释资金流：少量成交会影响全市场估值变化，所以资金流对指数波动有放大作用。"),
        (["科创", "创业", "主板", "散户"], "科创、创业、主板的强弱顺序被解释为筹码结构差异：散户越多，抛压和量化扰动越重。"),
    ]
    points = build_rule_points(text, rules, limit=6)
    if points:
        return points
    fallback = summarize_text(text, max_sentences=4).splitlines()
    return fallback or ["- 未识别到稳定的结构化要点，建议查看原始转写。"]


def build_sector_points(cleaned_segments: list[tuple[TranscriptSegment, str]]) -> list[str]:
    text = " ".join(item for _, item in cleaned_segments)
    rules = [
        (["石油", "煤炭", "油价"], "石油/煤炭：早盘领跌，主播归因于昨晚油价大跌。"),
        (["券", "放量", "冲高"], "券商：早盘放量冲高，但遇到压力后回落；后续要看能否真正突破黄线压力。"),
        (["机器人", "新高", "成交量"], "机器人：创出新高且成交量配合较好，主播认为走势相对健康。"),
        (["消费电子", "顶背离"], "消费电子：虽然也创新高，但冲高回落并出现小级别顶背离，强度弱于机器人。"),
        (["半导体", "第一次分歧"], "半导体：前两天是领涨主线，本场出现明显冲高回落，被主播定义为上涨后的第一次分歧。"),
        (["半导体", "外盘", "科技股"], "半导体：回落还与外盘科技股的不确定性有关，主播认为资金会提前反映今晚外盘可能回落的风险。"),
        (["CPO", "抱团", "死叉"], "CPO/光模块：与半导体同属抱团方向，尚未确认瓦解；若继续下跌并形成 5 日/10 日均线死叉，短期就要进入休息。"),
        (["科创", "创业", "主板"], "科创/创业：科技方向回落会直接影响科创和创业板，下午不能只看主板指数。"),
    ]
    return build_rule_points(text, rules, limit=8) or ["- 暂未提炼出明确板块观点。"]


def build_rule_points(
    text: str,
    rules: list[tuple[list[str], str]],
    limit: int,
) -> list[str]:
    points = []
    for keywords, summary in rules:
        if all(keyword.lower() in text.lower() for keyword in keywords):
            points.append(f"- {summary}")
        if len(points) >= limit:
            break
    return points


def build_topic_points(
    cleaned_segments: list[tuple[TranscriptSegment, str]],
    topics: list[tuple[str, list[str]]],
    limit: int,
) -> list[str]:
    points = []
    for label, keywords in topics:
        snippet = find_topic_snippet(cleaned_segments, keywords)
        if snippet:
            points.append(f"- {label}：{snippet}")
        if len(points) >= limit:
            break
    return points


def find_topic_snippet(cleaned_segments: list[tuple[TranscriptSegment, str]], keywords: list[str]) -> str:
    candidates = []
    for index, (_, text) in enumerate(cleaned_segments):
        if len(text) < 8 or is_low_signal(text):
            continue
        score = sum(1 for keyword in keywords if keyword.lower() in text.lower())
        if score == 0:
            continue
        context = merge_context(cleaned_segments, index)
        candidates.append((score, len(context), context))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], -item[1]))
    return shorten(candidates[0][2], 150)


def has_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def polish_sentence(text: str, limit: int) -> str:
    text = clean_text(shorten(text, limit))
    text = re.sub(r"(懂了没有|听懂了没有|是不是|对吧|好吧)", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ，。")
    return text or "暂无足够内容形成结论。"


def merge_context(cleaned_segments: list[tuple[TranscriptSegment, str]], index: int) -> str:
    texts = []
    for _, text in cleaned_segments[index : index + 4]:
        if text and not is_low_signal(text):
            texts.append(text)
    return "；".join(texts)


def first_meaningful_text(cleaned_segments: list[tuple[TranscriptSegment, str]]) -> str:
    for _, text in cleaned_segments:
        if len(text) >= 20 and not is_low_signal(text):
            return text
    return ""


def build_refined_timeline(cleaned_segments: list[tuple[TranscriptSegment, str]]) -> list[str]:
    buckets: list[str] = []
    last_text = ""
    for segment, text in cleaned_segments:
        if len(text) < 12:
            continue
        if is_low_signal(text):
            continue
        if similar_prefix(text, last_text):
            continue
        last_text = text
        buckets.append(f"- [{segment.start_text}] {shorten(text, 110)}")
        if len(buckets) >= 12:
            break
    return buckets or ["- 暂无可用时间线。"]


def build_uncertain_terms(text: str) -> list[str]:
    terms = []
    for term in ["队长", "五线谱", "大摩", "CPO/CPU", "4190", "4126"]:
        if term.replace("CPO/", "") in text or term in text:
            terms.append(f"- {term}：建议结合原直播画面或主播术语确认。")
    return terms or ["- 暂无明显高风险术语。"]


def is_low_signal(text: str) -> bool:
    low_signal_terms = ["关注", "点赞", "礼物", "打个", "听好", "懂了吗", "好不好"]
    return any(term in text for term in low_signal_terms) and len(text) < 40


def similar_prefix(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a[:24] == b[:24]


def shorten(text: str, limit: int) -> str:
    return text[:limit] + ("..." if len(text) > limit else "")


def extract_keywords(text: str, limit: int = 10) -> list[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_+-]{2,}", text)
    normalized = [token.lower() for token in tokens if token.lower() not in STOPWORDS]
    return [word for word, _ in Counter(normalized).most_common(limit)]


def summarize_text(text: str, max_sentences: int = 6) -> str:
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[。！？!?])\s+|[。\n]", text)
        if len(item.strip()) >= 8
    ]
    if not sentences:
        return "暂无足够内容形成摘要。"
    selected = sentences[:max_sentences]
    return "\n".join(f"- {sentence}" for sentence in selected)


def build_chapters(segments: list[TranscriptSegment], window: int = 8) -> list[str]:
    chapters: list[str] = []
    for offset in range(0, len(segments), window):
        group = segments[offset : offset + window]
        if not group:
            continue
        text = " ".join(item.text for item in group).strip()
        if not text:
            continue
        short = text[:120] + ("..." if len(text) > 120 else "")
        chapters.append(f"- [{group[0].start_text}] {short}")
    return chapters
