import re
from packages.analytics.read_transcripts import analyze_text, summarize_language


def find_evidence(analysis, section, category, limit=3):
    """Find paragraphs with the most matches for a category."""
    candidates = []

    for segment in analysis["segments"]:
        if section != "overall" and segment["section"] != section:
            continue

        language = segment["language"]
        match_count = language["counts"][category]

        if match_count == 0:
            continue

        candidates.append({
            "speaker": segment["speaker"],
            "section": segment["section"],
            "source_line": segment["source_line"],
            "text": segment["text"],
            "match_count": match_count,
            "matched_words": language["matched_words"][category],
        })

    candidates.sort(
        key=lambda paragraph: paragraph["match_count"],
        reverse=True,
    )

    return candidates[:limit]

def filter_speakers(analysis, selected_speakers):
    """Keep selected speakers and rebuild summaries."""
    selected = {
        name.strip().upper()
        for name in selected_speakers
        if name.strip()
    }

    if not selected:
        raise ValueError("Enter at least one management speaker.")

    segments = [
        segment for segment in analysis["segments"]
        if segment["speaker"] and segment["speaker"].strip().upper() in selected
    ]

    if not segments:
        raise ValueError(
            "No paragraphs matched the selected management speakers."
        )

    speakers = list(dict.fromkeys(
        segment["speaker"] for segment in segments
    ))

    return {
        **analysis,
        "segments": segments,
        "speakers": speakers,
        "speaker_count": len(speakers),
        "paragraph_count": len(segments),
        "section_counts": {
            section: sum(
                segment["section"] == section
                for segment in segments
            )
            for section in ("prepared", "qa", "unknown")
        },
        "language_summary": summarize_language(segments),
    }

GUIDANCE_METRIC = re.compile(
    r"\b(?:we\s+(?:now\s+)?(?:expect|forecast|project|anticipate)|"
    r"our\s+(?:guidance|outlook)\s+is\s+for)\s+"
    r"(?:(?:the|our)\s+)?(?P<metric>[\w -]{1,70}?)"
    r"(?:,\s*including\s+[^,]+,)?"
    r"\s+(?:to\s+(?:be|grow|increase|decline|range)\s+|of\s+(?!20\d{2}\s+to\b))"
    r"(?:in\s+the\s+range\s+of\s+)?",
    re.IGNORECASE,
)

PASSIVE_GUIDANCE_METRIC = re.compile(
    r"^(?:(?:our|the)\s+)?(?P<metric>[\w -]{1,70}?)\s+"
    r"(?:is|are)\s+(?:expected|projected|anticipated|forecast)\s+to\s+be\s+"
    r"(?:in\s+the\s+range\s+of\s+)?",
    re.IGNORECASE,
)

GUIDANCE_AMOUNT = r"\$?\d[\d,]*(?:\.\d+)?(?:\s*%|\s+(?:million|billion|basis points)\b)?"

GUIDANCE_VALUE = re.compile(
    rf"(?P<value>"
    rf"between\s+{GUIDANCE_AMOUNT}\s+and\s+{GUIDANCE_AMOUNT}"
    rf"|(?:between\s+|approximately\s+)?{GUIDANCE_AMOUNT}"
    rf"(?:\s*(?:to|[-‐‑–—])\s*{GUIDANCE_AMOUNT})?"
    rf"(?:,?\s+(?:plus or minus|±)\s*{GUIDANCE_AMOUNT})?"
    rf")(?![\d.,]\d)",
    re.IGNORECASE,
)

GUIDANCE_PERIOD = re.compile(
    r"\b(?:FY\s*\d{2,4}\s+Q[1-4]|Q[1-4]\s+FY\s*\d{2,4}|"
    r"(?:first|second|third|fourth|next|current)\s+"
    r"(?:fiscal\s+)?quarter(?:\s+\d{4})?|"
    r"full[- ]year(?:\s+\d{4})?|remaining\s+quarters\s+of\s+\d{4})\b",
    re.IGNORECASE,
)

METRIC_YEAR = re.compile(r"^(?P<year>20\d{2})\s+(?=\w)")

