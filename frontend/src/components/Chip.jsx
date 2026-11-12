// Small coloured label for flags, badges and status. Colour comes from the CSS class;
// the label is "chip.<value>" in i18n.jsx.
import { useT } from "../i18n";

export default function Chip({ kind, value }) {
  const t = useT();
  return <span className={`chip chip-${kind} chip-${value}`}>{t(`chip.${value}`, null, value)}</span>;
}
