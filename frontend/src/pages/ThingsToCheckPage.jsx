// Things to Check (patient): plain-language questions about gaps, conflicts and copied medicines.
// Yes / No / a value -> answered (patient reported). I don't know / Skip -> sent to the doctor.
import { useEffect, useState } from "react";
import { answerQuestion, getQuestions } from "../api";
import { useT } from "../i18n";

function answerText(a, t) {
  if (!a) return "";
  return a.answer === "value" ? `"${a.value}"` : t(`answered.${a.answer}`, null, a.answer);
}

function QuestionCard({ question, onAnswered }) {
  const t = useT();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send(answer) {
    setBusy(true);
    setError("");
    try {
      onAnswered(await answerQuestion(question.id, answer, answer === "value" ? value.trim() : null));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <li className="question">
      <p>{question.text}</p>
      {question.facts.length > 0 && (
        <p className="hint">
          {t("check.fromRecords")}{" "}
          {question.facts.map((f) => `"${f.quote}" (${f.event_date})`).join(" · ")}
        </p>
      )}
      {question.claim_condition ? (
        // hospital stay question (Claim documents): Yes / No / I don't know only
        <div className="answer-buttons">
          <button onClick={() => send("yes")} disabled={busy}>{t("answer.yes")}</button>
          <button onClick={() => send("no")} disabled={busy}>{t("answer.no")}</button>
          <button onClick={() => send("dont_know")} disabled={busy}>{t("answer.dont_know")}</button>
        </div>
      ) : (
      <div className="answer-buttons">
        <button onClick={() => send("yes")} disabled={busy}>{t("answer.yes")}</button>
        <button onClick={() => send("no")} disabled={busy}>{t("answer.no")}</button>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t("check.placeholder")}
          maxLength={500}
        />
        <button className="btn-primary" onClick={() => send("value")} disabled={busy || !value.trim()}>{t("check.send")}</button>
        <button onClick={() => send("dont_know")} disabled={busy}>{t("answer.dont_know")}</button>
        <button onClick={() => send("skip")} disabled={busy}>{t("answer.skip")}</button>
      </div>
      )}
      {error && <p className="error">{error}</p>}
    </li>
  );
}

export default function ThingsToCheckPage({ patient }) {
  const t = useT();
  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuestions(patient.id).then(setQuestions).catch((err) => setError(err.message));
  }, [patient.id, t.lang]); // question text comes from the backend in the user's language

  function handleAnswered(updated) {
    setQuestions((prev) => prev.map((q) => (q.id === updated.id ? updated : q)));
  }

  if (error) return <p className="error">{error}</p>;
  if (!questions) return <p>{t("loading")}</p>;

  const open = questions.filter((q) => q.status === "open");
  const done = questions.filter((q) => q.status !== "open");

  return (
    <section>
      <h1>{t("tab.questions")}</h1>
      <p className="hint">{t("check.hint")}</p>
      {open.length === 0 ? (
        <p className="ok">{t("check.nothing")}</p>
      ) : (
        <ul className="questions">
          {open.map((q) => (
            <QuestionCard key={q.id} question={q} onAnswered={handleAnswered} />
          ))}
        </ul>
      )}

      {done.length > 0 && (
        <>
          <h2>{t("check.handled")}</h2>
          <ul className="questions">
            {done.map((q) => (
              <li key={q.id} className="question question-done">
                <p>{q.text}</p>
                <p className="hint">
                  {t(`check.status.${q.status}`)}: {answerText(q.answer, t)}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
