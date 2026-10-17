import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { startAnalytics } from "./lib/analytics";
import { parseHash } from "./lib/route";
import { applyThemePref } from "./lib/theme";
import "./styles.css";

applyThemePref(); // before the first paint, so a saved light/dark choice never flashes
startAnalytics(import.meta.env.VITE_GOATCOUNTER, () => parseHash(window.location.hash));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
