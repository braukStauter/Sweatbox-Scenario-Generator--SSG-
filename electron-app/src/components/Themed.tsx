import type React from 'react';
import type { ButtonHTMLAttributes, InputHTMLAttributes, PropsWithChildren } from 'react';

export function ThemedButton({
  secondary,
  className = '',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { secondary?: boolean }) {
  return <button {...rest} className={`themed ${secondary ? 'secondary' : ''} ${className}`} />;
}

export function ThemedInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`themed ${props.className ?? ''}`} />;
}

export function Card({
  children,
  title,
  style,
}: PropsWithChildren<{ title?: string; style?: React.CSSProperties }>) {
  return (
    <div className="card" style={style}>
      {title && <h2 className="heading">{title}</h2>}
      {children}
    </div>
  );
}

export function Section({
  title,
  children,
}: PropsWithChildren<{ title: string }>) {
  return (
    <section className="stack">
      <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: 'var(--fg-secondary)' }}>
        {title}
      </h3>
      {children}
    </section>
  );
}
