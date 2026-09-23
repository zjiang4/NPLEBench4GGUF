#!/usr/bin/env python3
"""Build the NPLEBench text-only item set from a local LLM-Chinese-NMLE clone.

Usage:
    git clone https://github.com/zonghui0228/LLM-Chinese-NMLE.git
    python scripts/prepare_nplebench.py --source LLM-Chinese-NMLE --output data

Writes questions.json, answers.json, item_metadata.json, and excluded.json. Item IDs
are "<year>_<NNN>", where NNN is the item's position within that year's file; "number"
is the question number printed in the source, which restarts in each examination unit.
Each year's file contains four 120-item units in the order listed in UNITS.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

YEARS = ("2017", "2018", "2019", "2020", "2021")
UNIT_SIZE = 120
UNITS = (
    ("Pharmaceutical Chemistry/Pharmaceutics", "药学专业知识（一）"),
    ("Pharmacology", "药学专业知识（二）"),
    ("Regulations", "药事管理与法规"),
    ("Comprehensive Practice", "药学综合知识与技能"),
)
BLOCK_SEPARATOR = re.compile(r"(?m)^>{3,}\s*$")
ANSWER = re.compile(r"【\s*答案\s*】\s*([A-Ha-h,\s、，]+)")
ANSWER_AND_AFTER = re.compile(r"【\s*答案\s*】.*")
EXPLANATION_AND_AFTER = re.compile(r"【\s*(?:解析|说明)\s*】.*", re.S)
QUESTION_NUMBER = re.compile(r"^(\d+)[、.．]\s*(.*)$")
OPTION = re.compile(r"^([A-Ha-h])[\.\．、]\s*(.*)$")
FIGURE_REFERENCE = re.compile(r"如图|如下图|图中|(?:结构|结构式|骨架)如下")


def parse_block(block: str) -> dict:
    answer_match = ANSWER.search(block)
    answer_letters = re.findall(r"[A-H]", answer_match.group(1).upper()) if answer_match else []
    answer = sorted(dict.fromkeys(answer_letters))

    body = EXPLANATION_AND_AFTER.sub("", ANSWER_AND_AFTER.sub("", block))
    lines = [line.strip() for line in body.splitlines() if line.strip()]

    number = None
    stem_parts: list[str] = []
    options: dict[str, str] = {}
    current = ""
    for line in lines:
        if number is None:
            number_match = QUESTION_NUMBER.match(line)
            if number_match:
                number = int(number_match.group(1))
                line = number_match.group(2).strip()
                if not line:
                    continue
        option_match = OPTION.match(line)
        if option_match:
            current = option_match.group(1).upper()
            options[current] = option_match.group(2).strip()
        elif current:
            options[current] = (options[current] + "\n" + line).strip()
        else:
            stem_parts.append(line)

    return {"number": number, "stem": "\n".join(stem_parts).strip(), "options": options, "answer": answer}


def exclusion_reason(item: dict) -> str | None:
    if not item["stem"] or not item["answer"]:
        return "missing stem or answer"
    if not any(text.strip() for text in item["options"].values()):
        return "options are images"
    if any(letter not in item["options"] for letter in item["answer"]):
        return "answer not among options"
    if FIGURE_REFERENCE.search(item["stem"]):
        return "stem refers to a figure"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True, help="path to the LLM-Chinese-NMLE clone")
    parser.add_argument("--output", type=Path, required=True, help="directory for questions.json and answers.json")
    args = parser.parse_args()

    questions, answers, metadata, excluded = [], [], [], []
    for year in YEARS:
        text = (args.source / "data" / "pharmacist" / f"{year}.txt").read_text(encoding="utf-8", errors="ignore")
        blocks = [block.strip() for block in BLOCK_SEPARATOR.split(text.replace("\r\n", "\n")) if block.strip()]
        if len(blocks) != len(UNITS) * UNIT_SIZE:
            raise SystemExit(f"{year}: expected {len(UNITS) * UNIT_SIZE} items, found {len(blocks)}")
        for position, block in enumerate(blocks, start=1):
            item = parse_block(block)
            item_id = f"{year}_{position:03d}"
            unit = (position - 1) // UNIT_SIZE + 1
            subject, subject_zh = UNITS[unit - 1]
            reason = exclusion_reason(item)
            if reason:
                excluded.append({"id": item_id, "subject": subject, "reason": reason})
                continue
            number = item["number"] or position
            questions.append({"id": item_id, "year": int(year), "number": number,
                              "question": item["stem"], "options": item["options"]})
            answers.append({"id": item_id, "year": int(year), "number": number, "answer": item["answer"]})
            metadata.append({"id": item_id, "year": int(year), "unit": unit, "subject": subject,
                             "subject_zh": subject_zh,
                             "response_format": "multiple" if len(item["answer"]) > 1 else "single",
                             "option_count": len(item["options"])})

    args.output.mkdir(parents=True, exist_ok=True)
    outputs = (("questions.json", questions), ("answers.json", answers),
               ("item_metadata.json", metadata), ("excluded.json", excluded))
    for name, rows in outputs:
        (args.output / name).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"kept {len(questions)} items, excluded {len(excluded)}; written to {args.output}")


if __name__ == "__main__":
    main()
