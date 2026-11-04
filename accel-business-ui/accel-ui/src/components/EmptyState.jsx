import './EmptyState.css';

/** Centred illustration slot + title + one line + optional action. Pass an inline SVG as `illustration`. */
export default function EmptyState({ illustration, title, body, action }) {
  return (
    <div className="ab-empty">
      <div className="ab-empty__illo" aria-hidden={illustration ? undefined : true}>
        {illustration}
      </div>
      <h2 className="t-title">{title}</h2>
      {body ? <p className="t-callout t-secondary">{body}</p> : null}
      {action ? <div className="ab-empty__action">{action}</div> : null}
    </div>
  );
}
