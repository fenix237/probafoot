// ProbaFoot : front sans build (ES modules). Parle à l'API /v1 du même serveur.
const API = new URLSearchParams(location.search).get("api") || "";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fr = (x, d = 1) => x.toFixed(d).replace(".", ",");
const pct = (x, d = 1) => `${fr(x * 100, d)} %`;
const sgn = (x, d = 1) => (x >= 0 ? "+" : "−") + fr(Math.abs(x) * 100, d) + " %";
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const MODEL = { market: "Marché (clôture)", market_pre: "Marché avant match", dc: "Dixon-Coles", elo: "Elo", dc_ctx: "DC + repos", anchor: "Modèle ancré" };
const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const TITLES = { matchs: "Matchs", avenir: "À venir", performance: "Performance", estimer: "Estimer" };
const CHEV = `<svg class="chev" width="9" height="15" viewBox="0 0 9 15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M1.5 1.5l6 6-6 6"/></svg>`;

/* ---------- Données ---------- */
async function api(path) {
  let r;
  try { r = await fetch(API + path); } catch { throw new Error("API injoignable. Lancez : python -m uvicorn probafoot.api:app --port 8000"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`);
  return r.json();
}
const state = { league: "E0", season: "", minEv: 0, limit: 25, leagues: null, items: [], total: 0 };
async function leagues() { if (!state.leagues) state.leagues = (await api("/v1/leagues")).items; return state.leagues; }

/* ---------- Thème, défilement, lueur du verre ---------- */
const root = document.documentElement;
try { const t = localStorage.getItem("pf-theme"); if (t) root.dataset.theme = t; } catch {}
$("#theme").addEventListener("click", () => {
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("pf-theme", root.dataset.theme); } catch {}
});
const onScroll = () => document.body.classList.toggle("scrolled", scrollY > 70);
addEventListener("scroll", onScroll, { passive: true });
addEventListener("pointermove", (e) => {
  const g = e.target.closest && e.target.closest(".glass, .glass-strong");
  if (!g) return;
  const r = g.getBoundingClientRect();
  g.style.setProperty("--mx", `${e.clientX - r.left}px`); g.style.setProperty("--my", `${e.clientY - r.top}px`);
}, { passive: true });

/* ---------- Infobulle commune ---------- */
const tip = $("#tip");
function showTip(html, x, y) {
  tip.innerHTML = html; tip.classList.add("on");
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = `${Math.min(innerWidth - w - 8, Math.max(8, x + 14))}px`;
  tip.style.top = `${Math.min(innerHeight - h - 8, Math.max(8, y - h - 12))}px`;
}
const hideTip = () => tip.classList.remove("on");

/* ---------- Composants ---------- */
function ring(p, size = 190, centre = null) {
  const R = 42, C = 2 * Math.PI * R;
  let acc = 0;
  const segs = p.map((v, i) => {
    const len = Math.max(0, v * C - 7), off = -(acc * C + 3.5);
    acc += v;
    return `<circle class="c-${"hda"[i]}" cx="50" cy="50" r="${R}" data-len="${len}" stroke-dasharray="0 ${C}" stroke-dashoffset="${off}"/>`;
  }).join("");
  const i = p.indexOf(Math.max(...p));
  const mid = centre ?? `<b>${Math.round(p[i] * 100)}%</b><span>${["Domicile", "Nul", "Extérieur"][i]}</span>`;
  return `<div class="ring" style="--size:${size}px" role="img" aria-label="Domicile ${pct(p[0], 0)}, nul ${pct(p[1], 0)}, extérieur ${pct(p[2], 0)}">
    <svg viewBox="0 0 100 100"><circle class="track" cx="50" cy="50" r="${R}"/>${segs}</svg><div class="mid">${mid}</div></div>`;
}
function triple(p, names = ["Domicile", "Nul", "Extérieur"], sub = null) {
  const m = p.indexOf(Math.max(...p));
  return `<div class="triple">${p.map((v, i) => `<div class="${"hda"[i]}${i === m ? " top" : ""}"><span>${esc(names[i])}</span><b class="tnum">${pct(v, 0)}</b>${sub ? `<small>${sub[i]}</small>` : ""}</div>`).join("")}</div>`;
}
function pbar(p) {
  if (!p) return `<span class="muted">n/d</span>`;
  return `<div class="pbar" title="1 ${pct(p[0], 0)} · X ${pct(p[1], 0)} · 2 ${pct(p[2], 0)}" role="img" aria-label="Domicile ${pct(p[0], 0)}, nul ${pct(p[1], 0)}, extérieur ${pct(p[2], 0)}">
    <i class="h" data-w="${p[0] * 100}" style="width:0"></i><i class="d" data-w="${p[1] * 100}" style="width:0"></i><i class="a" data-w="${p[2] * 100}" style="width:0"></i></div>`;
}
const legend = () => `<div class="legend"><span><i style="background:var(--s1)"></i>Domicile</span><span><i style="background:var(--neutral)"></i>Nul</span><span><i style="background:var(--s2)"></i>Extérieur</span></div>`;
const skel = (n = 4, h = 84) => Array.from({ length: n }, () => `<div class="skel" style="min-height:${h}px"></div>`).join("");
const failure = (e) => `<div class="err" role="alert">${esc(e.message)}</div>`;
const seg = (id, opts, val) => `<div class="seg" id="${id}" role="tablist"><i class="thumb"></i>${opts.map((o) => `<button type="button" role="tab" data-v="${esc(o.v)}" aria-selected="${o.v === val}">${esc(o.label)}</button>`).join("")}</div>`;

function placeThumbs(scope = document) {
  $$(".seg", scope).forEach((s) => {
    const b = $('[aria-selected="true"]', s), t = $(".thumb", s);
    if (b && t) { t.style.width = `${b.offsetWidth}px`; t.style.transform = `translateX(${b.offsetLeft}px)`; }
  });
}
function placeLens() {
  const a = $('#tabbar a[aria-current="page"]'), l = $("#lens");
  if (a) { l.style.width = `${a.offsetWidth}px`; l.style.transform = `translateX(${a.offsetLeft}px)`; }
}
addEventListener("resize", () => { placeThumbs(); placeLens(); });
document.fonts && document.fonts.ready.then(() => { placeThumbs(); placeLens(); });

/* Après insertion : anneaux, barres, compteurs, avec un état de départ déjà lisible */
function activate(scope) {
  const go = () => {
    $$(".ring circle[data-len]", scope).forEach((c) => { const len = +c.dataset.len, C = 2 * Math.PI * 42; c.setAttribute("stroke-dasharray", `${len} ${C - len}`); });
    $$("[data-w]", scope).forEach((el) => (el.style.width = `${el.dataset.w}%`));
  };
  REDUCED ? go() : requestAnimationFrame(() => requestAnimationFrame(go));
  $$(".cnt", scope).forEach((el) => {
    const v = +el.dataset.v, d = +(el.dataset.d ?? 0), suf = el.dataset.suf ?? "", pre = el.dataset.pre ?? "";
    const f = (x) => pre + fr(x, d) + suf;
    if (REDUCED) return;
    const t0 = performance.now();
    const tick = (t) => { const k = Math.min(1, (t - t0) / 1000), e = 1 - Math.pow(1 - k, 4); el.textContent = f(v * e); if (k < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  });
  placeThumbs(scope);
}
const cnt = (v, d = 0, suf = "", pre = "") => `<span class="cnt tnum" data-v="${v}" data-d="${d}" data-suf="${suf}" data-pre="${pre}">${pre}${fr(v, d)}${suf}</span>`;
const NOTICE = `<div class="note rise" role="note"><b>Jeu responsable.</b> Les paris comportent des risques de perte : ne pariez que ce que vous pouvez vous permettre de perdre. Probabilités estimées, sans garantie de gain. Réservé aux majeurs.</div>`;
const largeTitle = (t, sub, id = "") => `<div class="largetitle rise"><h1>${t}</h1><p ${id ? `id="${id}"` : ""}>${sub}</p></div>`;

/* ---------- Vue : matchs ---------- */
function rowHTML(m, i) {
  const best = m.ev_dc ? Math.max(...m.ev_dc) : null;
  const d = new Date(m.kickoff);
  const ev = best === null ? `<span class="evpill">n/d</span>` : best > .5 ? `<span class="evpill sus" title="Désaccord très fort avec le marché : probablement une erreur du modèle">&gt; +50 %</span>` : `<span class="evpill ${best >= .03 ? "pos" : ""}">${sgn(best, 0)}</span>`;
  return `<a class="mrow" href="#/match/${m.id}" style="--i:${Math.min(i, 9)}">
    <div class="mdate"><b class="tnum">${d.getDate()}</b><span>${MONTHS[d.getMonth()]}</span></div>
    <div class="mteams"><div class="names">${esc(m.home)}<span>${esc(m.away)}</span></div>
      <div class="bars"><span>Marché</span>${pbar(m.probs.market)}<span>Modèle</span>${pbar(m.probs.dc)}</div></div>
    <div class="mscore tnum">${m.hg}–${m.ag}</div>${ev}${CHEV}</a>`;
}
function renderList() {
  const items = state.items.filter((m) => state.minEv <= 0 || (m.ev_dc && Math.max(...m.ev_dc) >= state.minEv / 100));
  const box = $("#mlist");
  box.innerHTML = items.length
    ? `<div class="glass group rise">${items.map(rowHTML).join("")}</div>
       <div class="row" style="justify-content:center;margin-top:18px">${state.total > state.limit ? `<button class="chip press" id="more" type="button">Afficher plus · ${state.limit} sur ${state.total}</button>` : `<span class="muted">${state.total} matchs</span>`}</div>`
    : `<div class="glass empty rise">Aucun match ne correspond à ces filtres.</div>`;
  activate(box);
  const more = $("#more", box);
  if (more) more.addEventListener("click", () => { state.limit += 25; refreshMatches(); });
}
async function refreshMatches(tok, first = false) {
  const lgs = await leagues();
  if (!lgs.some((l) => l.league === state.league) && lgs[0]) state.league = lgs[0].league;
  const [runs, list] = await Promise.all([
    api(`/v1/runs?league=${state.league}&limit=1`),
    api(`/v1/matches?league=${state.league}&limit=${state.limit}${state.season ? `&season=${state.season}` : ""}`),
  ]);
  if (tok && tok.stale) return;
  const run = runs.items[0], seasons = run ? run.seasons : [];
  state.items = list.items; state.total = list.total;
  $("#msub").innerHTML = run ? `${cnt(run.summary.n)} matchs rejoués sans fuite de données · chaque prévision n'utilise que ce qu'on savait avant le coup d'envoi.` : "Lancez un backtest pour alimenter l'application.";
  const top = state.items[0];
  $("#mhero").innerHTML = top ? `
    <section class="glass featured rise" style="--i:1">
      <div class="eyebrow">Dernier match évalué · ${esc(top.kickoff.slice(0, 10))}</div>
      <h2>${esc(top.home)} <em>contre</em> ${esc(top.away)} <span class="sc tnum">${top.hg}–${top.ag}</span></h2>
      ${triple(top.probs.dc, ["Domicile", "Nul", "Extérieur"], top.probs.market.map((v) => `Marché ${pct(v, 0)}`))}
      <div class="row" style="justify-content:space-between"><span class="muted">Probabilités du modèle avant le coup d'envoi, comparées à celles du marché.</span><a class="cta" href="#/match/${top.id}">Voir le détail</a></div>
    </section>` : "";
  activate($("#mhero"));
  const sOpts = [{ v: "", label: "Toutes" }, ...seasons.map((s) => ({ v: s, label: `${s.slice(0, 2)}/${s.slice(2)}` }))];
  if (first) {
    $("#mfilters").innerHTML = `${seg("seg-league", lgs.map((l) => ({ v: l.league, label: l.league })), state.league)}
      <span id="seasonwrap">${seg("seg-season", sOpts, state.season)}</span>
      <label class="evbox glass-strong">Valeur espérée min <input id="ev" type="range" min="0" max="15" step="1" value="${state.minEv}" aria-label="Valeur espérée minimale"> <b class="tnum" id="evv">${state.minEv} %</b></label>`;
    $("#seg-league").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; state.league = b.dataset.v; state.season = ""; state.limit = 25; pick("#seg-league", b); $("#seasonwrap").innerHTML = ""; refreshMatches(null, "seasons"); });
    $("#seasonwrap").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; state.season = b.dataset.v; state.limit = 25; pick("#seg-season", b); refreshMatches(); });
    const ev = $("#ev"), fill = () => ev.style.setProperty("--fill", `${(ev.value / 15) * 100}%`);
    fill();
    ev.addEventListener("input", () => { $("#evv").textContent = `${ev.value} %`; fill(); });
    ev.addEventListener("change", () => { state.minEv = +ev.value; renderList(); });
    placeThumbs($("#mfilters"));
  } else if (first === "seasons") {
    $("#seasonwrap").innerHTML = seg("seg-season", sOpts, "");
    placeThumbs($("#seasonwrap"));
  }
  renderList();
}
function pick(sel, btn) { $$("button", $(sel)).forEach((b) => b.setAttribute("aria-selected", b === btn)); placeThumbs($(sel).parentElement); }

