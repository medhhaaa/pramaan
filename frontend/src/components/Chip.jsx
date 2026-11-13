import { useTranslation } from 'react-i18next';
import { AlertTriangle, BadgeCheck, Layers, User, Ban, HelpCircle, Copy } from 'lucide-react';

// Evidence state chip: text + icon, never colour alone.
export function StatusChip({ status }) {
  const { t } = useTranslation();
  if (status === 'not_documented') {
    return <span className="chip chip-gap" title={t('status.not_documented')}><HelpCircle size={14} />{t('status.not_documented')}</span>;
  }
  if (status === 'negated') {
    return <span className="chip chip-outline" title={t('status.negated')}><Ban size={14} />{t('status.negated')}</span>;
  }
  return <span className="chip chip-doc" title={t('status.documented')}>{t('status.documented')}</span>;
}

const BADGE_ICON = { doctor_verified: BadgeCheck, independent_2plus: Layers, single_document: null, patient_reported: User, conflicting: AlertTriangle };
const BADGE_CLASS = { doctor_verified: 'chip-verified', independent_2plus: 'chip-info', single_document: 'chip-neutral', patient_reported: 'chip-patient', conflicting: 'chip-danger' };

export function BadgeChip({ badge }) {
  const { t } = useTranslation();
  if (!badge) return null;
  const Icon = BADGE_ICON[badge];
  return (
    <span className={`chip ${BADGE_CLASS[badge]}`} title={t(`badgeTips.${badge}`)}>
      {Icon && <Icon size={14} />}{t(`badges.${badge}`)}
    </span>
  );
}

export function FlagChip({ flag }) {
  const { t } = useTranslation();
  return (
    <span className={`chip ${['ambiguous_date', 'unit_mismatch', 'implausible_value', 'handwriting', 'echo'].includes(flag) ? 'chip-warn' : 'chip-danger'}`} title={t(`flagTips.${flag}`)}>
      <AlertTriangle size={14} />{t(`flagNames.${flag}`)}
    </span>
  );
}

export function CopyChip({ docName }) {
  const { t } = useTranslation();
  return <span className="chip chip-neutral"><Copy size={14} />{t('timeline.copyOf', { doc: docName })}</span>;
}

// Facts read from handwriting: how sure we are the line was read right (0-100).
// Two independent readers (the vision model and Tesseract) read the same line; the score is how
// well they agree. Low = check the fact against the original image.
export function ConfidenceChip({ value }) {
  const { t } = useTranslation();
  if (value == null) return null;
  const cls = value >= 85 ? 'chip-verified' : value >= 60 ? 'chip-warn' : 'chip-danger';
  return (
    <span
      className={`chip ${cls}`}
      title={t('confidence.tip', { defaultValue: 'How closely two independent readers agree on this handwritten line. Check low scores against the original image.' })}
    >
      {t('confidence.label', { defaultValue: 'Read confidence' })} {value}%
    </span>
  );
}
