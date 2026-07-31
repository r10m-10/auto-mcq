"use strict"

const API_BASE = "https://automcq.reyaanshsharma.com"
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function looksLikeUuid(value) {
  return typeof value === "string" && UUID_RE.test(value)
}

/* Injects the shared pencil-hatch SVG pattern used by every bubble. */
function ensurePencilDefs() {
  if (document.getElementById("automcq-defs")) return
  const holder = document.createElement("div")
  holder.innerHTML =
    '<svg id="automcq-defs" width="0" height="0" aria-hidden="true" style="position:absolute">' +
    "<defs>" +
    '<pattern id="automcq-hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">' +
    '<rect width="4" height="4" fill="#8B93A3"/>' +
    '<line x1="0" y1="0" x2="0" y2="4" stroke="#ECEFF4" stroke-width="1.1"/>' +
    "</pattern>" +
    "</defs>" +
    "</svg>"
  document.body.appendChild(holder.firstElementChild)
}

/* Single OMR bubble as inline SVG. Requires ensurePencilDefs() first. */
function bubbleSVG() {
  return (
    '<svg class="bubble" viewBox="0 0 24 24" aria-hidden="true">' +
    '<ellipse class="bubble-outline" cx="12" cy="12" rx="8.5" ry="8.5"/>' +
    '<ellipse class="bubble-fill" cx="12" cy="12" rx="7.5" ry="7.5" fill="url(#automcq-hatch)"/>' +
    "</svg>"
  )
}

/* The signature element: filled bubbles = credits available.
   Newly filled bubbles draw in with a pencil-scribble animation, staggered
   left-to-right, unless the user prefers reduced motion. */
class BubbleGrid {
  constructor(rootEl, options) {
    options = options || {}
    this.root = rootEl
    this.total = options.total || 12
    this.filled = typeof options.filled === "number" ? options.filled : 0
    this.root.classList.add("bubble-grid")
    this.root.setAttribute("role", "img")
    this.root.innerHTML = ""
    this.bubbles = []
    for (let i = 0; i < this.total; i++) {
      const cell = document.createElement("div")
      cell.className = "bubble-cell"
      cell.innerHTML = bubbleSVG()
      this.bubbles.push(cell.querySelector(".bubble"))
      this.root.appendChild(cell)
    }
    this.setFilled(this.filled, { animate: false })
  }

  setFilled(count, options) {
    options = options || {}
    const clamped = Math.max(0, Math.min(this.total, Math.round(count)))
    const reduce =
      window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    const animate = options.animate !== false && !reduce
    this.filled = clamped
    this.root.setAttribute("aria-label", "Credits: " + clamped + " of " + this.total)
    this.bubbles.forEach((bubble, index) => {
      const shouldFill = index < clamped
      const filled = bubble.classList.contains("filled")
      if (shouldFill && !filled) {
        if (animate) {
          window.setTimeout(() => bubble.classList.add("filled"), index * 110)
        } else {
          bubble.classList.add("filled")
        }
      } else if (!shouldFill && filled) {
        bubble.classList.remove("filled")
      }
    })
  }
}

async function apiFetch(path, options) {
  options = options || {}
  const res = await fetch(
    API_BASE + path,
    Object.assign({ headers: { "Content-Type": "application/json" } }, options)
  )
  let data = null
  try {
    data = await res.json()
  } catch (e) {
    /* non-JSON error body */
  }
  if (!res.ok) {
    let detail = "HTTP " + res.status
    if (data && data.detail) {
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return data
}

function linkDevice(deviceId) {
  return apiFetch("/link-device", { method: "POST", body: JSON.stringify({ device_id: deviceId }) })
}

function getBalance(deviceId) {
  return apiFetch("/balance?device_id=" + encodeURIComponent(deviceId))
}

function getHistory(deviceId) {
  return apiFetch("/history?device_id=" + encodeURIComponent(deviceId))
}

function claimSandbox(deviceId) {
  return apiFetch("/offerwall/sandbox-claim", {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId }),
  })
}
