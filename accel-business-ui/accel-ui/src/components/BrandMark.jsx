import './BrandMark.css';

/** Accel Business mark: vermilion tile, forward "A", marigold dot. Fictional brand. */
export default function BrandMark({ size = 32, withWordmark = true }) {
  return (
    <span className="ab-mark">
      <span className="ab-mark__tile" style={{ width: size, height: size, borderRadius: size * 0.28 }}>
        <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 32 32" aria-hidden="true">
          <path d="M7 24 16 8l9 16" fill="none" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M11.5 18h9" fill="none" stroke="#fff" strokeWidth="3.6" strokeLinecap="round" />
          <circle cx="25" cy="8" r="3.4" fill="#F2A900" />
        </svg>
      </span>
      {withWordmark ? (
        <span className="ab-mark__word">
          accel <small>business</small>
        </span>
      ) : (
        <span className="visually-hidden">Accel Business</span>
      )}
    </span>
  );
}
