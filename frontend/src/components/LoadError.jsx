import { useTranslation } from 'react-i18next';

// Shown instead of an endless loading skeleton when a request fails.
// message: the backend's own detail or "HTTP 500", shown small under the plain-language line.
export default function LoadError({ message }) {
  const { t } = useTranslation();
  return (
    <div className="empty-state card" role="alert">
      <p className="error-text">{t('common.error')}</p>
      {message && <p className="muted small mono">{message}</p>}
    </div>
  );
}
