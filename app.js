const data = window.TITO_DATA;
const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];

const saved = new Set(JSON.parse(localStorage.getItem("tito-ny-saved") || "[]"));
function persist() { localStorage.setItem("tito-ny-saved", JSON.stringify([...saved])); }

function usd(n) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

const state = { filter: "all", q: "", sort: "price" };

function each(l) {
  const n = l.beds >= 3 ? 3 : (l.beds || 2);
  return l.rent / n;
}

function matches(l) {
  const f = state.filter;
  if (f === "saved" && !saved.has(l.id)) return false;
  if (f === "2" && l.beds !== 2) return false;
  if (f === "3" && l.beds !== 3) return false;
  if (f === "west" && l.neighborhood !== "West Village") return false;
  if (f === "east" && l.neighborhood !== "East Village") return false;
  if (f === "greenwich" && l.neighborhood !== "Greenwich Village") return false;
  if (f === "soho" && !["SoHo","NoHo","NoLita","Hudson Square"].includes(l.neighborhood)) return false;
  if (f === "chelsea" && !["Chelsea","Meatpacking"].includes(l.neighborhood)) return false;
  if (state.q) {
    const blob = [l.name, l.headline, l.address, l.neighborhood, l.note, l.why].join(" ").toLowerCase();
    if (!blob.includes(state.q.toLowerCase())) return false;
  }
  return true;
}

function sorted(list) {
  const out = [...list];
  if (state.sort === "price") out.sort((a,b) => a.rent - b.rent);
  if (state.sort === "each") out.sort((a,b) => each(a) - each(b));
  if (state.sort === "beds") out.sort((a,b) => (b.beds||0) - (a.beds||0));
  if (state.sort === "name") out.sort((a,b) => a.name.localeCompare(b.name));
  return out;
}

function card(l) {
  const photo = l.photo
    ? `<div class="photo" style="background-image:url('${l.photo}')"></div>`
    : `<div class="photo none">${l.neighborhood.slice(0,2)}</div>`;
  const heart = saved.has(l.id) ? "on" : "";
  const split = l.beds >= 3 ? 3 : 2;
  const stats = [
    l.beds ? `${l.beds} bed` : null,
    l.baths ? `${l.baths} bath` : null,
    l.sqft ? `${l.sqft} sqft` : null,
    `${usd(each(l))} each / ${split}`
  ].filter(Boolean).map(s => `<span class="stat">${s}</span>`).join("");
  return `<article class="card" data-id="${l.id}">
    ${photo}
    <span class="badge ready">${l.neighborhood}</span>
    <button class="heart ${heart}" data-save="${l.id}" aria-label="Save">♥</button>
    <div class="body">
      <div class="where">${l.address}</div>
      <h2>${l.name}</h2>
      <div class="sub">${l.headline}</div>
      <div class="stats">${stats}</div>
      <div class="price">${usd(l.rent)} / mo</div>
    </div>
  </article>`;
}

function render() {
  const list = sorted(data.listings.filter(matches));
  $("#count").textContent = `${list.length} of ${data.listings.length}`;
  $("#grid").innerHTML = list.length ? list.map(card).join("") : `<div class="empty">${data.empty || "Nothing in this filter."}</div>`;
}

function openDrawer(id) {
  const l = data.listings.find(x => x.id === id);
  if (!l) return;
  const split = l.beds >= 3 ? 3 : 2;
  const photo = l.photo
    ? `<div class="photo" style="background-image:url('${l.photo}')"></div>`
    : `<div class="photo none">${l.neighborhood}</div>`;
  $("#drawer").innerHTML = `
    <div class="close-bar">
      <button type="button" class="close" id="close" aria-label="Close">✕</button>
    </div>
    ${photo}
    <div class="drawer-inner">
      <div class="where">${l.address} · ${l.neighborhood}</div>
      <h2>${l.name}</h2>
      <div class="price">${usd(l.rent)} / mo · ${usd(each(l))} each if ${split}</div>
      <p class="why">${l.why}</p>
      <p class="note">${l.note || ""}</p>
      <dl class="facts">
        <div><dt>Layout</dt><dd>${l.beds} bed · ${l.baths} bath${l.sqft ? " · " + l.sqft + " sqft" : ""}</dd></div>
        <div><dt>Available</dt><dd>${l.available || "See listing"}</dd></div>
        <div><dt>Source</dt><dd>${l.source}${l.ref ? " · " + l.ref : ""}</dd></div>
        <div><dt>Added</dt><dd>${l.added}</dd></div>
      </dl>
      <a class="cta" href="${l.url}" target="_blank" rel="noopener">Open the listing</a>
    </div>`;
  $("#drawer").classList.add("on");
  $("#shade").classList.add("on");
}

function closeDrawer() {
  $("#drawer").classList.remove("on");
  $("#shade").classList.remove("on");
}

document.addEventListener("click", (e) => {
  if (e.target.closest("#close") || e.target.id === "shade") {
    e.preventDefault();
    closeDrawer();
    return;
  }
  const save = e.target.closest("[data-save]");
  if (save) {
    e.stopPropagation();
    const id = save.dataset.save;
    if (saved.has(id)) saved.delete(id); else saved.add(id);
    persist(); render();
    return;
  }
  const cardEl = e.target.closest(".card");
  if (cardEl) openDrawer(cardEl.dataset.id);
  const chip = e.target.closest(".chip");
  if (chip) {
    state.filter = chip.dataset.filter;
    $$(".chip").forEach(c => c.classList.toggle("on", c === chip));
    render();
  }
});

document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
$("#search").addEventListener("input", (e) => { state.q = e.target.value; render(); });
$("#sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });

$("#updated").textContent = data.updatedLabel;
render();
