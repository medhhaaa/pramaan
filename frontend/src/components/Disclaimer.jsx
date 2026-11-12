// Shown on every page (CLAUDE.md section 11).
import { useT } from "../i18n";

export default function Disclaimer() {
  const t = useT();
  return <p className="disclaimer">{t("disclaimer")}</p>;
}
