import { useEffect, useState } from "react";

/** Seconds since `running` became true (for "Searching… 4s" style progress). */
export function useElapsed(running: boolean): number {
  const [s, setS] = useState(0);
  useEffect(() => {
    if (!running) return;
    setS(0);
    const t = setInterval(() => setS((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, [running]);
  return s;
}
