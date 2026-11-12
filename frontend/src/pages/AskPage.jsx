// Ask My Records: answers come only from stored facts, each with clickable citations.
import { useState } from "react";
import { askRecords, NOT_DOCUMENTED_ANSWERS } from "../api";
import ProofPanel from "../components/ProofPanel";
import { describeWithStatus } from "../format";
import { useT } from "../i18n";

export default function AskPage({ patient }) {
  const t = useT();
  const examples = [t("ask.ex1"), t("ask.ex2"), t("ask.ex3")];
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
        <h1>{t("ask.title", { name: patient.name })}</h1>
        <p className="hint">{t("ask.hint")}</p>
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
            placeholder={t("ask.placeholder")}
            maxLength={500}
          />
          <button type="submit" disabled={busy || !question.trim()}>
            {busy ? t("ask.busy") : t("ask.button")}
          </button>
        </form>
        <p className="hint">
          {t("ask.try")}{" "}
          {examples.map((ex) => (
            <button key={ex} className="link" onClick={() => ask(ex)} disabled={busy}>
              {ex}
            </button>
          ))}
        </p>
        {error && <p className="error">{error}</p>}

        {history.map((item, i) => (
          <div key={history.length - i} className="answer">
            <p>
              <strong>{t("ask.q")}</strong> {item.question}
            </p>
            <p className={NOT_DOCUMENTED_ANSWERS.includes(item.answer) ? "not-documented" : ""}>
              <strong>{t("ask.a")}</strong> {item.answer}
            </p>
            {item.citations.length > 0 && (
              <>
                <p className="hint">{t("ask.sources")}</p>
                <ul className="citations">
                  {item.citations.map((f) => (
                    <li key={f.fact_id}>
                      <button className="link" onClick={() => setSelected(f)}>
                        [{f.fact_id}] {describeWithStatus(f, t)}, {f.event_date}
                        {f.echo_of ? t("ask.copy") : ""}
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
