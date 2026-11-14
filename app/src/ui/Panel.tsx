// A screen that opens over the Plan or Walk view (the Drone fix and Target preview, P1-09).
import { useEffect, type ReactNode } from "react";

interface Props {
  title: string;
  label?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

export function Panel({ title, label, onClose, children }: Props) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <section className="panel" role="dialog" aria-label={title} onClick={(event) => event.stopPropagation()}>
        <header className="panel__head">
          <h2 className="panel__title">{title}</h2>
          {label}
          <button type="button" className="panel__close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
