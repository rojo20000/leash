// Generates SCRIPT.md (the printable talk track) from src/script.ts.
import { writeFileSync } from "node:fs";
import { STEPS, stepsFor, totalSeconds } from "../src/script.ts";

const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const table = (cut) => {
  let t = 0;
  return stepsFor(cut).map((s, i) => {
    const row = `| ${i} | ${s.scene} ${s.sceneName} | ${s.say.replace(/\|/g, "\|")} | ${mmss(t)} | ${s.sec}s |`;
    t += s.sec;
    return row;
  }).join("\n");
};
const head = "| Step | Scene | Say | Starts | Length |\n|---|---|---|---|---|";
writeFileSync(new URL("../SCRIPT.md", import.meta.url), `# Leash talk track

Generated from \`src/script.ts\` by \`npm run script-md\`. Edit the lines there, not here.
Press the clicker once per row. The step number is also the URL hash: \`#7\` opens step 7's end state.

## Full version: ${mmss(totalSeconds(false))} (${STEPS.length} steps)

${head}
${table(false)}

## CUT_TO_3MIN version: ${mmss(totalSeconds(true))} (${stepsFor(true).length} steps; open the deck with \`?cut=1\`)

Scene 2 is folded into Scene 1 and Scene 6 runs 45 s. Step numbers differ from the full version.

${head}
${table(true)}
`);
console.log("wrote SCRIPT.md");
