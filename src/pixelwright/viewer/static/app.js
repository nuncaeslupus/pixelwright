// Viewer shell: the asset list. Asset modes (Look, Compare, Mark, Play) build on this.
export const token = document.querySelector('meta[name="pw-token"]').content;

export async function api(path, body) {
  const init = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-PW-Token": token },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, init);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ? data.error.message : res.statusText);
  return data;
}

async function showAssets() {
  const { assets } = await api("/api/assets");
  const app = document.getElementById("app");
  if (!assets.length) {
    app.innerHTML = '<p class="muted">No assets yet. Create one with <code>pw new</code>.</p>';
    return;
  }
  app.innerHTML = '<div class="cards"></div>';
  for (const a of assets) {
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `<div class="thumb">${a.thumbnail ? `<img alt="" src="${a.thumbnail}">` : ""}</div>
      <strong></strong><div class="muted"></div>`;
    card.querySelector("strong").textContent = a.id;
    card.querySelector(".muted").textContent = a.status;
    app.querySelector(".cards").append(card);
  }
}

showAssets().catch((err) => {
  document.getElementById("app").textContent = err.message;
});
