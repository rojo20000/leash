import { focusScene, goTo, goToStop, onSync, currentIndex, pageProgress, rendered, stopCount, stopIndex } from './runtime';

function arrowButton(dir: 'prev' | 'next', label: string): HTMLButtonElement {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = `rail__arrow rail__arrow--${dir}`;
  b.setAttribute('aria-label', label);
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '24');
  svg.setAttribute('height', '24');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', dir === 'prev' ? 'M15 4 L7 12 L15 20' : 'M9 4 L17 12 L9 20');
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', 'currentColor');
  path.setAttribute('stroke-width', '3');
  path.setAttribute('stroke-linecap', 'square');
  svg.append(path);
  b.append(svg);
  return b;
}

export function buildRail(host: HTMLElement) {
  const nav = document.createElement('nav');
  nav.className = 'rail';
  nav.dataset.ground = 'white'; // the rail never flips with the scene ground
  nav.setAttribute('aria-label', 'Scenes');

  const perf = document.createElement('div');
  perf.className = 'rail__perf perf-y';
  perf.setAttribute('aria-hidden', 'true');

  const line = document.createElement('div');
  line.className = 'rail__line';
  const fill = document.createElement('div');
  fill.className = 'rail__fill';
  line.append(fill);

  const ol = document.createElement('ol');
  ol.className = 'rail__list';
  ol.id = 'rail-list';

  const current = document.createElement('div');
  current.className = 'rail__current';

  const menu = document.createElement('button');
  menu.type = 'button';
  menu.className = 'rail__menu';
  menu.textContent = 'Scenes';
  menu.setAttribute('aria-expanded', 'false');
  menu.setAttribute('aria-controls', 'rail-list');

  let isOpen = false;
  const links: HTMLAnchorElement[] = [];

  function setOpen(open: boolean, returnFocus = false) {
    isOpen = open;
    nav.dataset.open = String(open);
    menu.setAttribute('aria-expanded', String(open));
    if (open) links[currentIndex()]?.focus();
    else if (returnFocus) menu.focus();
  }

  rendered.forEach((r, i) => {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.className = 'rail__link';
    a.href = `#${r.mod.id}`;
    a.textContent = r.mod.title;
    a.addEventListener('click', (e) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button !== 0) return;
      e.preventDefault();
      goTo(i);
      focusScene(i);
      if (isOpen) setOpen(false);
    });
    li.append(a);
    ol.append(li);
    links.push(a);
  });

  menu.addEventListener('click', () => setOpen(!isOpen));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen) {
      e.preventDefault();
      setOpen(false, true);
    }
  });
  document.addEventListener('click', (e) => {
    if (isOpen && e.target instanceof Node && !nav.contains(e.target)) setOpen(false);
  });
  // leaving the narrow layout closes the menu
  window.matchMedia('(max-width: 767px)').addEventListener('change', () => { if (isOpen) setOpen(false); });

  const arrows = document.createElement('div');
  arrows.className = 'rail__arrows';
  const prevBtn = arrowButton('prev', 'Previous step');
  const nextBtn = arrowButton('next', 'Next step');
  prevBtn.addEventListener('click', () => goToStop(stopIndex() - 1));
  nextBtn.addEventListener('click', () => goToStop(stopIndex() + 1));
  arrows.append(prevBtn, nextBtn);

  const topline = document.createElement('div');
  topline.className = 'rail__topline';
  const topfill = document.createElement('div');
  topfill.className = 'rail__topfill';
  topline.append(topfill);

  nav.append(perf, line, ol, current, arrows, menu, topline);
  host.append(nav);

  let shown = -1;
  const sync = () => {
    const idx = currentIndex();
    if (idx !== shown) {
      shown = idx;
      links.forEach((a, i) => (i === idx ? a.setAttribute('aria-current', 'true') : a.removeAttribute('aria-current')));
      current.textContent = rendered[idx]?.mod.title ?? '';
    }
    const si = stopIndex();
    prevBtn.disabled = si <= 0;
    nextBtn.disabled = si >= stopCount() - 1;
    fill.style.transform = `scaleY(${pageProgress()})`;
    topfill.style.transform = `scaleX(${rendered[idx]?.frame.progress ?? 0})`;
  };
  onSync(sync);
  sync();
}
