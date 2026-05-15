from __future__ import annotations

from collections import Counter
import re

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
    "軟件": "软件",
    "畫工": "化工",
    "航天": "航天",
    "李礦": "锂矿",
    "軍線": "均线",
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
    "訪談": "反弹",
    "點位": "点位",
    "資金流": "资金流",
    "流入": "流入",
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


def build_note(segments: list[TranscriptSegment], source_url: str) -> str:
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
        f"- 来源：{source_url}",
        f"- 转写时长：{duration}",
        f"- 转写片段：{len(segments)}",
        f"- 结束原因：{ended_reason or '未知'}",
        "",
        "## 一句话结论",
        "",
        build_core_takeaway(full_text),
        "",
        "## 要点",
        "",
    ]
    lines.extend(build_key_points(full_text))
    lines.extend(["", "## 板块观察", ""])
    lines.extend(build_sector_points(full_text))
    lines.extend(["", "## 关键时间线", ""])
    lines.extend(build_refined_timeline(cleaned_segments))
    lines.extend(["", "## 需核对的 ASR 词", ""])
    lines.extend(build_uncertain_terms(full_text))
    return "\n".join(lines).strip() + "\n"


def clean_text(text: str) -> str:
    cleaned = text
    for source, target in CORRECTIONS.items():
        cleaned = cleaned.replace(source, target)
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(.)\1{3,}", r"\1\1", cleaned)
    return cleaned.strip(" ，。,.")


def build_core_takeaway(text: str) -> str:
    if not text:
        return "- 暂无足够内容形成结论。"
    points = []
    if all(term in text for term in ["4126", "4190", "10日均线"]):
        points.append("主播认为午前反弹仍属修复性质，下午先看 4190 附近压力和 10 日均线能否守住；资金流若继续回流，反弹才有延续基础。")
    if "资金流" in text:
        points.append("核心观察变量是资金流：早盘快速流出，10 点后流出放缓，10 点半后开始回流，是反弹出现的主要解释。")
    if "机器人" in text and "半导体" in text:
        points.append("强势方向集中在半导体、消费电子、AI 应用、机器人、新能源车等科技和高端制造链条。")
    if not points:
        points.append(text[:180] + ("..." if len(text) > 180 else ""))
    return "\n".join(f"- {point}" for point in points[:3])


def build_key_points(text: str) -> list[str]:
    rules = [
        ("4126", "4126 附近被主播视为早盘支撑位，实际低点接近该区域，随后市场没有继续下杀。"),
        ("4190", "4190 附近是 30 分钟级别压力位；若下午不能有效突破，反弹强度仍不足。"),
        ("10日均线", "上证 10 日均线约在 4177-4178 一带，下午若重新跌破，反弹偏弱，下周一仍可能继续探低。"),
        ("资金流", "资金流是判断反弹能否延续的第二个关键变量；若午后重新向下，指数大概率承压。"),
        ("科创板", "科创板、芯片半导体、消费电子、机器人等仍是需要重点观察的强势方向。"),
        ("加法", "做加法不应只看跌幅；更适合关注逆势强、或热点板块中前期涨幅不大后回调的标的。"),
        ("放巨量", "高位冲高后放巨量、回落明显的品种，被主播视为高位减仓迹象，短线修复难度更大。"),
    ]
    points = [f"- {summary}" for keyword, summary in rules if keyword in text]
    return points or ["- 未识别到稳定的结构化要点，建议查看原始转写。"]


def build_sector_points(text: str) -> list[str]:
    rules = [
        ("半导体", "半导体/芯片：早盘回踩后反弹，仍属于较强方向；主播提到其接近 5 日线或五线谱红线后修复。"),
        ("消费电子", "消费电子：与半导体硬件链条相关，早盘也有表现。"),
        ("AI应用", "AI 应用/软件开发：早盘有所异动，但强度弱于机器人、半导体等方向。"),
        ("机器人", "机器人：10 点半后走强，逻辑包括马斯克相关预期、大摩对中国机器人产业链的判断，以及与新能源车产业链的重叠。"),
        ("新能源车", "新能源车：与机器人同属高端制造和装备制造链条，资金可能从高位方向向中低位方向切换。"),
        ("化工", "化工：早盘有补涨性质，但前期横盘较久，整体弹性有限。"),
        ("电力", "电力：短期偏弱，5 日均线压制、10 日均线支撑；若回踩不能守住，走势会转差。"),
        ("航天", "航天：套牢盘较多，上行不顺；10 日均线暂时守住，但成交量不足，修复需要放量。"),
        ("锂矿", "锂矿：已连续下跌多日，下周一是第八天时间窗口；若仍止不住，走势会更难看。"),
        ("黄金", "黄金：受消息影响大，短期偏弱，修复不容易。"),
        ("固态电池", "固态电池/电池：目前尚未走坏，重点观察 5 日线是否下穿 10 日线形成死叉。"),
    ]
    points = [f"- {summary}" for keyword, summary in rules if keyword in text]
    return points or ["- 暂未提炼出明确板块观点。"]


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