async function viewMatches(app, tok) {
  app.innerHTML = `${largeTitle("Matchs", "Chargement…", "msub")}${NOTICE}<div id="mhero"></div><div class="filters rise" id="mfilters" style="--i:2"></div><div id="mlist">${skel(5, 96)}</div>
    <p class="muted" style="margin:18px 4px 0">Valeur espérée (EV) : gain moyen attendu du meilleur choix du modèle contre les cotes Bet365 avant match. Une EV très élevée signale surtout un désaccord avec le marché, donc souvent une erreur du modèle. Une EV positive n'est pas une garantie : elle ne se confirme qu'après des milliers de paris.</p><p class="foot" id="foot"></p>`;
  await refreshMatches(tok, true);
  fetch(API + "/v1/health").then((r) => r.json()).then((h) => { const f = $("#foot"); if (f) f.textContent = `ProbaFoot v${h.version} · outil d'aide à la décision, pas une machine à gagner.`; }).catch(() => {});
}

/* ---------- Feuille : fiche d'un match ---------- */
const sheet = $("#sheet"), sheetBody = $("#sheet-body");
let sheetTok = 0;
function trackLine(label, v, color) { return `<div class="line"><span>${label}</span><div class="track"><i data-w="${v * 100}" style="width:0;background:${color}"></i></div><b class="tnum">${pct(v, 0)}</b></div>`; }
async function openSheet(id) {
  const tok = ++sheetTok;
  if (sheet.hidden) { sheet.hidden = false; document.body.classList.add("lock"); requestAnimationFrame(() => requestAnimationFrame(() => sheet.classList.add("open"))); }
  sheetBody.innerHTML = `<div class="stack">${skel(3, 110)}</div>`;
  $("#sheet-close").focus({ preventScroll: true });
  try {
    const d = await api(`/v1/matches/${id}`);
    if (tok !== sheetTok) return;
    const p = d.probs, main = p.dc || p.market;
    const names = { H: d.home, D: "Match nul", A: d.away };
    const oc = ["H", "D", "A"].map((k, i) => `<div class="inner outcome rise" style="--i:${i + 1}">
      <div class="row" style="justify-content:space-between"><span class="name">${esc(names[k])}</span>${d.result === k ? `<span class="chip good">Résultat réel</span>` : ""}</div>
      ${p.market ? trackLine("Marché", p.market[i], "var(--s1)") : ""}${p.dc ? trackLine("Modèle", p.dc[i], "var(--s2)") : ""}${p.elo ? trackLine("Elo", p.elo[i], "var(--neutral)") : ""}</div>`).join("");
    const odds = Object.entries(d.odds).sort(([k]) => (k === "pre" ? -1 : 1)).flatMap(([kind, books]) => Object.entries(books).map(([bk, o]) => `<tr><td>${kind === "pre" ? "Avant match" : "Clôture"}</td><td>${esc(bk)}</td>${o.map((v) => `<td class="n">${fr(v, 2)}</td>`).join("")}</tr>`)).join("");
    sheetBody.innerHTML = `
      <div><div class="eyebrow">${esc(d.league)} · saison ${esc(d.season.slice(0, 2))}/${esc(d.season.slice(2))} · ${esc(d.kickoff.replace("T", " "))}</div>
        <h2 class="big" id="sheet-title" style="margin-top:8px">${esc(d.home)} <span class="sc tnum">${d.hg}–${d.ag}</span> ${esc(d.away)}</h2></div>
      <div class="stack" style="gap:12px">${triple(main, ["Domicile", "Nul", "Extérieur"], p.market ? p.market.map((v) => `Marché ${pct(v, 0)}`) : null)}<p class="muted" style="margin:0">Prédiction émise le <b>${esc((d.as_of || "").replace("T", " "))}</b>, uniquement avec les résultats connus à cet instant.</p></div>
      <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(210px,1fr))">${oc}</div>
      <div class="cols-2">
        <section class="inner pad rise" style="--i:4"><h3 style="font-size:18px;margin-bottom:8px">Cotes enregistrées</h3><div class="scroll"><table class="t"><thead><tr><th>Moment</th><th>Bookmaker</th><th class="n">1</th><th class="n">X</th><th class="n">2</th></tr></thead><tbody>${odds}</tbody></table></div>
          ${d.close_fair_probs ? `<p class="muted" style="margin:10px 0 0">Juste prix de clôture (marge retirée) : ${d.close_fair_probs.map((v) => pct(v, 0)).join(" · ")}</p>` : ""}</section>
        <section class="inner pad rise" style="--i:5"><h3 style="font-size:18px;margin-bottom:14px">Chronologie</h3>
          <ul class="timeline">${d.events.map((e) => `<li><span class="chip">${esc(e.event_type)}</span><div class="muted tnum" style="margin-top:5px">Survenu ${esc(e.occurred_at.replace("T", " "))}<br>Connu ${esc(e.known_at.replace("T", " "))} · ${esc(e.source)}</div></li>`).join("")}</ul>
          <p class="muted" style="margin:12px 0 0">Seule la date « connu » décide de ce qu'un modèle a le droit de voir : c'est la protection contre la fuite de données.</p></section>
      </div>`;
    activate(sheetBody);
  } catch (e) { if (tok === sheetTok) sheetBody.innerHTML = failure(e); }
}
function closeSheet() {
  if (sheet.hidden) return;
  sheetTok++; sheet.classList.remove("open"); document.body.classList.remove("lock");
  setTimeout(() => { if (!sheet.classList.contains("open")) sheet.hidden = true; }, REDUCED ? 0 : 650);
}
function dismissSheet() { history.replaceState(null, "", "#/"); render(); }
$("#sheet-close").addEventListener("click", dismissSheet);
$("#sheet-backdrop").addEventListener("click", dismissSheet);
addEventListener("keydown", (e) => { if (e.key === "Escape" && !sheet.hidden) dismissSheet(); });

