import { useState } from "react";
import "./App.css";

const categories = ["positive", "negative", "uncertainty"];
const callLabels = { previous: "Previous call", current: "Current call" };

function formatNumber(value) {
  return value == null ? "—" : value.toFixed(2);
}

function sectionLabel(section) {
  if (section === "qa") return "Q&A";
  if (section === "prepared") return "Prepared remarks";
  return "Section not identified";
}

function GuidancePanel({ result }) {
  return (
    <section className="panel" aria-labelledby="guidance-heading">
      <div className="section-header">
        <h2 id="guidance-heading">Management Guidance</h2>
      </div>

      <p className="muted">
        Check the forecast period, business segment, and reporting basis before
        treating a difference as a guidance revision.
      </p>

      <div className="evidence-grid">
        {Object.entries(callLabels).map(([period, label]) => {
          const rows = result.guidance?.[period] ?? [];

          return (
            <div key={period}>
              <h3 className="period-title">{label}</h3>
              <p className="muted">{result[`${period}_file`]}</p>

              {rows.length === 0 && (
                <p className="muted">No guidance extracted for this call.</p>
              )}

              {rows.map((row, index) => {
                const basis = [row.reporting_basis, row.currency_basis]
                  .filter(Boolean)
                  .join(" · ");

                return (
                  <article
                    className="quote-card"
                    key={`${row.source_line}-${row.metric}-${index}`}
                  >
                    <h4>
                      {row.business_scope ?? "Scope not identified"} · {row.metric}
                    </h4>
                    <div className="metric-value">{row.outlook}</div>
                    {basis && <p className="muted">{basis}</p>}
                    <p className="muted">
                      {row.forecast_period ?? "Period not identified"}
                    </p>

                    <details>
                      <summary>Read the source quote</summary>
                      <p>{row.quote}</p>

                      {row.scope_context && (
                        <p className="muted">
                          Segment context: {row.scope_context}
                        </p>
                      )}

                      {row.period_context && (
                        <p className="muted">
                          Forecast period context: {row.period_context}
                        </p>
                      )}

                      <small>
                        {row.speaker} · {sectionLabel(row.section)}
                        {Number.isInteger(row.source_line) &&
                          ` · Line ${row.source_line + 1}`}
                      </small>
                    </details>
                  </article>
                );
              })}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default function App() {
  const [previousFile, setPreviousFile] = useState(null);
  const [currentFile, setCurrentFile] = useState(null);
  const [speakers, setSpeakers] = useState("");
  const [section, setSection] = useState("overall");
  const [category, setCategory] = useState("uncertainty");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleCompare(event) {
    event.preventDefault();
    if (!previousFile || !currentFile) return;

    setError("");
    setResult(null);
    setLoading(true);

    const form = new FormData();
    form.append("previous_file", previousFile);
    form.append("current_file", currentFile);
    form.append("management_speakers", speakers);

    try {
      const response = await fetch("/api/compare-files", {
        method: "POST",
        body: form,
      });
      const data = await response.json().catch(() => null);

      if (!response.ok || !data?.comparisons) {
        throw new Error(
          typeof data?.detail === "string"
            ? data.detail
            : "Comparison failed. Check that FastAPI is running and try again."
        );
      }

      setSection("overall");
      setResult(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to compare transcripts."
      );
    } finally {
      setLoading(false);
    }
  }

  const comparison = result?.comparisons?.[section];
  const evidence = comparison?.metrics?.[category];
  const fullText = result?.speaker_scope === "full transcript text";
  const wordUnit = fullText ? "transcript words" : "speech words";

  return (
    <main className="dashboard">
      <header className="hero">
        <span className="badge">EARNINGS CALL RESEARCH</span>
        <h1>EarningsScope<span>.</span></h1>
        <p>See how the language changes. Read the evidence behind it.</p>
      </header>

      <section className="panel">
        <h2>Compare two quarters</h2>
        <p className="muted">
          Upload two calls from the same company, earlier quarter first.
        </p>

        <form onSubmit={handleCompare}>
          <div className="upload-grid">
            <label className="upload-card">
              <span className="step">01</span>
              <strong>Previous quarter</strong>
              <span className="muted">Select a .txt or .pdf transcript</span>
              <input
                type="file"
                accept=".txt,.pdf"
                required
                disabled={loading}
                onChange={(event) =>
                  setPreviousFile(event.target.files?.[0] ?? null)
                }
              />
            </label>

            <label className="upload-card">
              <span className="step">02</span>
              <strong>Current quarter</strong>
              <span className="muted">Select a .txt or .pdf transcript</span>
              <input
                type="file"
                accept=".txt,.pdf"
                required
                disabled={loading}
                onChange={(event) =>
                  setCurrentFile(event.target.files?.[0] ?? null)
                }
              />
            </label>
          </div>

          <label className="speaker-field">
            <strong>Management speakers · optional</strong>
            <input
              type="text"
              value={speakers}
              disabled={loading}
              placeholder="SATYA NADELLA, AMY HOOD"
              onChange={(event) => setSpeakers(event.target.value)}
            />
            <span className="muted">
              Separate names with commas. Leave blank to include all speakers.
            </span>
          </label>

          <button
            className="primary-button"
            disabled={loading || !previousFile || !currentFile}
          >
            {loading ? "Comparing transcripts…" : "Compare quarters →"}
          </button>
        </form>

        {error && <p className="error" role="alert">{error}</p>}
      </section>

      {result && !fullText && <GuidancePanel result={result} />}

      {comparison && (
        <section className="panel">
          <div className="section-header">
            <div>
              <h2>Language changes</h2>
              <p className="muted">
                {result.previous_file} → {result.current_file}
              </p>
              <p className="muted">Scope: {result.speaker_scope}</p>
            </div>

            <label>
              <span className="control-label">Call section</span>
              <select value={section} onChange={(event) => setSection(event.target.value)}>
                <option value="overall">Overall</option>
                <option value="prepared" disabled={!result.comparisons.prepared.comparison_available}>Prepared remarks</option>
                <option value="qa" disabled={!result.comparisons.qa.comparison_available}>Q&A</option>
              </select>
            </label>
          </div>

          {result.comparison_notice && (
            <p className="notice" role="status">{result.comparison_notice}</p>
          )}

          <p className="muted">
            {comparison.previous_token_count.toLocaleString()}
            {" previous · "}
            {comparison.current_token_count.toLocaleString()} current {wordUnit}
          </p>

          {!comparison.comparison_available && (
            <p className="notice">
              This section has no detected speech in one or both transcripts.
              Its change cannot be calculated.
            </p>
          )}

          <div className="metric-grid">
            {categories.map((name) => {
              const metric = comparison.metrics[name];

              return (
                <article className="metric-card" key={name}>
                  <h3>{name}</h3>
                  <div className="metric-value">
                    {metric.change > 0 ? "+" : ""}
                    {formatNumber(metric.change)}
                  </div>
                  <p>Change per 1,000 {wordUnit}</p>
                  <div className="rate-row">
                    <span>Previous <b>{formatNumber(metric.previous_rate)}</b></span>
                    <span>Current <b>{formatNumber(metric.current_rate)}</b></span>
                  </div>
                </article>
              );
            })}
          </div>

          <p className="method-note">
            Dictionary matches per 1,000 {wordUnit}. Changes are current
            minus previous.
          </p>
        </section>
      )}

      {evidence && (
        <section className="panel">
          <div className="section-header">
            <div>
              <h2>Read the evidence</h2>
              <p className="muted">Paragraphs ranked by matching-word count.</p>
            </div>

            <label>
              <span className="control-label">Language category</span>
              <select value={category} onChange={(event) => setCategory(event.target.value)}>
                {categories.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="evidence-grid">
            {Object.entries(callLabels).map(([period, label]) => {
              const quotes = evidence[`${period}_evidence`] ?? [];

              return (
                <div key={period}>
                  <h3 className="period-title">{label}</h3>
                  {quotes.length === 0 && (
                    <p className="muted">No matching paragraphs.</p>
                  )}

                  {quotes.map((quote, index) => (
                    <article
                      className="quote-card"
                      key={`${quote.source_line}-${quote.speaker}-${index}`}
                    >
                      <strong>{quote.speaker ?? "Speaker not identified"}</strong>
                      <p>{quote.text}</p>
                      <small>
                        Line {quote.source_line + 1} · {sectionLabel(quote.section)}
                        {" · "}{quote.match_count} matches
                      </small>
                      <div className="word-tags">
                        {quote.matched_words.map((word) => (
                          <span key={word}>{word}</span>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {!result && !loading && (
        <p className="empty-state">
          Your quarter comparison and supporting quotes will appear here.
        </p>
      )}
    </main>
  );
}
