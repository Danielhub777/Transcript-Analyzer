import json
import re
from pathlib import Path

from packages.analytics.language_analysis import analyze_language


PERSON_NAME = r"[A-Z][\w.'’\-]*(?:\s+[A-Z][\w.'’\-]*){1,4}"
ROLE_HEADING = re.compile(
    rf"(?P<name>{PERSON_NAME}),\s*"
    r"(?:CEO|CFO|COO|CTO|President|(?:S?VP|EVP|Director),\s*[A-Z][\w ,&-]*)"
)
NAMED_SPEAKER = re.compile(rf"(?:{PERSON_NAME}|Operator)")
AFFILIATED_SPEAKER = re.compile(rf"(?P<name>{PERSON_NAME})\s+\([^():]+\)")
PERSON_LABEL = re.compile(
    rf"{PERSON_NAME},\s*(?:CEO|CFO|COO|CTO|SVP|EVP|VP|Head of|Director|"
    r"(?:Senior |Executive )?Vice President|Chief|Analyst)\b[^:]*"
)
ROLE_LINE = re.compile(
    r"(?:Analyst\b|Chief [A-Za-z ]+ Officer\b|(?:Executive |Senior )?Vice President\b|"
    r"Founder,|President,|Director,|Head of )"
)


def read_transcript(file_path):
    """Open the transcript and return its text."""
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def find_qa_start(lines):
    """Find the Q&A introduction's line number."""
    markers = (
        "we'll now move over to q&a",
        "we'll now move to q&a",
        "we will now begin the question-and-answer",
        "we will now open the lines for a question and answer session",
        "let's open up the call for questions",
        "we will now transition to q&a",
        "i will take your questions",
        "i will now take your questions",
    )

    for index, line in enumerate(lines):
        # Normalize curly apostrophes for matching.
        normalized = line.lower().replace("’", "'")

        if normalized.strip() == "question and answer section" or any(
            marker in normalized for marker in markers
        ):
            return index

    return None


def parse_segments(lines, qa_start):
    """Group speech paragraphs under speakers and sections."""
    segments = []
    current_speaker = None
    split_headings = {
        index: line.strip()
        for index, line in enumerate(lines[:-1])
        if NAMED_SPEAKER.fullmatch(line.strip())
        and ROLE_LINE.match(lines[index + 1].strip())
    }
    has_role_headings = bool(split_headings) or any(
        ROLE_HEADING.fullmatch(line.strip())
        or (":" in line and PERSON_LABEL.fullmatch(line.split(":", 1)[0].strip()))
        for line in lines
    )
    paragraph = None
    discussion_start = next(
        (index for index, line in enumerate(lines)
         if line.strip().casefold() == "management discussion section"),
        -1,
    )

    for index, line in enumerate(lines):
        if index <= discussion_start:
            continue
        line = line.strip()

        if index in split_headings:
            current_speaker = split_headings[index]
            paragraph = None
            continue
        if index - 1 in split_headings:
            continue

        if not line:
            paragraph = None
            continue

        heading = ROLE_HEADING.fullmatch(line)
        if heading:
            current_speaker = heading["name"]
            paragraph = None
            continue

        if ":" in line:
            label, speech = line.split(":", 1)
            speaker = label.split(",", 1)[0].strip()
            affiliation = AFFILIATED_SPEAKER.fullmatch(label.strip())

            if speaker.isupper() or (
                has_role_headings and (
                    NAMED_SPEAKER.fullmatch(label.strip())
                    or PERSON_LABEL.fullmatch(label.strip())
                    or affiliation
                )
            ):
                current_speaker = affiliation["name"] if affiliation else speaker
                line = speech.strip()
                paragraph = None

        if not current_speaker or not line or (
            has_role_headings and (line.isdecimal() or not any(c.isalnum() for c in line))
        ):
            continue

        # Stage directions are not spoken paragraphs.
        if line.startswith("(") and line.endswith(")"):
            continue

        if qa_start is None:
            section = "unknown"
        elif index < qa_start:
            section = "prepared"
        else:
            section = "qa"

        if has_role_headings and paragraph and paragraph["section"] == section:
            paragraph["text"] += " " + line
            continue

        paragraph = {
            "speaker": current_speaker,
            "section": section,
            "text": line,
            "source_line": index,
        }
        segments.append(paragraph)

    return segments