GUIDANCE_SCOPE = re.compile(
    r"^\s*(?:in|for)\s+"
    r"(?P<scope>M365 Commercial Cloud|"
    r"Productivity and Business Processes|"
    r"Intelligent Cloud|More Personal Computing|"
    r"(?:the\s+)?(?:total|overall)\s+company)"
    r"(?=\s|,|$)",
    re.IGNORECASE,
)

OUTLOOK_HEADING = re.compile(
    r"^\s*(?:now,?\s+)?(?:moving to|turning to|looking ahead to)\s+"
    r"(?:our\s+)?(?P<period>Q[1-4])\s+(?:outlook|guidance)\b",
    re.IGNORECASE,
)

def extract_guidance(analysis):
    """Return explicit numerical outlooks with their source evidence."""
    rows = []
    active_period = None
    active_period_context = None
    previous_speaker_section = None

    for segment in analysis["segments"]:
        speaker_section = (segment["speaker"], segment["section"])
        if speaker_section != previous_speaker_section:
            active_period = None
            active_period_context = None
        previous_speaker_section = speaker_section

        sentences = re.split(r"(?<=[.!?])\s+", segment["text"].strip())

        for index, sentence in enumerate(sentences):
            heading = OUTLOOK_HEADING.match(sentence)
            if heading:
                active_period = heading["period"].upper()
                active_period_context = sentence

            metric = GUIDANCE_METRIC.search(sentence) or PASSIVE_GUIDANCE_METRIC.match(sentence)
            if metric is None:
                continue

            value = GUIDANCE_VALUE.match(sentence, metric.end())
            if value is None:
                continue

            # A single value cannot represent paired metrics quoted respectively.
            if re.search(r"\brespectively\b", sentence[value.end():], re.IGNORECASE):
                continue
            reported_value = " ".join(value["value"].split())
            if "%" not in reported_value and "$" not in reported_value:
                if not re.search(r"\b(?:million|billion)\b", reported_value, re.I):
                    continue

            metric_name = metric["metric"].strip()
            metric_period = GUIDANCE_PERIOD.search(metric_name)
            leading_year = METRIC_YEAR.match(metric_name)
            periods = {
                match.group().lower(): match.group()
                for match in GUIDANCE_PERIOD.finditer(sentence[:value.start()])
            }
            if metric_period:
                metric_name = " ".join((
                    re.sub(r"\s+for(?:\s+the)?$", "", metric_name[:metric_period.start()].rstrip()),
                    metric_name[metric_period.end():].strip(),
                )).strip()
            elif leading_year:
                year = leading_year["year"]
                periods[year] = year
                metric_name = metric_name[leading_year.end():]

            period_context = None

            trailing_year = re.match(r"\s+in\s+(20\d{2})\b", sentence[value.end():])
            if not periods and trailing_year:
                year = trailing_year[1]
                periods[year] = year

            if not periods and index > 0:
                context = sentences[index - 1]

                if re.match(
                    r"^(?:turning to|looking ahead to|moving to|for|"
                    r"let me turn to (?:our|the) outlook for)\b",
                    context,
                    re.IGNORECASE,
                ):
                    periods = {
                        match.group().lower(): match.group()
                        for match in GUIDANCE_PERIOD.finditer(context)
                    }
                    if len(periods) == 1:
                        period_context = context

            if not periods and active_period is not None:
                periods = {active_period.lower(): active_period}
                period_context = active_period_context
            scope_match = GUIDANCE_SCOPE.match(sentence)
            scope_context = None

            if scope_match is None and index > 0:
                previous_sentence = sentences[index - 1]
                heading = re.sub(
                    r"^(?:turning to|moving to|starting with)\s+",
                    "For ",
                    previous_sentence,
                    flags=re.IGNORECASE,
                ).rstrip(".!?")

                scope_match = GUIDANCE_SCOPE.match(heading)
                if scope_match:
                    scope_context = previous_sentence

            basis_matches = {
                match.group(1).lower()
                for match in re.finditer(
                    r"\bon\s+an?\s+(adjusted|reported)\s+basis\b",
                    sentence,
                    re.IGNORECASE,
                )
            }
            reporting_basis = (
                next(iter(basis_matches)) if len(basis_matches) == 1 else None
            )

            if (
                scope_match is None
                and reporting_basis == "reported"
                and index > 0
                and re.match(
                    r"^and\s+on\s+a\s+reported\s+basis\b",
                    sentence,
                    re.IGNORECASE,
                )
            ):
                prior_sentence = sentences[index - 1]
                prior_scope = GUIDANCE_SCOPE.match(prior_sentence)
                if prior_scope and re.search(
                    r"\bon\s+an\s+adjusted\s+basis\b",
                    prior_sentence,
                    re.IGNORECASE,
                ):
                    scope_match = prior_scope
                    scope_context = prior_sentence

            rows.append({
                "metric": metric_name,
                "business_scope": (
                    scope_match["scope"] if scope_match else None
                ),
                "scope_context": scope_context,
                "forecast_period": (
                    next(iter(periods.values())) if len(periods) == 1 else None
                ),
                "period_context": period_context,
                "outlook": reported_value,
                "reporting_basis": reporting_basis,
                "currency_basis": (
                    "constant currency"
                    if re.search(r"\bconstant currency\b", sentence, re.IGNORECASE)
                    else None
                ),
                "speaker": segment["speaker"],
                "section": segment["section"],
                "source_line": segment["source_line"],
                "quote": sentence,
            })

    return rows

