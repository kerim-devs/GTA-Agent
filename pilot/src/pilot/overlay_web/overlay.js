"use strict";

const element = (id) => document.getElementById(id);
const skillNames = {
  drive_route: "Route fahren",
  wait: "Warten",
  press: "Taste drücken",
  walk: "Gehen",
  look: "Umschauen",
  shoot: "Zielen und schießen",
};
const skillStates = { running: "Wird ausgeführt", done: "Abgeschlossen", failed: "Unterbrochen", cancelled: "Beendet" };
const skillName = (name) => skillNames[name] || "Aktion";
const text = (id, value, limit = 240) => {
  const content = typeof value === "string" ? value : "";
  element(id).textContent = content.length > limit ? `${content.slice(0, limit - 1)}…` : content;
};

function render(state) {
  text("sentence", state.sentence || "Warte auf eine Entscheidung.", 360);
  element("thinking").hidden = !state.thinking || ["stale", "ended", "waiting"].includes(state.status);
  text("skill", state.skill ? skillName(state.skill.name) : "Bereit");
  text("skill-state", state.skill ? (skillStates[state.skill.status] || "") : "");
  const plan = Array.isArray(state.plan) ? state.plan : [];
  const list = element("plan");
  list.replaceChildren();
  list.hidden = plan.length < 2;
  for (const step of plan.slice(0, 5)) {
    const item = document.createElement("li");
    item.textContent = skillName(step.name);
    list.appendChild(item);
  }
  if (plan.length > 5) {
    const item = document.createElement("li");
    item.textContent = `Weitere ${plan.length - 5} Schritte`;
    list.appendChild(item);
  }
  for (const field of ["objective", "help"]) {
    text(field, state[field]);
    element(`${field}-panel`).hidden = !state[field];
  }
  element("context").hidden = !state.objective && !state.help;
  text("speed", Number.isFinite(state.speed_kmh) ? String(Math.round(state.speed_kmh)) : "—");
  element("distance").hidden = !Number.isFinite(state.distance_m);
  text("distance", state.distance_m >= 1000
    ? `${(state.distance_m / 1000).toLocaleString("de-DE", { maximumFractionDigits: 1 })} km übrig`
    : `${Math.round(state.distance_m)} m übrig`);
  element("takeover").hidden = !state.takeover;
  element("shadow").hidden = !state.shadow;
  const statuses = { waiting: "Warte auf Aufzeichnung", stale: "Keine neuen Daten", live: "", playing: "Aufzeichnung", ended: "Aufzeichnung beendet" };
  text("connection", statuses[state.status] || "Warte auf Aufzeichnung");
}

const updates = new EventSource("/events");
updates.onmessage = (event) => {
  try {
    render(JSON.parse(event.data));
  } catch {
    // Keep the last good display if a connection delivers an incomplete event.
  }
};
updates.onerror = () => {
  text("connection", "Verbindung wird hergestellt");
  element("thinking").hidden = true;
};
