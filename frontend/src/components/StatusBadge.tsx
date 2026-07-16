import { statusStyle } from '../palette';

export function StatusBadge({ status }: { status?: string | null }) {
  const s = statusStyle(status);
  return (
    <span
      style={{
        display: 'inline-block',
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.01em',
        padding: '2px 8px',
        borderRadius: 999,
        background: s.bg,
        color: s.fg,
        whiteSpace: 'nowrap',
      }}
    >
      {s.label}
    </span>
  );
}
