"""
Generate several candidate scripts and keep the one that best fits the
retention rules.

A single LLM call lands inside the word budget roughly half the time — the
failures are length drift, not broken structure. Generating a handful and
scoring them mechanically turns that into a near-certain hit, and on Groq's
free tier each attempt costs about three seconds and nothing else.

    python tools/pick_script.py "an AI voice clone draining a family account"
    python tools/pick_script.py "..." --candidates 6 --quiet

`--quiet` prints only the winning script, so it can be piped straight into a
generation run:

    SCRIPT=$(python tools/pick_script.py "..." --quiet)
    python cli.py --video-script "$SCRIPT" ...
"""

import argparse
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "docs",
    "prompts",
    "retention-script-system-prompt.md",
)

# 与提示词里的长度规则保持一致：改一边必须同时改另一边，否则打分会把
# 完全合规的稿子判成不合格。Edge TTS 默认语速约 2.84 词/秒，60 秒即 170 词。
MIN_WORDS = 200
MAX_WORDS = 250
MIN_SENTENCES = 18
MAX_SENTENCES = 45
# Edge TTS 的实际语速取决于句长：长句里的停顿多，短句几乎连着读。实测同一
# 把声音在长句稿子上是 2.84 词/秒，在短句稿子上到 3.17。下限必须按更快的
# 那个值算，否则一篇“合格”的稿子会渲染成不足 60 秒的成片。
WORDS_PER_SECOND = 3.2
# 超过这个平均句长，字幕就会在竖屏上折成四行。实测 18 词一句必然溢出。
MAX_WORDS_PER_SENTENCE = 11

# 与 VideoParams.custom_system_prompt 的 max_length 对齐。
MAX_SYSTEM_PROMPT_CHARS = 8000

# 弱稿里反复出现的套话。它们不增加任何信息，是脚本被凑长度的信号。
BANNED_PHRASES = (
    "until it was too late",
    "what hit them",
    "the damage was done",
    "suspect a thing",
    "was shocked",
    "still trying to recover",
    "little did they know",
    "in this video",
)

# 结尾如果只是复述结局，观众就知道可以走了。这些是“总结式收尾”的特征词。
SUMMARY_ENDINGS = (
    "savings were gone",
    "money was gone",
    "was lost",
    "were lost",
    "lost everything",
)


def load_system_prompt() -> str:
    """
    从 Markdown 文档里取出 BEGIN/END 之间的可执行提示词部分。

    标记必须独占一行。文档的“Usage”小节里印着提取用的 sed 命令，那行同样含有
    这两个标记；不加行锚点会先匹配到命令本身，只截出四个字符，而且不会报错，
    模型会拿着空提示词生成一篇跑题的长文。sed 版本因为锚定行首才幸免。
    """
    with open(PROMPT_FILE, encoding="utf-8") as fp:
        content = fp.read()
    match = re.search(
        r"^<!-- BEGIN -->[ \t]*$(.*?)^<!-- END -->[ \t]*$",
        content,
        re.DOTALL | re.MULTILINE,
    )
    if not match:
        raise SystemExit(f"no <!-- BEGIN -->/<!-- END --> block in {PROMPT_FILE}")
    prompt = match.group(1).strip()
    # 提示词意外变短是上面那类静默失败的信号，宁可直接停下来。
    if len(prompt) < 2000:
        raise SystemExit(
            f"extracted prompt is only {len(prompt)} chars — check the markers"
        )
    # llm._limit_script_text 超长时只打一条 warning 就直接截断，被切掉的往往是
    # 结尾的自检清单，模型照样返回一段“看起来正常”的稿子。这里提前拦下来。
    if len(prompt) > MAX_SYSTEM_PROMPT_CHARS:
        raise SystemExit(
            f"prompt is {len(prompt)} chars, over the {MAX_SYSTEM_PROMPT_CHARS} "
            f"limit — it would be silently truncated. Trim it first."
        )
    return prompt


def split_sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part]


