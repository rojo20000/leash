import { goToStop, sceneNeighbourStop, stopCount, stopIndex } from './runtime';

// Text entry keeps its own keys. Buttons and links do not: focus on an arrow button or a rail link
// must not stop the navigation keys from working.
const TEXT_ENTRY = 'input, textarea, select, [contenteditable], [role="textbox"]';

export function startKeyboard() {
  window.addEventListener('keydown', (e) => {
    if (e.defaultPrevented || e.ctrlKey || e.altKey || e.metaKey) return;
    const target = e.target instanceof Element ? e.target : null;
    if (target?.closest(TEXT_ENTRY)) return;
    const last = stopCount() - 1;
    if (last < 0) return;

    const isSpace = e.key === ' ' || e.key === 'Spacebar';
    if (isSpace && target?.closest('button')) return; // native activation: exactly one click
    const base = stopIndex();
    let to: number;
    switch (e.key) {
      case 'ArrowDown': case 'ArrowRight':
        to = Math.min(last, base + 1); break;
      case ' ': case 'Spacebar':
        to = e.shiftKey ? Math.max(0, base - 1) : Math.min(last, base + 1); break;
      case 'ArrowUp': case 'ArrowLeft':
        to = Math.max(0, base - 1); break;
      case 'PageDown': to = sceneNeighbourStop(base, 1); break;
      case 'PageUp': to = sceneNeighbourStop(base, -1); break;
      case 'Home': to = 0; break;
      case 'End': to = last; break;
      default: return;
    }
    e.preventDefault();
    goToStop(to);
  });
}
