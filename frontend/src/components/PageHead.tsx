import type { ReactNode } from "react";
import { BlockReveal, ScrambleText } from "./Motion";

interface Props {
  /** Mono label above the title, decoded on load: "evidence.backtest(time_safe)". */
  kicker: string;
  title: string;
  /** Lede and anything else under the title. */
  children?: ReactNode;
  /** Controls on the right (business type, toggles). */
  aside?: ReactNode;
  className?: string;
}

/** Every screen opens the same way: a decoding mono kicker, a block-revealed title, grid paper behind. */
export function PageHead({ kicker, title, children, aside, className }: Props) {
  return (
    <header className={`page-top paper ${className ?? ""}`}>
      <div className="page-top__main">
        <ScrambleText className="kicker" start="mount" text={kicker} cursor />
        <BlockReveal className="page-title" text={title} />
        {children}
      </div>
      {aside && <div className="page-top__aside">{aside}</div>}
    </header>
  );
}

/** A section's mono label, decoded when it scrolls into view. */
export function Kicker({ text }: { text: string }) {
  return <ScrambleText className="kicker kicker--section" text={text} />;
}
