const DATA_URL = "data/players.json";

const state = { players: [], query: "", sort: "value-desc" };
const $ = (id) => document.getElementById(id);

function formatValue(value) {
  if (!Number.isFinite(value)) return "—";
  if (value >= 1_000_000) return `€${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}m`;
  if (value >= 1_000) return `€${Math.round(value / 1_000)}k`;
  return `€${value}`;
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>'"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
}

function render() {
  const query = state.query.trim().toLowerCase();
  let players = state.players.filter((p) => [p.name, p.club, p.nationality].join(" ").toLowerCase().includes(query));

  players.sort((a, b) => {
    if (state.sort === "value-asc") return (a.marketValue || 0) - (b.marketValue || 0);
    if (state.sort === "name-asc") return a.name.localeCompare(b.name);
    if (state.sort === "age-asc") return (a.age ?? 999) - (b.age ?? 999);
    return (b.marketValue || 0) - (a.marketValue || 0);
  });

  $("ranking").innerHTML = players.map((p, i) => `
    <article class="player">
      <div class="rank">${i + 1}</div>
      <div>
        <p class="name">${escapeHtml(p.name)}</p>
        <p class="meta">${escapeHtml(p.club || "Unknown club")} • ${escapeHtml(p.nationality || "Unknown nationality")}${p.age ? ` • ${p.age}` : ""}</p>
      </div>
      <div class="value">${formatValue(p.marketValue)}<small>market value</small></div>
    </article>`).join("");
  $("empty").hidden = players.length !== 0;
}

async function load() {
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.players = Array.isArray(data.players) ? data.players : [];

    const values = state.players.map((p) => p.marketValue).filter(Number.isFinite);
    $("player-count").textContent = state.players.length;
    $("total-value").textContent = formatValue(values.reduce((a, b) => a + b, 0));
    $("top-value").textContent = formatValue(Math.max(...values, 0));
    $("updated").textContent = data.updatedAt ? `Updated ${new Date(data.updatedAt).toLocaleString()}` : "Latest available data";
    render();
  } catch (error) {
    $("updated").textContent = "Could not load the latest ranking data.";
    $("ranking").innerHTML = `<p class="empty">The data feed is unavailable right now. Please try again later.</p>`;
    console.error(error);
  }
}

$("search").addEventListener("input", (event) => { state.query = event.target.value; render(); });
$("sort").addEventListener("change", (event) => { state.sort = event.target.value; render(); });
load();
