import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { applyThemePref } from "./lib/theme";
import "./styles.css";

applyThemePref(); // before the first paint, so a saved light/dark choice never flashes

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
