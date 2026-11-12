import { useState } from "react";
import { login } from "../api";
import { useT } from "../i18n";

export default function LoginPage({ onLogin }) {
  const t = useT();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data = await login(username.trim(), password);
      onLogin({ username: data.username, role: data.role, language: data.language });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="auth-card">
      <h1>{t("login.title")}</h1>
      <form onSubmit={handleSubmit} className="form">
        <label>
          {t("login.username")}
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          {t("login.password")}
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button type="submit" disabled={busy || !username || !password}>
          {busy ? t("login.busy") : t("login.button")}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
      <p className="hint">{t("login.demo")}</p>
    </section>
  );
}
