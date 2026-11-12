// Things to Check (patient): plain-language questions about gaps, conflicts and copied medicines.
// Yes / No / a value -> answered (patient reported). I don't know / Skip -> sent to the doctor.
import { useEffect, useState } from "react";
import { answerQuestion, getQuestions } from "../api";

const STATUS_TEXT = {
  answered: "You answered",
  sent_to_doctor: "Sent to your doctor",
  resolved: "Resolved by your doctor",
};

function answerText(a) {
  if (!a) return "";
  const labels = { yes: "Yes", no: "No", dont_know: "I don't know", skip: "Skipped", confirm: "Confirmed", correct: "Corrected", unclear: "Marked unclear" };
  return a.answer === "value" ? `"${a.value}"` : labels[a.answer] || a.answer;
}

function QuestionCard({ question, onAnswered }) {
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
          From your records:{" "}
          {question.facts.map((f) => `"${f.quote}" (${f.event_date})`).join(" · ")}
        </p>
      )}
      <div className="answer-buttons">
        <button onClick={() => send("yes")} disabled={busy}>Yes</button>
        <button onClick={() => send("no")} disabled={busy}>No</button>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="or type an answer"
          maxLength={500}
        />
        <button className="btn-primary" onClick={() => send("value")} disabled={busy || !value.trim()}>Send</button>
        <button onClick={() => send("dont_know")} disabled={busy}>I don't know</button>
        <button onClick={() => send("skip")} disabled={busy}>Skip</button>
      </div>
      {error && <p className="error">{error}</p>}
    </li>
  );
}

export default function ThingsToCheckPage({ patient }) {
  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuestions(patient.id).then(setQuestions).catch((err) => setError(err.message));
  }, [patient.id]);

  function handleAnswered(updated) {
    setQuestions((prev) => prev.map((q) => (q.id === updated.id ? updated : q)));
  }

  if (error) return <p className="error">{error}</p>;
  if (!questions) return <p>Loading...</p>;

  const open = questions.filter((q) => q.status === "open");
  const done = questions.filter((q) => q.status !== "open");

  return (
    <section>
      <h1>Things to check</h1>
      <p className="hint">
        Pramaan found places where your records are unclear. Your answers help your doctor. If you
        are not sure, choose "I don't know" and your doctor will look at it.
      </p>
      {open.length === 0 ? (
        <p className="ok">Nothing to check right now.</p>
      ) : (
        <ul className="questions">
          {open.map((q) => (
            <QuestionCard key={q.id} question={q} onAnswered={handleAnswered} />
          ))}
        </ul>
      )}

      {done.length > 0 && (
        <>
          <h2>Already handled</h2>
          <ul className="questions">
            {done.map((q) => (
              <li key={q.id} className="question question-done">
                <p>{q.text}</p>
                <p className="hint">
                  {STATUS_TEXT[q.status]}: {answerText(q.answer)}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
