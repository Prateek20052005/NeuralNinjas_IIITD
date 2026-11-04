import { Moon, Shield, Sun } from 'lucide-react';

/** Trailing header buttons on every owner screen: "Your data" (once there is an application) and light/dark. */
export default function HeaderActions({ tr, theme, onTheme, onPrivacy, extra }) {
  const dark = theme === 'dark';
  return (
    <>
      {extra}
      {onPrivacy ? (
        <button type="button" className="ab-icon-btn" aria-label={tr('ui.privacy_open')} title={tr('ui.privacy_open')} onClick={onPrivacy}>
          <Shield size={21} strokeWidth={1.75} aria-hidden="true" />
        </button>
      ) : null}
      <button type="button" className="ab-icon-btn" aria-label={tr(dark ? 'ui.dark_off' : 'ui.dark_on')}
              title={tr(dark ? 'ui.dark_off' : 'ui.dark_on')} onClick={onTheme}>
        {dark ? <Sun size={21} strokeWidth={1.75} aria-hidden="true" /> : <Moon size={21} strokeWidth={1.75} aria-hidden="true" />}
      </button>
    </>
  );
}
