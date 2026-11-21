import { execSync } from "node:child_process";

// Build once before the preview server starts, so the webServer below is a single vite process.
export default function globalSetup() {
  execSync("npx tsc && npx vite build", { stdio: "inherit" });
}
