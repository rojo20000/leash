import '@fontsource-variable/bricolage-grotesque/standard.css';
import '@fontsource-variable/hanken-grotesk/wght.css';
import '@fontsource-variable/martian-mono/standard.css';
import './shell/tokens.css';
import './shell/base.css';
import { registeredScenes } from './shell/registry';
import placeholder from './shell/placeholder';
import { mountScene, rendered, startRuntime } from './shell/runtime';
import { buildRail } from './shell/rail';
import { startKeyboard } from './shell/keyboard';

const app = document.getElementById('app')!;
const main = document.createElement('main');
main.id = 'main';
app.append(main);

let first = true;
for (const mod of registeredScenes()) {
  if (mountScene(main, mod, first)) first = false;
}
if (rendered.length === 0) mountScene(main, placeholder, true);

startRuntime();
buildRail(app);
startKeyboard();
