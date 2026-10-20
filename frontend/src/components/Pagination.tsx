import { Icon } from "./Icon";

interface Props {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}

export function Pagination({ total, limit, offset, onChange }: Props) {
  if (total <= limit) return null;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.ceil(total / limit);
  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        disabled={offset === 0}
        onClick={() => onChange(offset - limit)}
      >
        <Icon name="back" size={14} /> Previous
      </button>
      <span className="muted">
        Page {page} of {pages} · {total} results
      </span>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        disabled={offset + limit >= total}
        onClick={() => onChange(offset + limit)}
      >
        Next <Icon name="arrowRight" size={14} />
      </button>
    </nav>
  );
}
