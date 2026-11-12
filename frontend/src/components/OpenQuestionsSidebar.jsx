// Doctor's Open Questions sidebar: everything not yet resolved, "I don't know" / Skip first.
// Confirm: the doctor confirms one fact as correct -> correction record -> doctor_verified.
// Correct: the doctor changes a fact (original kept) -> doctor_verified.
// Mark unclear: resolved without changing any fact.
import { useEffect, useState } from "react";
import { answerQuestion, correctFact, getQuestions } from "../api";
import { describeWithStatus } from "../format";
import { useT } from "../i18n";
import CorrectionForm from "./CorrectionForm";

const ORDER = { sent_to_doctor: 0, answered: 1, open: 2 };

function patientAnswer(a, t) {
  if (!a || a.role !== "patient") return null;
  return a.answer === "value" ? `"${a.value}"` : t(`answered.${a.answer}`, null, a.answer);
}

function OpenQuestion({ question, user, onResolved }) {
  const t = useT();
  const [correcting, setCorrecting] = useState(null); // fact being corrected
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(action) {
    setBusy(true);
    setError("");
    try {
      await action();
      onResolved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  // confirming = a correction record with the value unchanged, so the fact becomes doctor_verified
  const confirm = (fact) =>
    run(async () => {
      await correctFact(fact.fact_id, "status", fact.status);
      await answerQuestion(question.id, "confirm", fact.fact_id);
    });

  const markUnclear = () => run(() => answerQuestion(question.id, "unclear"));

  const answer = patientAnswer(question.answer, t);

  return (
    <li className="question">
      <p className="hint">
        {t(`oq.status.${question.status}`)}
        {answer && `: ${answer}`}
      </p>
      <p>{question.text}</p>
      <ul className="oq-facts">
        {question.facts.map((f) => (
          <li key={f.fact_id}>
            <span>
              {describeWithStatus(f, t)} <small>({f.document_id}, {f.event_date})</small>
            </span>
            <span className="oq-actions">
              <button className="btn-primary" onClick={() => confirm(f)} disabled={busy}>{t("oq.confirm")}</button>{" "}
              <button className="btn-secondary" onClick={() => setCorrecting(correcting?.fact_id === f.fact_id ? null : f)} disabled={busy}>
                {t("oq.correct")}
              </button>
            </span>
          </li>
        ))}
      </ul>
      {correcting && (
        <CorrectionForm
          fact={correcting}
          user={user}
          onCorrected={(updated) => run(() => answerQuestion(question.id, "correct", updated.fact_id))}
        />
      )}
      <button className="btn-ghost" onClick={markUnclear} disabled={busy}>{t("oq.unclear")}</button>
      {error && <p className="error">{error}</p>}
    </li>
  );
}

export default function OpenQuestionsSidebar({ patient, user, onChange }) {
  const t = useT();
  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    getQuestions(patient.id).then(setQuestions).catch((err) => setError(err.message));
  }, [patient.id, reload, t.lang]); // question text comes from the backend in the user's language

  function handleResolved() {
    setReload((n) => n + 1);
    onChange?.();
  }

  const open = (questions || [])
    .filter((q) => q.status !== "resolved")
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.id - b.id);
  const resolved = (questions || []).filter((q) => q.status === "resolved");

  return (
    <aside className="sidebar">
      <h2>{t("oq.title", { n: open.length })}</h2>
      {error && <p className="error">{error}</p>}
      {!questions && !error && <p>{t("loading")}</p>}
      {questions && open.length === 0 && <p className="ok">{t("oq.none")}</p>}
      <ul className="questions">
        {open.map((q) => (
          <OpenQuestion key={q.id} question={q} user={user} onResolved={handleResolved} />
        ))}
      </ul>
      {resolved.length > 0 && (
        <p className="hint">
          {t("oq.resolved", { n: resolved.length })}{" "}
          {resolved
            .map((q) =>
              t("oq.resolvedItem", {
                id: q.id,
                answer: t(`answered.${q.answer?.answer}`, null, q.answer?.answer),
                by: q.answer?.by,
              }),
            )
            .join(", ")}
        </p>
      )}
    </aside>
  );
}
