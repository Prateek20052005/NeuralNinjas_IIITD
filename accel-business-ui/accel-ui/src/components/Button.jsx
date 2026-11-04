import './Button.css';

/**
 * variant: 'primary' | 'secondary' | 'plain' | 'destructive' | 'trust'
 * Renders an <a> when `href` is given, otherwise a <button>.
 */
export default function Button({
  variant = 'primary',
  block = false,
  size = 'md',
  icon: Icon,
  href,
  children,
  className = '',
  type = 'button',
  ...rest
}) {
  const cls = ['ab-btn', `ab-btn--${variant}`, size === 'sm' && 'ab-btn--sm', block && 'ab-btn--block', className]
    .filter(Boolean)
    .join(' ');
  const content = (
    <>
      {Icon ? <Icon size={size === 'sm' ? 16 : 18} strokeWidth={1.75} aria-hidden="true" /> : null}
      {children}
    </>
  );
  if (href) {
    return (
      <a className={cls} href={href} {...rest}>
        {content}
      </a>
    );
  }
  return (
    <button className={cls} type={type} {...rest}>
      {content}
    </button>
  );
}
