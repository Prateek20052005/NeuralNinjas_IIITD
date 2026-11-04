import { useState } from 'react';
import { Globe } from 'lucide-react';
import BottomSheet from './BottomSheet.jsx';
import SegmentedControl from './SegmentedControl.jsx';
import Button from './Button.jsx';
import './LanguageSwitcher.css';

export const LANGUAGES = [
  { value: 'en', label: 'English', short: 'EN', lang: 'en' },
  { value: 'hi', label: 'हिंदी', short: 'हिं', lang: 'hi' },
  { value: 'mr', label: 'मराठी', short: 'मरा', lang: 'mr' },
];

/** Header pill showing the current language; opens a sheet to change it. */
export default function LanguageSwitcher({ value, onChange, t = { title: 'Choose language', done: 'Done', change: 'Change language' } }) {
  const [open, setOpen] = useState(false);
  const current = LANGUAGES.find((l) => l.value === value) || LANGUAGES[0];
  return (
    <>
      <button type="button" className="ab-lsw" aria-label={`${t.change}, ${current.label}`} onClick={() => setOpen(true)}>
        <Globe size={18} strokeWidth={1.75} aria-hidden="true" />
        <span lang={current.lang}>{current.short}</span>
      </button>
      <BottomSheet open={open} onClose={() => setOpen(false)} title={t.title}>
        <SegmentedControl label={t.title} options={LANGUAGES} value={value} onChange={onChange} />
        <Button block onClick={() => setOpen(false)}>
          {t.done}
        </Button>
      </BottomSheet>
    </>
  );
}