def save_json(data, output_path):
    """Save structured results to a JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as output:
        json.dump(data, output, indent=2, ensure_ascii=False)

def summarize_language(segments):
    """Summarize speech language for the full call and each section."""
    groups = {
        "overall": segments,
        "prepared": [
            segment for segment in segments
            if segment["section"] == "prepared"
        ],
        "qa": [
            segment for segment in segments
            if segment["section"] == "qa"
        ],
        "unknown": [
            segment for segment in segments
            if segment["section"] == "unknown"
        ],
    }

    summaries = {}

    for group_name, group_segments in groups.items():
        combined_text = "\n".join(
            segment["text"] for segment in group_segments
        )

        summaries[group_name] = {
            "paragraph_count": len(group_segments),
            "language": analyze_language(combined_text),
        }

    return summaries

def unattributed_segments(lines):
    """Keep source paragraphs and their starting lines without guessing speakers."""
    segments = []
    paragraph = None
    for index, line in enumerate(lines):
        line = line.strip()
        if not line:
            paragraph = None
        elif paragraph is None:
            paragraph = {
                "speaker": None,
                "section": "unknown",
                "text": line,
                "source_line": index,
            }
            segments.append(paragraph)
        else:
            paragraph["text"] += " " + line
    return segments


def analyze_text(text, *, full_text=False):
    if not text.strip():
        raise ValueError("The transcript text is empty.")

    lines = text.splitlines()
    qa_start = None if full_text else find_qa_start(lines)
    segments = [] if full_text else parse_segments(lines, qa_start)

    if not segments:
        qa_start = None
        segments = unattributed_segments(lines)

    speakers = []
    section_counts = {
        "prepared": 0,
        "qa": 0,
        "unknown": 0,
    }

    for segment in segments:
        segment["language"] = analyze_language(segment["text"])

        speaker = segment["speaker"]

        if speaker is not None and speaker not in speakers:
            speakers.append(speaker)

        section = segment["section"]
        section_counts[section] += 1

    return {
        "language_summary": summarize_language(segments),
        "word_count": len(text.split()),
        "speaker_count": len(speakers),
        "speakers": speakers,
        "paragraph_count": len(segments),
        "section_counts": section_counts,
        "qa_start_line": qa_start,
        "segments": segments,
    }

def main():
    """Run the complete transcript-reading workflow."""
    project_root = Path(__file__).resolve().parents[2]

    # Change this if your saved filename differs.
    filename = "MSFT_FY2026_Q2.txt"

    input_path = (
        project_root / "data" / "raw" / "transcripts" / filename
    )

    output_path = (
        project_root / "data" / "processed"
        / f"{input_path.stem}_parsed.json"
    )

    text = read_transcript(input_path)

    if not text.strip():
        raise ValueError("The transcript file is empty.")

    lines = text.splitlines()
    qa_start = find_qa_start(lines)
    segments = parse_segments(lines, qa_start)

    if not segments:
        raise ValueError("No speaker paragraphs were detected.")

    result = {
        "source_file": filename,
        "word_count": len(text.split()),
        "qa_start_line": qa_start,
        "segments": segments,
    }

    save_json(result, output_path)

    print("Transcript:", filename)
    print("Word count:", result["word_count"])
    print("Paragraphs:", len(segments))
    print("Q&A starts at line:", qa_start)
    print("Saved to:", output_path)

    if qa_start is None:
        print("Warning: Q&A boundary not found; sections marked unknown.")


if __name__ == "__main__":
    main()