/* ---------- Vue : performance ---------- */
function cumulativeChart(rows) {
  const W = 640, H = 330, L = 50, R = 16, T = 16, B = 34;
  const vals = rows.flatMap((r) => [r.market, r.dc]);
  let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * .18 || .01; lo -= pad; hi += pad;
  const x = (i) => L + (i / (rows.length - 1)) * (W - L - R), y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const line = (k) => rows.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(r[k]).toFixed(1)}`).join("");
  const gap = `${line("dc")}${rows.map((r, i) => `L${x(rows.length - 1 - i).toFixed(1)},${y(rows[rows.length - 1 - i].market).toFixed(1)}`).join("")}Z`;
  const ticks = [lo + pad, (lo + hi) / 2, hi - pad], last = rows.length - 1;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Log-loss cumulée moyenne : marché contre modèle" style="width:100%;height:auto">
    ${ticks.map((t) => `<line class="grid-l" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"/><text x="${L - 8}" y="${y(t) + 4}" text-anchor="end">${fr(t, 3)}</text>`).join("")}
    <line class="axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>
    <text x="${L}" y="${H - 10}">${rows[0].date}</text><text x="${W - R}" y="${H - 10}" text-anchor="end">${rows[last].date}</text>
    <path d="${gap}" fill="var(--s2)" opacity=".13"/>
    <path d="${line("market")}" fill="none" stroke="var(--s1)" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
    <path d="${line("dc")}" fill="none" stroke="var(--s2)" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(last)}" cy="${y(rows[last].market)}" r="5" fill="var(--s1)" stroke="var(--glass-strong)" stroke-width="2.5"/><circle cx="${x(last)}" cy="${y(rows[last].dc)}" r="5" fill="var(--s2)" stroke="var(--glass-strong)" stroke-width="2.5"/>
    <text x="${x(last) - 10}" y="${y(rows[last].market) + 20}" text-anchor="end" style="fill:var(--s1);font-weight:700">Marché</text>
    <text x="${x(last) - 10}" y="${y(rows[last].dc) - 12}" text-anchor="end" style="fill:var(--s2);font-weight:700">Modèle</text>
    <line id="xh" class="axis" y1="${T}" y2="${H - B}" style="display:none"/><rect id="hit" x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent"/></svg>`;
}
function wireCumulative(scope, rows) {
  const svg = $(".chart", scope), hit = svg && $("#hit", svg), xh = svg && $("#xh", svg);
  if (!hit) return;
  const W = 640, L = 50, R = 16;
  hit.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(rows.length - 1, Math.round(((px - L) / (W - L - R)) * (rows.length - 1))));
    const xx = L + (i / (rows.length - 1)) * (W - L - R);
    xh.setAttribute("x1", xx); xh.setAttribute("x2", xx); xh.style.display = "";
    const q = rows[i];
    showTip(`<b>${q.date} · ${q.n} matchs</b>Marché ${fr(q.market, 4)}<br>Modèle ${fr(q.dc, 4)}<br>Écart ${q.dc - q.market >= 0 ? "+" : "−"}${fr(Math.abs(q.dc - q.market), 4)}`, e.clientX, e.clientY);
  });
  hit.addEventListener("pointerleave", () => { xh.style.display = "none"; hideTip(); });
}
function calibrationChart(rows) {
  const S = 340, L = 44, B = 40, T = 12, R = 14;
  const x = (v) => L + v * (S - L - R), y = (v) => S - B - v * (S - B - T), maxN = Math.max(...rows.map((r) => r.n));
  return `<svg class="chart" viewBox="0 0 ${S} ${S}" role="img" aria-label="Calibration : fréquence observée selon la probabilité annoncée" style="width:100%;max-width:420px;height:auto">
    ${[0, .25, .5, .75, 1].map((t) => `<line class="grid-l" x1="${x(0)}" x2="${x(1)}" y1="${y(t)}" y2="${y(t)}"/><text x="${L - 8}" y="${y(t) + 4}" text-anchor="end">${t * 100}%</text><text x="${x(t)}" y="${S - B + 18}" text-anchor="middle">${t * 100}%</text>`).join("")}
    <line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" stroke="var(--ink-3)" stroke-dasharray="5 6" opacity=".7"/>
    <path d="${rows.map((r, i) => `${i ? "L" : "M"}${x(r.p_mean).toFixed(1)},${y(r.freq).toFixed(1)}`).join("")}" fill="none" stroke="var(--s2)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
    ${rows.map((r, i) => `<circle data-i="${i}" cx="${x(r.p_mean)}" cy="${y(r.freq)}" r="${4.5 + 5 * Math.sqrt(r.n / maxN)}" fill="var(--s2)" stroke="var(--glass-strong)" stroke-width="2.5"/>`).join("")}
    <text x="${(L + S - R) / 2}" y="${S - 6}" text-anchor="middle">Probabilité annoncée</text><text transform="rotate(-90)" x="${-(S - B + T) / 2}" y="12" text-anchor="middle">Fréquence observée</text></svg>`;
}
function wireCalibration(scope, rows) {
  $$("circle[data-i]", scope).forEach((c) => {
    const r = rows[+c.dataset.i];
    c.addEventListener("pointermove", (e) => showTip(`<b>Annoncé ${pct(r.p_mean)}</b>Observé ${pct(r.freq)}<br>${r.n} prévisions`, e.clientX, e.clientY));
    c.addEventListener("pointerleave", hideTip);
  });
}
async function viewPerformance(app, tok) {
  app.innerHTML = `${largeTitle("Performance", "Chargement…")}<div class="stack">${skel(3, 110)}</div>`;
  const lgs = await leagues();
  const p = await api(`/v1/performance?league=${state.league}`);
  if (tok.stale) return;
  p.cumulative = p.cumulative.filter((r) => r.n >= 60);
  const dc = p.models.dc, mk = p.models.market, vs = p.paired.dc_vs_market, bad = vs && vs.verdict === "moins bon";
  const headline = bad ? "Le modèle ne bat pas encore le marché." : vs && vs.verdict === "meilleur" ? "Le modèle devance le marché." : "Le modèle est au niveau du marché.";
  app.innerHTML = `${largeTitle("Performance", `Mesurée sur ${cnt(p.n)} matchs jamais vus (saisons ${p.seasons.map((s) => `${s.slice(0, 2)}/${s.slice(2)}`).join(", ")}), contre les cotes de clôture : la référence la plus difficile à battre.`)}
    <div class="filters rise" style="--i:1">${seg("seg-league", lgs.map((l) => ({ v: l.league, label: l.league })), state.league)}<span class="muted">Run ${esc(p.run_id)}</span></div>
    <section class="glass pad rise" style="--i:2"><div class="eyebrow">Verdict</div><h2 style="font-size:clamp(24px,4vw,36px);margin-top:6px;letter-spacing:-.035em;font-weight:800">${headline}</h2></section>
    <div class="grid" style="margin-top:16px">
      <div class="glass pad kpi rise" style="--i:3"><div class="eyebrow">Log-loss marché</div><b>${cnt(mk.log_loss, 4)}</b><span class="muted">plus bas = mieux</span></div>
      <div class="glass pad kpi rise" style="--i:4"><div class="eyebrow">Log-loss modèle</div><b class="${bad ? "neg" : "pos"}">${cnt(dc.log_loss, 4)}</b><span class="muted">écart ${vs ? (vs.mean >= 0 ? "+" : "−") + fr(Math.abs(vs.mean), 4) : "n/d"} [${vs ? fr(vs.lo, 4) : ""} ; ${vs ? fr(vs.hi, 4) : ""}]</span></div>
      <div class="glass pad kpi rise" style="--i:5"><div class="eyebrow">Calibration (ECE)</div><b>${cnt(dc.ece * 100, 2, " %")}</b><span class="muted">écart moyen annoncé / observé</span></div>
      ${p.bets ? `<div class="glass pad kpi rise" style="--i:6"><div class="eyebrow">CLV moyen simulé</div><b class="${p.bets.clv < 0 ? "neg" : "pos"}">${sgn(p.bets.clv, 2)}</b><span class="muted">${p.bets.n} paris · ROI ${sgn(p.bets.roi, 1)}</span></div>` : ""}
    </div>
    ${p.paired.anchor_vs_market_pre ? (() => { const v = p.paired.anchor_vs_market_pre, th = p.anchor && p.anchor.theta; return `<section class="glass pad rise" style="margin-top:16px;--i:5"><div class="eyebrow">Modèle ancré sur le marché</div>
      <h3 style="font-size:22px;margin:6px 0 8px">${v.verdict === "meilleur" ? "La correction améliore le prix du marché." : v.verdict === "moins bon" ? "La correction dégrade légèrement le prix du marché." : "La correction ne change rien de mesurable."}</h3>
      <p style="margin:0;color:var(--ink-2);max-width:70ch">On part des cotes avant match et on y ajoute ce que le modèle statistique apporte. Écart de log-loss face aux cotes avant match : <b class="tnum">${v.mean >= 0 ? "+" : "−"}${fr(Math.abs(v.mean), 4)}</b> [${fr(v.lo, 4)} ; ${fr(v.hi, 4)}]. ${v.verdict === "meilleur" ? "" : "Règle du projet : tant que l'écart n'est pas entièrement négatif, le prix du marché reste la meilleure estimation et l'ancrage n'est pas activé."}</p>
      ${th ? `<p class="muted" style="margin:10px 0 0">Poids appris : marché ${fr(th[0], 2)}, modèle ${fr(th[1], 2)} (marché pur = 1 et 0).</p>` : ""}</section>`; })() : ""}
    <div class="cols-2" style="margin-top:16px">
      <section class="glass pad rise" style="--i:6"><h3 style="font-size:19px">Log-loss cumulée moyenne</h3><p class="muted" style="margin:4px 0 10px">Plus la ligne est basse, meilleures sont les probabilités. La zone colorée est l'écart à combler. Survolez pour comparer.</p>${p.cumulative.length > 1 ? cumulativeChart(p.cumulative) : `<div class="empty">Pas assez de matchs.</div>`}</section>
      <section class="glass pad rise" style="--i:7"><h3 style="font-size:19px">Calibration du modèle</h3><p class="muted" style="margin:4px 0 10px">Quand le modèle annonce 60 %, l'événement doit arriver environ 6 fois sur 10 : les points suivent la diagonale.</p>${calibrationChart(p.calibration)}
        <details style="margin-top:10px"><summary class="muted" style="cursor:pointer">Voir en tableau</summary><div class="scroll"><table class="t"><thead><tr><th>Tranche</th><th class="n">n</th><th class="n">Annoncé</th><th class="n">Observé</th></tr></thead><tbody>
        ${p.calibration.map((r) => `<tr><td>${Math.round(r.lo * 100)}–${Math.round(r.hi * 100)} %</td><td class="n">${r.n}</td><td class="n">${pct(r.p_mean)}</td><td class="n">${pct(r.freq)}</td></tr>`).join("")}</tbody></table></div></details></section>
    </div>
    <section class="glass pad rise" style="margin-top:16px;--i:8"><h3 style="font-size:19px;margin-bottom:8px">Tous les modèles</h3><div class="scroll"><table class="t"><thead><tr><th>Modèle</th><th class="n">Log-loss</th><th class="n">RPS</th><th class="n">Brier</th><th class="n">ECE</th><th>Face au marché</th></tr></thead><tbody>
      ${Object.entries(p.models).map(([k, s]) => { const v = p.paired[`${k}_vs_market`]; return `<tr><td><b>${esc(MODEL[k] || k)}</b></td><td class="n">${fr(s.log_loss, 4)}</td><td class="n">${fr(s.rps, 4)}</td><td class="n">${fr(s.brier, 4)}</td><td class="n">${fr(s.ece, 4)}</td><td>${k === "market" ? `<span class="chip">référence</span>` : v ? `<span class="chip ${v.verdict === "meilleur" ? "good" : v.verdict === "moins bon" ? "bad" : "warn"}">${v.verdict}</span>` : ""}</td></tr>`; }).join("")}</tbody></table></div>
      <p class="muted" style="margin:10px 0 0">Un ROI mesuré sur quelques centaines de paris n'a aucune valeur probante : seuls la log-loss, la calibration et le CLV permettent de juger tôt.</p></section>`;
  activate(app);
  if (p.cumulative.length > 1) wireCumulative(app, p.cumulative);
  wireCalibration(app, p.calibration);
  $("#seg-league").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; state.league = b.dataset.v; pick("#seg-league", b); setTimeout(() => showView("performance", true), 260); });
}

