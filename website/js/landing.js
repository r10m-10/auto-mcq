"use strict"

// TODO(store-urls): replace with the real listing URLs once the extension is
// published to each store. Current values are store search/landing pages.
const STORE_URLS = {
  chrome: "https://chrome.google.com/webstore",
  firefox: "https://addons.mozilla.org/en-US/firefox/",
}

const HERO_QUESTIONS = 4
const HERO_OPTIONS = ["A", "B", "C", "D"]
const HERO_PREFILL = [
  [0, 0],
  [1, 1],
  [2, 2],
  [3, 3],
]

function buildHeroSheet() {
  const sheet = document.getElementById("heroSheet")
  if (!sheet) return

  let html =
    '<div class="sheet-cols"><span></span>' +
    HERO_OPTIONS.map((opt) => "<span>" + opt + "</span>").join("") +
    "</div>"

  for (let q = 1; q <= HERO_QUESTIONS; q++) {
    html += '<div class="sheet-row"><span class="q">' + String(q).padStart(2, "0") + "</span>"
    HERO_OPTIONS.forEach((opt, i) => {
      html +=
        '<button class="hero-bubble" type="button" data-q="' +
        q +
        '" data-opt="' +
        i +
        '" aria-pressed="false" aria-label="Question ' +
        q +
        ", option " +
        opt +
        '">' +
        bubbleSVG() +
        "</button>"
    })
    html += "</div>"
  }

  sheet.innerHTML = html
  sheet.querySelectorAll(".hero-bubble").forEach((btn) => {
    btn.addEventListener("click", () => toggleHeroBubble(btn))
  })
}

function toggleHeroBubble(btn) {
  const pressed = btn.getAttribute("aria-pressed") === "true"
  btn.setAttribute("aria-pressed", String(!pressed))
  const bubble = btn.querySelector(".bubble")
  if (bubble) bubble.classList.toggle("filled", !pressed)
}

function prefillHero() {
  const reduce =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  HERO_PREFILL.forEach(([q, opt], idx) => {
    const delay = reduce ? 0 : 700 + idx * 240
    window.setTimeout(() => {
      const btn = document.querySelector(
        '.hero-bubble[data-q="' + (q + 1) + '"][data-opt="' + opt + '"]'
      )
      if (btn && btn.getAttribute("aria-pressed") !== "true") {
        btn.setAttribute("aria-pressed", "true")
        const bubble = btn.querySelector(".bubble")
        if (bubble) bubble.classList.add("filled")
      }
    }, delay)
  })
}

function buildStoreChooser() {
  const modal = document.getElementById("storeModal")
  if (!modal) return

  const lastFocus = { el: null }

  function open() {
    lastFocus.el = document.activeElement
    modal.classList.add("is-open")
    const first = modal.querySelector(".store-card")
    if (first) first.focus()
  }

  function close() {
    modal.classList.remove("is-open")
    if (lastFocus.el && document.contains(lastFocus.el)) lastFocus.el.focus()
  }

  document.querySelectorAll("[data-store-chooser]").forEach((btn) => {
    btn.addEventListener("click", open)
  })

  modal.querySelectorAll(".store-card").forEach((card) => {
    card.addEventListener("click", () => {
      const store = card.dataset.store
      if (STORE_URLS[store]) {
        window.open(STORE_URLS[store], "_blank", "noopener")
      }
      close()
    })
  })

  document.getElementById("storeClose").addEventListener("click", close)
  modal.addEventListener("click", (e) => {
    if (e.target === modal) close()
  })
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("is-open")) close()
  })
}

/* Keep the "3 credits" mentions on the landing page in sync with the
   admin-configured ad reward. Fail-open: if /config is unreachable the
   static numbers stay. */
function syncRewardAmounts() {
  const mentions = document.querySelectorAll(".reward-amount")
  if (!mentions.length) return
  fetch(API_BASE + "/config")
    .then((res) => (res.ok ? res.json() : null))
    .then((cfg) => {
      if (cfg && typeof cfg.ad_reward === "number") {
        mentions.forEach((el) => { el.textContent = cfg.ad_reward })
      }
    })
    .catch(() => {})
}

document.addEventListener("DOMContentLoaded", () => {
  ensurePencilDefs()
  buildHeroSheet()
  prefillHero()
  buildStoreChooser()
  syncRewardAmounts()
})
