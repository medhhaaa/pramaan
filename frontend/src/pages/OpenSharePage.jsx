// Doctor: open records a patient shared by QR code or typed code.
// Access is read-only and ends when the patient's chosen time runs out.
import { useCallback, useEffect, useRef, useState } from "react";
import { openShare } from "../api";
import QrScanner from "../components/QrScanner";

// the QR holds a link like http://localhost:5173/?share=<token>; anything else is a code
function readScan(text) {
  try {
    const token = new URL(text).searchParams.get("share");
    if (token) return { token };
  } catch {
    // not a link
  }
  return { code: text };
}

export default function OpenSharePage({ initialToken, onOpened }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const triedLink = useRef(false);

  const open = useCallback(
    async (what) => {
      setBusy(true);
      setError("");
      try {
        const res = await openShare(what);
        onOpened({ ...res.patient, shared_until: res.expires_at });
      } catch (err) {
        setError(err.message);
        setBusy(false);
      }
    },
    [onOpened],
  );

  // opened from a scanned link (?share=...): use its token straight away
  useEffect(() => {
    if (initialToken && !triedLink.current) {
      triedLink.current = true;
      open({ token: initialToken });
    }
  }, [initialToken, open]);

  const onScan = useCallback((text) => open(readScan(text)), [open]);

  function submit(e) {
    e.preventDefault();
    if (code.trim()) open({ code });
  }

  return (
    <section className="share-page">
      <h1>Open shared records</h1>
      <p className="hint">
        Scan the patient's QR code, or type the code they tell you. You will be able to read
        their records until the time they chose runs out.
      </p>

      <QrScanner onResult={onScan} />

      <form className="share-code-form" onSubmit={submit}>
        <label>
          Code
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="ABCD-2345"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
          />
        </label>
        <button type="submit" disabled={busy || !code.trim()}>
          {busy ? "Opening..." : "Open"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}
    </section>
  );
}
