import './Chip.css';

/** Wrapping row of chips. `label` names the group for screen readers. */
export default function ChipGroup({ label, scroll = false, children }) {
  return (
    <div className={['ab-chips', scroll && 'ab-chips--scroll'].filter(Boolean).join(' ')} role="group" aria-label={label}>
      {children}
    </div>
  );
}
