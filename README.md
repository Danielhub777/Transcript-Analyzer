# EarningsScope

EarningsScope compares two earnings-call transcripts from the same company. Upload an earlier and a later call to see changes in positive, negative, and uncertainty language, read the passages behind the counts, and inspect numerical guidance alongside its source quotes.

Earnings calls are long, and forecasts can look comparable even when their periods, reporting bases, or currency assumptions differ. The dashboard gives analysts a quick way to find changes worth reading in context.

## How it works

1. The FastAPI backend accepts UTF-8 TXT files and PDFs with selectable text. It extracts PDF text with pypdf and attempts to identify speakers, prepared remarks, and Q&A.
2. The Python analytics package counts exact matches against the Loughran–McDonald positive, negative, and uncertainty word lists. It reports matches per 1,000 words and subtracts the earlier call's rate from the later call's rate. Evidence cards show up to three passages per category, call, and section, ranked by match count.
3. The optional speaker filter applies to both calls. If speaker headings are unavailable, both calls are compared using their full text. If the requested names cannot be matched in both parsed calls, the comparison includes all detected speakers and shows a notice.
4. Separate rules extract explicit numerical guidance and retain the quote, speaker, source line, and any identifiable period or basis. The cards show the outlooks as stated in each call.

The React dashboard in `apps/web` submits multipart uploads to `/api/compare-files`. During local development, Vite forwards `/api` requests to FastAPI at `127.0.0.1:8000` and removes the prefix. The API lives in `apps/api`, with transcript parsing, scoring, and guidance extraction in `packages/analytics`.

## Run locally

Use Python 3.12 and Node.js 22.12+ with npm. From the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix apps/web ci
```

Download the **Master Dictionary CSV** from [Notre Dame's Loughran–McDonald dictionary page](https://sraf.nd.edu/loughranmcdonald-master-dictionary/). From the repository root, put it at `data/dictionaries/loughran_mcdonald.csv`. The backend loads it at startup and requires the `Word`, `Positive`, `Negative`, and `Uncertainty` columns.

```powershell
New-Item -ItemType Directory -Force data/dictionaries
Copy-Item "$env:USERPROFILE/Downloads/Loughran-McDonald_MasterDictionary_1993-2025.csv" data/dictionaries/loughran_mcdonald.csv
```

Run the API in one terminal and Vite in another, both from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
npm --prefix apps/web run dev -- --host 127.0.0.1
```

Open the [dashboard](http://127.0.0.1:5173) or the [FastAPI docs](http://127.0.0.1:8000/docs). For frontend checks, run `npm --prefix apps/web run lint` and `npm --prefix apps/web run build`. For a backend startup check with the dictionary installed, run `.\.venv\Scripts\python.exe -c "from apps.api.main import app; print(app.title)"`.

## Junior seminar demo: Microsoft FY2026 Q2 → Q3

1. Open the official [FY2026 Q2 call](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q2) and [FY2026 Q3 call](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3). Copy each page's **Transcript** section into a UTF-8 text file. Keep the speaker labels and paragraph breaks. Save them locally as `data/raw/transcripts/MSFT_FY2026_Q2.txt` and `data/raw/transcripts/MSFT_FY2026_Q3.txt`.
2. In the dashboard, upload Q2 as **Previous quarter** and Q3 as **Current quarter**. Enter `Satya Nadella, Amy Hood` in **Management speakers**, then select **Compare quarters**.
3. In **Management Guidance**, look in the current-call column for two separate **Q4 M365 Commercial Cloud revenue growth** cards. Both forecasts are in constant currency. Open **Read the source quote** on each card for Amy Hood's full statement and its context.

| Basis | Q4 outlook | Source quote excerpt |
| --- | --- | --- |
| Adjusted | 15%–16%, constant currency | “between 15% and 16% in constant currency” |
| Reported | 13%–14%, constant currency | “on a reported basis, we expect revenue growth to be between 13% and 14% in constant currency” |

Source: [Microsoft FY2026 Q3 earnings call, Amy Hood's Q4 outlook](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3). These are two reporting bases for guidance given on the same call. Comparing them illustrates why period, basis, and source evidence matter.

To reproduce through the API with the same inputs:

```powershell
curl.exe --fail-with-body http://127.0.0.1:8000/compare-files -F "previous_file=@data/raw/transcripts/MSFT_FY2026_Q2.txt" -F "current_file=@data/raw/transcripts/MSFT_FY2026_Q3.txt" -F "management_speakers=Satya Nadella, Amy Hood"
```

## Data and limitations

- Obtain earnings-call transcripts from the issuing company's investor relations website. Keep local transcripts and generated JSON under the ignored data directories. Notre Dame makes the dictionary available for academic research and lists a separate commercial licensing contact. Obtain it from the publisher and check the applicable terms. Third-party inputs and transcript-derived exports are excluded from the public source tree.
- Speaker identification and guidance extraction use rules, so unfamiliar layouts or phrasing may reduce coverage. Scanned PDFs need OCR before upload. Section comparisons require detected speech in that section in both calls.
- Dictionary matches measure word frequency. Context, negation, and meaning still require human review. Guidance cards may omit ambiguous forecasts and leave unclear period, business scope, or reporting basis fields blank.
- **Verified examples:** Microsoft FY2026 Q2 → Q3 TXT uploads returned the two cards above with the management filter. Meta Q2 → Q3 2026 text-based PDFs returned four guidance rows per call with a blank filter, including Susan Li's Q3 revenue outlook of $61–64 billion and Q4 outlook of $73–76 billion.
- **Planned:** saved comparisons, historical return backtesting, and evaluation of whether transcript signals add predictive value.
