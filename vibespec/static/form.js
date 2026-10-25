/* Guided form: anchor chips, example fill, validation, request body. */
(() => {
  const { el, $ } = VS;
  const MAX_ANCHORS = 3, SUGGESTIONS = ["Muji", "Patagonia", "Aesop", "IKEA", "Carhartt", "Lululemon"];
  const EXAMPLE = {
    concept: "Minimalist, eco-conscious 40-room boutique hotel for mindful travellers", city: "New York City",
    anchors: ["Muji", "Patagonia"], goals: "Calm minimalist sound, a small library of nature and sustainability books, natural low-waste amenities, local places to explore on foot",
    max_place_price_level: "3", min_place_rating: "4.0", min_book_year: "2012", amenity_unit_budget_usd: "30", exclude_terms: "Starbucks",
  };
  const form = $("#f"), box = $("#chips"), input = $("#anchor-in"), err = $("#anchor-err");
  let anchors = [];
  VS.confirmed = {};

  function draw() {
    box.querySelectorAll(".chip").forEach((c) => c.remove());
    anchors.forEach((name, i) => box.insertBefore(el("span", { class: `chip ${VS.ANCHOR_CLASS[i]}` }, name,
      el("button", { type: "button", "aria-label": `Remove ${name}`, onclick: () => { anchors.splice(i, 1); draw(); input.focus(); } }, "×")), input));
    input.disabled = anchors.length >= MAX_ANCHORS;
    input.placeholder = anchors.length >= MAX_ANCHORS ? "Three anchors is the maximum" : "Type a brand, press Enter";
    $("#suggest").querySelectorAll("button").forEach((b) => { b.disabled = anchors.includes(b.textContent) || anchors.length >= MAX_ANCHORS; b.style.opacity = b.disabled ? ".4" : ""; });
  }
  function add(raw) {
    const name = raw.trim().replace(/\s+/g, " ");
    if (!name) return;
    err.textContent = "";
    if (anchors.some((a) => a.toLowerCase() === name.toLowerCase())) { err.textContent = `${name} is already added.`; return; }
    if (anchors.length >= MAX_ANCHORS) { err.textContent = "Three anchors is the maximum."; return; }
    anchors.push(name); input.value = ""; draw();
  }
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(input.value); }
    else if (e.key === "Backspace" && !input.value && anchors.length) { anchors.pop(); draw(); }
  });
  input.addEventListener("blur", () => add(input.value));
  SUGGESTIONS.forEach((s) => $("#suggest").append(el("button", { type: "button", onclick: () => add(s) }, s)));

  function setAll(values) {
    for (const [k, v] of Object.entries(values)) if (k !== "anchors" && form.elements[k]) form.elements[k].value = v;
    anchors = [...values.anchors]; VS.confirmed = {}; draw();
    if (values.max_place_price_level) $("details.opt").open = true;
  }
  VS.form = {
    fillExample: () => setAll(EXAMPLE),
    body() {
      add(input.value);
      const v = (n) => form.elements[n].value.trim();
      return { concept: v("concept"), city: v("city"), anchors: [...anchors], goals: v("goals"), confirmed: VS.confirmed,
        constraints: Object.fromEntries(["max_place_price_level", "min_place_rating", "min_book_year", "amenity_unit_budget_usd", "exclude_terms", "hotel_location"].map((k) => [k, v(k) || null])) };
    },
    validate() {
      const b = VS.form.body(), problems = [];
      if (!b.concept) problems.push(["concept", "Describe your hotel in a sentence."]);
      if (!b.city) problems.push(["city", "Enter the city to search places in."]);
      if (b.anchors.length < 2) { err.textContent = "Add at least two anchors (brands your guests love)."; problems.push(["anchor-in", err.textContent]); }
      $("#form-err").textContent = problems.filter(([id]) => id !== "anchor-in").map(([, m]) => m).join(" ");
      if (problems.length) $(`#${problems[0][0]}`).focus();
      return !problems.length;
    },
    summary: () => { const b = VS.form.body(); return `${b.city}. Anchors: ${b.anchors.join(", ")}.`; },
  };
  $("#fill").addEventListener("click", VS.form.fillExample);
  $("#use-example").addEventListener("click", () => { VS.form.fillExample(); $("#compose").scrollIntoView(); $("#go").focus({ preventScroll: true }); });
  draw();
})();