/* ---------- Vue : à venir (cotes captées) ---------- */
const FRDATE = (iso) => { const d = new Date(iso + "Z"); return `${d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" })} · ${d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`; };
async function viewUpcoming(app, tok) {
  app.innerHTML = `${largeTitle("À venir", "Chargement…")}<div class="stack">${skel(3, 150)}</div>`;
  const [up, st] = await Promise.all([api("/v1/odds/upcoming?limit=40"), api("/v1/capture/status")]);
  if (tok.stale) return;
  const last = st.leagues.map((l) => l.captured_at).sort().pop();
  const rem = st.leagues.map((l) => l.remaining).filter((x) => x != null).pop();
  const head = `${largeTitle("À venir", up.items.length ? `${up.items.length} matchs avec des cotes captées. Le « juste prix » est la moyenne des bookmakers, marge retirée.` : "Aucune cote captée pour l'instant.")}`;
  if (!up.items.length) {
    app.innerHTML = `${head}${NOTICE}<section class="glass pad rise"><h3 style="font-size:19px">Démarrer la capture</h3>
      <p style="color:var(--ink-2);max-width:62ch">La capture enregistre les cotes de plusieurs bookmakers à intervalles réguliers. Cet historique ne se rattrape pas : plus tôt elle démarre, plus vos futurs backtests seront fiables.</p>
      <ol class="muted" style="font-size:15px;line-height:1.8"><li>Créez une clé gratuite sur the-odds-api.com.</li><li>Définissez la variable d'environnement <b>ODDS_API_KEY</b> avec cette clé.</li><li>Lancez <code>python -m probafoot capture</code>, ou le service Docker <code>capture</code>.</li></ol>
      <p class="muted" style="margin:0">${st.ticks} cotes en base · ${st.fixtures} matchs suivis.</p></section>`;
    activate(app); return;
  }
  app.innerHTML = `${head}${NOTICE}
    <div class="muted rise" style="margin:-6px 0 16px">Dernière capture : ${esc((last || "").replace("T", " "))} UTC${rem != null ? ` · crédits API restants : ${rem}` : ""}${st.unresolved_fixtures ? ` · ${st.unresolved_fixtures} match(s) à rapprocher à la main` : ""}</div>
    <div class="stack">${up.items.map((m, i) => {
      const names = [m.home, "Nul", m.away];
      const sub = m.fair.map((_, k) => `Meilleure cote ${fr(m.best[k].odds, 2)} · ${esc(m.best[k].bookmaker)}${m.ev ? ` · EV ${sgn(m.ev[k], 0)}` : ""}`);
      const mv = m.move ? m.move.map((x, k) => `${["1", "X", "2"][k]} ${x >= 0 ? "+" : "−"}${fr(Math.abs(x) * 100, 1)} pt`).join(" · ") : "";
      return `<section class="glass pad rise" style="--i:${Math.min(i, 8)}">
        <div class="eyebrow">${esc(m.league)} · ${esc(FRDATE(m.commence))} · ${m.n_books} bookmaker${m.n_books > 1 ? "s" : ""}</div>
        <h3 style="font-size:22px;margin:6px 0 12px">${esc(m.home)} <span class="muted">contre</span> ${esc(m.away)}</h3>
        ${triple(m.fair, names, sub)}
        <p class="muted" style="margin:12px 0 0">${m.model ? `Modèle : ${m.model.map((v) => pct(v, 0)).join(" · ")} (domicile · nul · extérieur). ` : `<b>Pas d'estimation du modèle</b> : noms d'équipes à rapprocher. `}${mv ? `Mouvement depuis l'ouverture : ${mv}.` : "Première capture : pas encore de mouvement."}</p></section>`;
    }).join("")}</div>
    <p class="muted" style="margin:18px 4px 0">EV : valeur espérée du modèle contre la meilleure cote disponible. Le modèle perd actuellement face au marché : une EV affichée est un désaccord à examiner, pas un conseil de pari.</p>`;
  activate(app);
}

