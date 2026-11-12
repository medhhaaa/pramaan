// One fact on the timeline. Values are shown exactly as written in the document.
import { describeWithStatus, typeLabel } from "../format";
import { useT } from "../i18n";
import Chip from "./Chip";

export default function FactCard({ fact, original, selected, onSelect }) {
  const t = useT();
  const isEcho = Boolean(fact.echo_of);

  return (
    <li
      className={`fact ${isEcho ? "fact-echo" : ""} ${selected ? "fact-selected" : ""}`}
      onClick={() => onSelect(fact)}
      title={t("fact.clickHint")}
    >
      <div className="fact-main">
        <span className="fact-type">{typeLabel(fact.type, t)}</span>
        <span className={fact.status === "negated" ? "fact-negated" : ""}>
          {describeWithStatus(fact, t)}
        </span>
        {fact.action && <small> ({t(`action.${fact.action}`, null, fact.action)})</small>}
      </div>

      <div className="fact-meta">
        <span>{fact.event_date || t("fact.noDate")}</span>
        {fact.event_date !== fact.document_date && (
          <small> · {t("fact.written", { date: fact.document_date })}</small>
        )}
        {fact.date_raw && <small> · {t("fact.asWritten", { raw: fact.date_raw })}</small>}
      </div>

      <div className="chips">
        <Chip kind="status" value={fact.status} />
        {fact.badge && <Chip kind="badge" value={fact.badge} />}
        {fact.flags.map((flag) => (
          <Chip key={flag} kind="flag" value={flag} />
        ))}
        {fact.corrected && <Chip kind="badge" value="corrected" />}
      </div>

      {isEcho && (
        <div className="fact-echo-note">
          {t("fact.copyOf", {
            what: original ? `${original.document_id} (${original.document_date})` : fact.echo_of,
          })}
        </div>
      )}
    </li>
  );
}
