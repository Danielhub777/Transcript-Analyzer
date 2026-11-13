import csv
import re
from pathlib import Path


DICTIONARY_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "dictionaries"
    / "loughran_mcdonald.csv"
)

CATEGORY_COLUMNS = {
    "positive": "Positive",
    "negative": "Negative",
    "uncertainty": "Uncertainty",
}


def load_word_groups(path):
    groups = {category: set() for category in CATEGORY_COLUMNS}

    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"Word", *CATEGORY_COLUMNS.values()}
        missing = required.difference(reader.fieldnames or [])

        if missing:
            raise ValueError(
                f"Dictionary CSV is missing columns: {', '.join(sorted(missing))}"
            )

        for row in reader:
            word = row["Word"].strip().lower()

            for category, column in CATEGORY_COLUMNS.items():
                if word and int(row[column].strip() or "0") > 0:
                    groups[category].add(word)

    return groups


WORD_GROUPS = load_word_groups(DICTIONARY_PATH)


def analyze_language(text):
    # Convert text into lowercase words.
    words = re.findall(r"\b[a-z]+\b", text.lower())

    counts = {}
    matched_words = {}

    for category, vocabulary in WORD_GROUPS.items():
        matches = [
            word for word in words
            if word in vocabulary
        ]

        counts[category] = len(matches)
        matched_words[category] = sorted(set(matches))

    word_count = len(words)

    rates = {
        category: round(
            count / word_count * 1000, 2
        ) if word_count else 0.0
        for category, count in counts.items()
    }

    return {
        "token_count": word_count,
        "counts": counts,
        "rates_per_1000_words": rates,
        "matched_words": matched_words,
    }