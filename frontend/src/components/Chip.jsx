import './Chip.css';

/** One tap-to-answer chip. Put several inside <ChipGroup>. */
export default function Chip({ selected = false, numeric = false, onClick, children, ...rest }) {
  return (
    <button
      type="button"
      className={['ab-chip', selected && 'is-on', numeric && 'ab-chip--num'].filter(Boolean).join(' ')}
      aria-pressed={selected}
      onClick={onClick}
      {...rest}
    >
      {children}
    </button>
  );
}
