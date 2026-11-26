// One-tap attendance for the next game. Your name is asked once and remembered here.
(() => {
  const root = document.querySelector('.rsvp[data-game]');
  if (!root) return;
  const game = root.dataset.game;
  const API = '/api/attendance';
  const KEY = 'ors-rsvp-name';
  const LABEL = { in: 'In', maybe: 'Maybe', out: 'Out' };

  const store = {
    get() { try { return localStorage.getItem(KEY) || ''; } catch { return ''; } },
    set(v) { try { localStorage.setItem(KEY, v); } catch { /* private mode: ask again next time */ } },
  };
  let name = store.get();
  let players = [];
  let pending = null; // status chosen before we knew the name

  const $ = (s) => root.querySelector(s);
  const btns = [...root.querySelectorAll('[data-status]')];
  const form = $('.rsvp-name');
  const input = $('#rsvp-name-input');
  const who = $('.rsvp-who');
  const err = $('.rsvp-err');
  const lists = { in: $('[data-list="in"]'), maybe: $('[data-list="maybe"]'), out: $('[data-list="out"]') };
  const counts = { in: $('[data-count="in"]'), maybe: $('[data-count="maybe"]'), out: $('[data-count="out"]') };

  const mine = () => players.find((p) => p.name.toLocaleLowerCase() === name.toLocaleLowerCase());

  function render() {
    const me = name && mine();
    btns.forEach((b) => b.setAttribute('aria-pressed', String(!!me && me.status === b.dataset.status)));
    for (const s of Object.keys(lists)) {
      const group = players.filter((p) => p.status === s);
      counts[s].textContent = group.length;
      lists[s].replaceChildren(...group.map((p) => {
        const li = document.createElement('li');
        li.textContent = p.name;
        if (name && p.name.toLocaleLowerCase() === name.toLocaleLowerCase()) li.className = 'me';
        return li;
      }));
    }
    who.hidden = !name;
    if (name) who.querySelector('b').textContent = name;
    const dl = document.getElementById('rsvp-names');
    dl.replaceChildren(...players.map((p) => Object.assign(document.createElement('option'), { value: p.name })));
  }

  function showError(msg) { err.textContent = msg || ''; err.hidden = !msg; }

  async function load() {
    try {
      const r = await fetch(`${API}?game=${encodeURIComponent(game)}`);
      if (!r.ok) throw new Error();
      players = (await r.json()).players;
      root.classList.remove('loading');
      render();
    } catch { showError("Couldn't load attendance. Refresh to try again."); }
  }

  async function send(status) {
    showError('');
    btns.forEach((b) => (b.disabled = true));
    try {
      const r = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game, name, status }),
      });
      const out = await r.json();
      if (!r.ok) throw new Error(out.error || 'Something went wrong');
      players = out.players;
      render();
    } catch (e) { showError(e.message); }
    finally { btns.forEach((b) => (b.disabled = false)); }
  }

  btns.forEach((b) => b.addEventListener('click', () => {
    const s = b.dataset.status;
    if (!name) { pending = s; form.hidden = false; input.focus(); return; }
    const me = mine();
    send(me && me.status === s ? '' : s); // tap your current answer again to clear it
  }));

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const v = input.value.replace(/\s+/g, ' ').trim();
    if (!v) return input.focus();
    name = v;
    store.set(v);
    form.hidden = true;
    if (pending) { send(pending); pending = null; } else render();
  });

  who.querySelector('button').addEventListener('click', () => {
    input.value = name;
    form.hidden = false;
    input.select();
  });

  load();
})();