def compare_transcripts(
    previous_text,
    current_text,
    management_speakers=None,
):
    previous = analyze_text(previous_text)
    current = analyze_text(current_text)

    speaker_scope = "all detected speakers"
    selected_speakers = None
    comparison_notice = None
    rate_unit = "matches per 1000 speech words"
    if not previous["speakers"] or not current["speakers"]:
        # Compare the same scope in both calls when either speaker layout is unknown.
        previous = analyze_text(previous_text, full_text=True)
        current = analyze_text(current_text, full_text=True)
        speaker_scope = "full transcript text"
        rate_unit = "matches per 1000 transcript words"
        comparison_notice = (
            "Speaker headings could not be identified in one or both transcripts. "
            "The comparison uses the full text of both calls."
        )
        if management_speakers:
            comparison_notice += " The management filter was not applied."
    elif management_speakers is not None:
        try:
            filtered_previous = filter_speakers(previous, management_speakers)
            filtered_current = filter_speakers(current, management_speakers)
        except ValueError as error:
            comparison_notice = f"{error} Both calls include all detected speakers."
        else:
            previous, current = filtered_previous, filtered_current
            speaker_scope = "selected management speakers"
            selected_speakers = management_speakers

    comparisons = {}

    for section in ("overall", "prepared", "qa"):
        previous_group = previous["language_summary"][section]
        current_group = current["language_summary"][section]

        previous_language = previous_group["language"]
        current_language = current_group["language"]

        available = (
            previous_language["token_count"] > 0
            and current_language["token_count"] > 0
        )

        metrics = {}

        for category in ("positive", "negative", "uncertainty"):
            previous_rate = (
                previous_language["rates_per_1000_words"][category]
            )
            current_rate = (
                current_language["rates_per_1000_words"][category]
            )

            metrics[category] = {
                "previous_rate": previous_rate,
                "current_rate": current_rate,
                "change": (
                    round(current_rate - previous_rate, 2)
                    if available else None
                ),
                "previous_evidence": find_evidence(
                    previous, section, category
                ),
                "current_evidence": find_evidence(
                    current, section, category
                ),
            }

        comparisons[section] = {
            "comparison_available": available,
            "previous_token_count": previous_language["token_count"],
            "current_token_count": current_language["token_count"],
            "metrics": metrics,
        }

    return {
        "rate_unit": rate_unit,
        "change_definition": "current minus previous",
        "speaker_scope": speaker_scope,
        "selected_speakers": selected_speakers,
        "comparison_notice": comparison_notice,
        "comparisons": comparisons,
        "guidance": {
            "previous": extract_guidance(previous) if previous["speakers"] else [],
            "current": extract_guidance(current) if current["speakers"] else [],
        },
        "previous": previous,
        "current": current,
    }
