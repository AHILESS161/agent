import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import "./styles/registr-v3.css";

if (!window.location.hash) {
  window.location.hash = "#/";
}

createRoot(document.getElementById("root")!).render(<App />);