/* ---------- Vue : estimer ---------- */
async function viewPredict(app, tok) {
  const lgs = await leagues();
  if (tok.stale) return;
  app.innerHTML = `${largeTitle("Estimer", "Choisissez deux équipes. Modèle Dixon-Coles entraîné sur les quatre dernières années, sans compositions ni blessures.")}
    <section class="glass pad rise" style="--i:1"><div class="row" style="gap:12px">
      <select class="pick" id="lg" aria-label="Ligue">${lgs.map((l) => `<option ${l.league === state.league ? "selected" : ""}>${esc(l.league)}</option>`).join("")}</select>
      <select class="pick" id="home" aria-label="Équipe à domicile"><option value="">Domicile…</option></select>
      <span class="muted">contre</span>
      <select class="pick" id="away" aria-label="Équipe à l'extérieur"><option value="">Extérieur…</option></select>
      <button class="cta" id="go" type="button" disabled>Estimer</button></div></section>
    <div id="out" style="margin-top:16px"></div>`;
  const check = () => ($("#go").disabled = !$("#home").value || !$("#away").value || $("#home").value === $("#away").value);
  const fill = async () => {
    const t = (await api(`/v1/teams?league=${$("#lg").value}`)).items;
    for (const id of ["home", "away"]) $(`#${id}`).innerHTML = `<option value="">${id === "home" ? "Domicile…" : "Extérieur…"}</option>` + t.map((x) => `<option>${esc(x)}</option>`).join("");
    check();
  };
  $("#lg").addEventListener("change", () => { state.league = $("#lg").value; fill(); });
  $("#home").addEventListener("change", check); $("#away").addEventListener("change", check);
  $("#go").addEventListener("click", async () => {
    const out = $("#out"); out.innerHTML = skel(2, 160);
    try {
      const r = await api(`/v1/predict?league=${$("#lg").value}&home=${encodeURIComponent($("#home").value)}&away=${encodeURIComponent($("#away").value)}`);
      const m = r.markets, P = [m["1"].p, m.X.p, m["2"].p];
      const NAMES = { "1": r.home, X: "Match nul", "2": r.away, "over_2.5": "Plus de 2,5 buts", "under_2.5": "Moins de 2,5 buts", btts_yes: "Les deux équipes marquent", btts_no: "Une équipe au moins ne marque pas" };
      out.innerHTML = `<div class="cols-2">
        <section class="glass pad rise" style="display:grid;gap:14px;align-content:start"><h2 style="font-size:22px">${esc(r.home)} contre ${esc(r.away)}</h2>${triple(P, [r.home, "Nul", r.away])}<p class="muted" style="margin:0">Buts attendus : <b class="tnum">${fr(r.expected_goals.home, 1)}</b> – <b class="tnum">${fr(r.expected_goals.away, 1)}</b></p></section>
        <section class="glass pad rise" style="--i:1;display:grid;gap:14px;align-content:start"><h3 style="font-size:19px">Marchés</h3>
          ${Object.entries(m).map(([k, v]) => `<div><div class="row" style="justify-content:space-between;font-size:14.5px"><span>${esc(NAMES[k] || k)}</span><b class="tnum">${pct(v.p)} <span class="muted">· cote juste ${v.fair_odds ? fr(v.fair_odds, 2) : "–"}</span></b></div><div class="track" style="margin-top:6px"><i data-w="${v.p * 100}" style="width:0;background:var(--accent)"></i></div></div>`).join("")}</section></div>
        <section class="glass pad rise" style="margin-top:16px;--i:2"><div class="eyebrow">Scores les plus probables</div><div class="row" style="margin-top:10px">${r.top_scores.map((s) => `<span class="chip tnum">${esc(s.score)} · ${pct(s.p)}</span>`).join("")}</div>
          <p class="muted" style="margin:12px 0 0">${esc(r.notice)} Cote juste = 1 / probabilité : une cote plus élevée ne garantit rien, le modèle peut se tromper.</p></section>`;
      activate(out);
    } catch (e) { out.innerHTML = failure(e); }
  });
  fill();
}

