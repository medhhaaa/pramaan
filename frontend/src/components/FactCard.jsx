// One fact on the timeline. Values are shown exactly as written in the document.
import { describeWithStatus, typeLabel } from "../format";
import Chip from "./Chip";

export default function FactCard({ fact, original, selected, onSelect }) {
  const isEcho = Boolean(fact.echo_of);

  return (
    <li
      className={`fact ${isEcho ? "fact-echo" : ""} ${selected ? "fact-selected" : ""}`}
      onClick={() => onSelect(fact)}
      title="Click to see the source line"
    >
      <div className="fact-main">
        <span className="fact-type">{typeLabel(fact.type)}</span>
        <span className={fact.status === "negated" ? "fact-negated" : ""}>
          {describeWithStatus(fact)}
        </span>
        {fact.action && <small> ({fact.action})</small>}
      </div>

      <div className="fact-meta">
        <span>{fact.event_date || "date not documented"}</span>
        {fact.event_date !== fact.document_date && (
          <small> · written {fact.document_date}</small>
        )}
        {fact.date_raw && <small> · as written: "{fact.date_raw}"</small>}
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
          Copy of {original ? `${original.document_id} (${original.document_date})` : fact.echo_of}
          : not new evidence
        </div>
      )}
    </li>
  );
}
