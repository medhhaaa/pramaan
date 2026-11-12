// Patient: share my records with a doctor for a short time.
// The backend makes a QR code and an 8-character code. A doctor scans or types it and can
// READ these records until the time runs out; then access closes by itself.
import { useCallback, useEffect, useState } from "react";
import { createShare, getShares, stopShare } from "../api";
import Countdown from "../components/Countdown";

const TIME_CHOICES = [5, 15, 30, 60];

export default function SharePage({ patient }) {
  const [minutes, setMinutes] = useState(15);
  const [share, setShare] = useState(null); // the share just made (has the QR and code)
  const [active, setActive] = useState([]); // all shares still running
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    getShares(patient.id).then(setActive).catch((err) => setError(err.message));
  }, [patient.id]);

  // check every 5 seconds, so the patient sees when a doctor opens the share
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function make() {
    setBusy(true);
    setError("");
    try {
      setShare(await createShare(patient.id, minutes));
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function stop(shareId) {
    try {
      await stopShare(shareId);
      if (share?.share_id === shareId) setShare(null);
      refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  const onShareEnd = useCallback(() => {
    setShare(null);
    refresh();
  }, [refresh]);

  const current = share && active.find((a) => a.share_id === share.share_id);

  return (
    <section className="share-page">
      <h1>Share my records</h1>
      <p className="hint">
        A doctor scans the QR code or types the code. They can only <strong>read</strong> your
        records, only until the time runs out. You can stop sharing at any time.
      </p>

      {!share && (
        <div className="share-create">
          <label>
            Share for{" "}
            <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
              {TIME_CHOICES.map((m) => (
                <option key={m} value={m}>{m} minutes</option>
              ))}
            </select>
          </label>
          <button className="btn-primary" onClick={make} disabled={busy}>
            {busy ? "Making QR..." : "Make QR code"}
          </button>
        </div>
      )}

      {share && (
        <div className="share-card">
          <img src={share.qr_svg} alt="QR code for the doctor to scan" className="share-qr" />
          <div className="share-details">
            <p>Or tell the doctor this code:</p>
            <p className="share-code">{share.code}</p>
            <p>
              Ends in <Countdown expiresAt={share.expires_at} onEnd={onShareEnd} />
            </p>
            <p className={current?.opened_by ? "ok" : "hint"}>
              {current?.opened_by ? `Opened by ${current.opened_by}` : "Not opened yet"}
            </p>
            <button className="btn-secondary" onClick={() => stop(share.share_id)}>Stop sharing</button>
          </div>
        </div>
      )}

      {error && <p className="error">{error}</p>}

      {active.filter((a) => a.share_id !== share?.share_id).length > 0 && (
        <>
          <h2>Other active shares</h2>
          <ul className="list">
            {active
              .filter((a) => a.share_id !== share?.share_id)
              .map((a) => (
                <li key={a.share_id}>
                  <div>
                    {a.opened_by ? `Opened by ${a.opened_by}` : "Not opened yet"} · ends in{" "}
                    <Countdown expiresAt={a.expires_at} onEnd={refresh} />
                  </div>
                  <button className="btn-secondary" onClick={() => stop(a.share_id)}>Stop sharing</button>
                </li>
              ))}
          </ul>
        </>
      )}
    </section>
  );
}
