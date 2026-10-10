import type { ReactNode } from "react";

/** A card on the page: soft edge, hairline border, small caps title. */
export function Panel({
  title,
  right,
  children,
  className = "",
  bodyClassName = "p-5",
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`card min-w-0 overflow-hidden ${className}`}>
      {(title || right) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-panel-etch px-5 py-3">
          <h2 className="legend">{title}</h2>
          {right}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

type AnnState = "armed" | "alarm" | "idle" | "active";

const ANN: Record<AnnState, { text: string; dot: string }> = {
  armed: { text: "text-armed", dot: "bg-armed" },
  alarm: { text: "text-alarm", dot: "bg-alarm" },
  idle: { text: "text-label-muted", dot: "bg-label-muted" },
  active: { text: "text-label", dot: "bg-label" },
};

/** A status pill. State is carried by the colour AND by the words, never colour alone. */
export function Annunciator({ label, state, detail }: { label: string; state: AnnState; detail?: string }) {
  const s = ANN[state];
  return (
    <span className={`pill ${s.text}`} title={detail}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {label}
    </span>
  );
}

/** A labelled number. */
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
      <div className={`num mt-1.5 whitespace-nowrap text-xl ${color}`}>
        {value}
        {unit && <span className="ml-1 font-sans text-xs text-label-muted">{unit}</span>}
      </div>
      {sub && <div className="mt-0.5 text-xs text-label-muted">{sub}</div>}
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
    <div className="card border-alarm p-6">
      <div className="legend text-alarm">Engine offline</div>
      <p className="mt-2 text-label">{message}</p>
      <p className="mt-1 text-sm text-label-muted">
        From the repository root run <code className="num text-label">python demo.py</code>, or start the engine alone
        with <code className="num text-label">python -m sim.api</code>. A hosted copy that has been asleep can take up to
        a minute to wake.
      </p>
    </div>
  );
}

export function Loading() {
  return <div className="legend py-10">Loading…</div>;
}
