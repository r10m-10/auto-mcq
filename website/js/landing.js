"use strict"

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

document.addEventListener("DOMContentLoaded", () => {
  ensurePencilDefs()
  buildHeroSheet()
  prefillHero()
})
