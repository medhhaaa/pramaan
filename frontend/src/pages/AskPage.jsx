// Ask My Records: answers come only from stored facts, each with clickable citations.
import { useState } from "react";
import { askRecords, NOT_DOCUMENTED_ANSWER } from "../api";
import ProofPanel from "../components/ProofPanel";
import { describeWithStatus } from "../format";

const EXAMPLES = ["Is she allergic to anything?", "What is the latest HbA1c?", "Does she smoke?"];

export default function AskPage({ patient }) {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState([]); // [{question, answer, citations}] newest first
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  async function ask(q) {
    const text = q.trim();
    if (!text) return;
    setBusy(true);
    setError("");
    try {
      const res = await askRecords(patient.id, text);
      setHistory((prev) => [{ question: text, ...res }, ...prev]);
      setQuestion("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={selected ? "with-panel" : ""}>
      <div>
        <h1>Ask my records: {patient.name}</h1>
        <p className="hint">
          Answers use only what is written in the records, with the source of every claim. If the
          records don't say, Pramaan says so instead of guessing.
        </p>
        <form
          className="ask-form"
          onSubmit={(e) => {
            e.preventDefault();
            ask(question);
          }}
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question about the records"
            maxLength={500}
          />
          <button type="submit" disabled={busy || !question.trim()}>
            {busy ? "Checking records..." : "Ask"}
          </button>
        </form>
        <p className="hint">
          Try:{" "}
          {EXAMPLES.map((ex) => (
            <button key={ex} className="link" onClick={() => ask(ex)} disabled={busy}>
              {ex}
            </button>
          ))}
        </p>
        {error && <p className="error">{error}</p>}

        {history.map((item, i) => (
          <div key={history.length - i} className="answer">
            <p>
              <strong>Q:</strong> {item.question}
            </p>
            <p className={item.answer === NOT_DOCUMENTED_ANSWER ? "not-documented" : ""}>
              <strong>A:</strong> {item.answer}
            </p>
            {item.citations.length > 0 && (
              <>
                <p className="hint">Sources (click to see the line in the document):</p>
                <ul className="citations">
                  {item.citations.map((f) => (
                    <li key={f.fact_id}>
                      <button className="link" onClick={() => setSelected(f)}>
                        [{f.fact_id}] {describeWithStatus(f)}, {f.event_date}
                        {f.echo_of ? " (copy)" : ""}
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        ))}
      </div>
      {selected && (
        <ProofPanel key={selected.document_id} fact={selected} onClose={() => setSelected(null)} />
      )}
    </section>
  );
}