/* ---------- Routeur ---------- */
let navId = 0;
const app = $("#app");
function setNav(view) {
  $$("#tabbar a").forEach((a) => (a.dataset.nav === view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  $("#bartitle").textContent = TITLES[view];
  placeLens();
}
async function showView(view, keepScroll = false) {
  const tok = { stale: false }; showView.tok && (showView.tok.stale = true); showView.tok = tok;
  hideTip(); app.dataset.view = view;
  try {
    if (view === "performance") await viewPerformance(app, tok);
    else if (view === "avenir") await viewUpcoming(app, tok);
    else if (view === "estimer") await viewPredict(app, tok);
    else await viewMatches(app, tok);
  } catch (e) { if (!tok.stale) app.innerHTML = `<div style="padding-top:20px">${failure(e)}</div>`; }
  if (!tok.stale && !keepScroll) { scrollTo({ top: 0, behavior: "auto" }); onScroll(); }
}
async function render() {
  const h = location.hash || "#/";
  const m = h.match(/^#\/match\/(\d+)/);
  const view = h.startsWith("#/performance") ? "performance" : h.startsWith("#/estimer") ? "estimer" : h.startsWith("#/avenir") ? "avenir" : "matchs";
  setNav(view);
  if (!m) closeSheet();
  if (app.dataset.view !== view) await showView(view, !!m);
  if (m) openSheet(m[1]);
}
addEventListener("hashchange", render);
render();
