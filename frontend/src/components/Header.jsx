// Top bar: app name, language switch, who is logged in, and logout.
import { LANGUAGES, useT } from "../i18n";

export default function Header({ user, onLogout, onChangeLanguage }) {
  const t = useT();
  return (
    <header className="header">
      <strong>Pramaan</strong>
      {user && (
        <span className="header-user">
          {user.language && (
            <select
              aria-label={t("language")}
              value={user.language}
              onChange={(e) => onChangeLanguage(e.target.value).catch((err) => alert(err.message))}
            >
              {LANGUAGES.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          )}{" "}
          {user.username} ({t(`role.${user.role}`)}){" "}
          <button className="btn-secondary" onClick={onLogout}>{t("logout")}</button>
        </span>
      )}
    </header>
  );
}