def score(text: str) -> tuple[int, list[str]]:
    """
    给候选脚本打分，返回 (扣分, 问题列表)。分数越低越好。

    扣分权重按“对完播率的实际伤害”排序：问句结尾和总结式收尾直接毁掉循环，
    套话只是稀释信息，长度偏差可以靠挑选另一条候选解决。
    """
    problems: list[str] = []
    penalty = 0

    words = len(text.split())
    if words < MIN_WORDS:
        penalty += (MIN_WORDS - words) * 2
        problems.append(f"{words} words, short of {MIN_WORDS}")
    elif words > MAX_WORDS:
        penalty += (words - MAX_WORDS) * 2
        problems.append(f"{words} words, over {MAX_WORDS}")

    sentences = split_sentences(text)
    if not MIN_SENTENCES <= len(sentences) <= MAX_SENTENCES:
        penalty += 5
        problems.append(f"{len(sentences)} sentences")

    # 字幕渲染按句子断行，长句会在屏幕上堆成四行盖住画面。平均句长因此是
    # 可读性问题而不是文风偏好，必须参与打分。
    if sentences:
        average_words = len(text.split()) / len(sentences)
        if average_words > MAX_WORDS_PER_SENTENCE:
            penalty += int((average_words - MAX_WORDS_PER_SENTENCE) * 4)
            problems.append(f"{average_words:.0f} words per sentence")

    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            penalty += 15
            problems.append(f'banned phrase "{phrase}"')

    if sentences:
        last = sentences[-1].strip()
        if last.endswith("?"):
            penalty += 40
            problems.append("ends on a question")
        if any(marker in last.lower() for marker in SUMMARY_ENDINGS):
            penalty += 30
            problems.append("ends on a summary")

    # 数字必须写成单词，TTS 会把阿拉伯数字和符号读错。
    if re.search(r"\d", text) or "$" in text:
        penalty += 20
        problems.append("contains digits or symbols")

    return penalty, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("subject", help="video subject")
    parser.add_argument("--candidates", type=int, default=4)
    parser.add_argument("--language", default="en-US")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only the winning script, for piping into cli.py",
    )
    args = parser.parse_args()

    # 必须先导入 llm：app.config 在导入时会给 loguru 装上自己的 sink，
    # 提前调用 remove() 会被它重新覆盖，--quiet 下日志照样混进 stdout，
    # 让调用方把整段日志当成脚本内容传给下一步。
    from app.services import llm
    from loguru import logger

    if args.quiet:
        logger.remove()

    system_prompt = load_system_prompt()
    results: list[tuple[int, list[str], str]] = []
    failures: list[str] = []
    for index in range(args.candidates):
        try:
            text = llm.generate_script(
                video_subject=args.subject,
                language=args.language,
                paragraph_number=1,
                custom_system_prompt=system_prompt,
            ).strip()
        except Exception as exc:
            if not args.quiet:
                print(f"candidate {index + 1}: failed ({exc})", file=sys.stderr)
            continue
        if not text:
            continue
        # llm.generate_script 失败时不抛异常，而是把 "Error: ..." 当成正文返回。
        # 不在这里拦住，配额耗尽那一刻整批稿子都会变成错误信息，再被 TTS
        # 一字不差地念出来。
        if text.startswith("Error:") or text.startswith("Error "):
            failures.append(text.splitlines()[0][:200])
            if not args.quiet:
                print(
                    f"candidate {index + 1}: provider error — {text[:160]}",
                    file=sys.stderr,
                )
            continue
        penalty, problems = score(text)
        results.append((penalty, problems, text))
        if not args.quiet:
            state = "clean" if not problems else "; ".join(problems)
            print(
                f"candidate {index + 1}: {len(text.split())} words, "
                f"penalty {penalty} — {state}",
                file=sys.stderr,
            )

    if not results:
        # 非零退出码 + 空 stdout，让 `SCRIPT=$(...)` 这类调用不会拿到错误文本
        # 当脚本继续往下跑。
        print("no usable candidate was generated", file=sys.stderr)
        for failure in failures[:3]:
            print(f"  {failure}", file=sys.stderr)
        return 1

    results.sort(key=lambda item: item[0])
    penalty, problems, best = results[0]

    if args.quiet:
        print(best)
        return 0

    print(f"\n--- best candidate (penalty {penalty}) ---")
    print(best)
    if problems:
        print(f"\nremaining issues: {'; '.join(problems)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
