import type { ReactNode } from "react";

/** A module on the panel: raised surface, engraved border, mono legend. */
export function Panel({
  title,
  right,
  children,
  className = "",
  bodyClassName = "p-4",
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`border border-panel-etch bg-panel-raised ${className}`}>
      {(title || right) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-panel-etch px-4 py-2">
          <h2 className="legend">{title}</h2>
          {right}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

type AnnState = "armed" | "alarm" | "idle" | "active";

const ANN: Record<AnnState, string> = {
  armed: "border-armed text-armed",
  alarm: "border-alarm text-alarm",
  idle: "border-panel-etch text-label-muted",
  active: "border-label text-label",
};

/** Annunciator tile. State is carried by colour AND by the words, never colour alone. */
export function Annunciator({ label, state, detail }: { label: string; state: AnnState; detail?: string }) {
  return (
    <div className={`num border px-2 py-1.5 text-2xs uppercase tracking-wider ${ANN[state]}`} title={detail}>
      {label}
    </div>
  );
}

/** A labelled figure in the data face. */
export function Figure({
  label,
  value,
  unit,
  sub,
  tone = "label",
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  tone?: "label" | "export" | "import" | "muted" | "armed" | "alarm";
}) {
  const color = {
    label: "text-label",
    export: "text-export",
    import: "text-import",
    muted: "text-label-muted",
    armed: "text-armed",
    alarm: "text-alarm",
  }[tone];
  return (
    <div>
      <div className="legend">{label}</div>
      <div className={`num mt-1 whitespace-nowrap text-lg ${color}`}>
        {value}
        {unit && <span className="ml-1 text-xs text-label-muted">{unit}</span>}
      </div>
      {sub && <div className="num mt-0.5 text-2xs text-label-muted">{sub}</div>}
    </div>
  );
}

export function Hash({ value, head = 10, tail = 6 }: { value?: string; head?: number; tail?: number }) {
  if (!value) return <span className="num text-label-muted">—</span>;
  const short = value.length <= head + tail + 1 ? value : `${value.slice(0, head)}…${value.slice(-tail)}`;
  return (
    <span className="num break-all text-label" title={value}>
      {short}
    </span>
  );
}

export function EngineOffline({ message }: { message: string }) {
  return (
    <div className="border border-alarm bg-panel-raised p-6">
      <div className="num text-2xs uppercase tracking-wider text-alarm">Engine offline</div>
      <p className="mt-2 text-sm text-label">{message}</p>
      <p className="mt-1 text-sm text-label-muted">
        From the repository root run <code className="num text-label">python demo.py</code>, or start the engine alone
        with <code className="num text-label">python -m sim.api</code>.
      </p>
    </div>
  );
}

export function Loading() {
  return <div className="legend py-10">Reading the panel…</div>;
}
