"use strict"

// EDIT-ME (testing): ad length in seconds. Set to 2-3 for quick tests instead of waiting 25s.
// Overridden at runtime by the admin's offerwall_config.ad_seconds when reachable.
const AD_SECONDS = 25
const AD_REWARD = 3
const BALANCE_BUBBLES = 12
const HEADER_BUBBLES = 8

const state = {
  deviceId: null,
  balance: null,
  balanceGrid: null,
  headerGrid: null,
  adTimer: null,
  adRemaining: 0,
  adSeconds: AD_SECONDS,
  adReward: AD_REWARD,
  pendingFlash: null,
  noticeFromTabLeave: false,
}

function $(sel) {
  return document.querySelector(sel)
}

function $$(sel) {
  return Array.from(document.querySelectorAll(sel))
}

async function init() {
  ensurePencilDefs()
  state.balanceGrid = new BubbleGrid($("#balanceBubbles"), {
    total: BALANCE_BUBBLES,
    filled: 0,
  })
  state.headerGrid = new BubbleGrid($("#headerBubbles"), {
    total: HEADER_BUBBLES,
    filled: 0,
  })

  const params = new URLSearchParams(window.location.search)
  let device = params.get("device_id")
  if (!device || !looksLikeUuid(device)) {
    device = localStorage.getItem("automcq_device_id")
  }

  if (device && looksLikeUuid(device)) {
    await linkAndLoad(device)
  } else {
    showUnlinked()
  }

  bindEvents()
}

function showUnlinked() {
  setStatus("UNLINKED", "stamp--off")
  $("#deviceShort").textContent = "\u2014"
  $("#deviceState").textContent =
    "No device ID found in this link. Paste the device ID from the extension popup below to connect."
  $("#deviceState").className = "device-meta"
  $("#watchRewardBtn").disabled = true
  openManualLink()
  $("#historyEmpty").textContent =
    "No activity yet \u2014 link your device to see your ledger."
}

async function linkAndLoad(deviceId) {
  state.deviceId = deviceId
  $("#deviceShort").textContent = deviceId.slice(0, 8).toUpperCase() + "\u2026"

  try {
    const balance = await getBalance(deviceId)
    localStorage.setItem("automcq_device_id", deviceId)
    applyBalance(balance.credits_balance)
    setStatus("LINKED", "stamp--ok")
    $("#deviceState").textContent = deviceId
    $("#deviceState").className = "device-id"
    $("#watchRewardBtn").disabled = false
    closeManualLink()
    loadHistory(deviceId)
  } catch (err) {
    if (err.status === 404) {
      forgetDevice()
    } else {
      setApiError(err)
    }
  }
}

function forgetDevice() {
  state.deviceId = null
  localStorage.removeItem("automcq_device_id")
  const url = new URL(window.location.href)
  url.searchParams.delete("device_id")
  history.replaceState(null, "", url.pathname + url.search)
  showUnlinked()
}

function setStatus(text, cls) {
  const el = $("#claimStatus")
  el.textContent = text
  el.className = "claim-status stamp " + cls
}

function setApiError(err) {
  setStatus("API ERROR", "stamp--off")
  $("#deviceState").textContent =
    "Could not reach the credit server (HTTP " + (err.status || "?") + "). Check your connection and try again."
  $("#deviceState").className = "device-meta"
  $("#watchRewardBtn").disabled = true
  openManualLink()
}

function setCooldownError(err) {
  setStatus("AD COOLDOWN", "stamp--off")
  $("#deviceState").textContent = err.message
  $("#deviceState").className = "device-meta"
}

function applyBalance(count) {
  state.balance = count
  state.balanceGrid.setFilled(count)
  state.headerGrid.setFilled(Math.min(count, HEADER_BUBBLES))
  $("#balanceCount").textContent = String(count).padStart(2, "0")
  $("#headerBalance").textContent = count
  $("#headerCredits").classList.add("is-visible")
}

async function loadHistory(deviceId) {
  try {
    const rows = await getHistory(deviceId)
    renderHistory(rows)
  } catch (err) {
    /* keep the empty state; balance is the live source of truth */
  }
}

function renderHistory(rows) {
  const table = $("#historyTable")
  const empty = $("#historyEmpty")
  if (!rows.length) {
    empty.textContent = "No credit activity yet."
    empty.hidden = false
    table.hidden = true
    return
  }
  empty.hidden = true
  table.hidden = false
  const tbody = table.querySelector("tbody")
  tbody.innerHTML = rows
    .map((row) => {
      const sign = row.delta > 0 ? "+" : ""
      const cls = row.delta > 0 ? "delta-pos" : row.delta < 0 ? "delta-neg" : ""
      const reason =
        row.reason === "ad_reward" ? "AD REWARD" : String(row.reason || "").toUpperCase()
      return (
        "<tr><td>" +
        esc(row.timestamp) +
        "</td><td>" +
        esc(reason) +
        "</td><td class=\"" +
        cls +
        "\">" +
        sign +
        row.delta +
        "</td></tr>"
      )
    })
    .join("")
}

function esc(text) {
  const div = document.createElement("div")
  div.textContent = String(text)
  return div.innerHTML
}

function openManualLink() {
  const details = document.querySelector(".manual-link")
  if (details) details.open = true
}

function closeManualLink() {
  const details = document.querySelector(".manual-link")
  if (details) details.open = false
}

function bindEvents() {
  $("#watchRewardBtn").addEventListener("click", handleWatchReward)
  $("#rewardClose").addEventListener("click", closeAdModal)
  $("#rewardCancel").addEventListener("click", closeAdModal)
  $("#rewardClaim").addEventListener("click", claimReward)
  $("#noticeClose").addEventListener("click", closeNoticeModal)
  $("#noticeCloseBtn").addEventListener("click", closeNoticeModal)

  $("#manualLinkForm").addEventListener("submit", (e) => {
    e.preventDefault()
    const value = $("#manualDeviceId").value.trim()
    if (!looksLikeUuid(value)) {
      setStatus("INVALID DEVICE ID", "stamp--off")
      return
    }
    linkAndLoad(value)
  })
}

async function handleWatchReward() {
  /* Respect the admin's offerwall_enabled switch: when ads are off, tell
     the user there is nothing to watch instead of opening the ad modal.
     Fail-open (default true) so a config fetch failure never blocks ads.
     Also picks up the admin's ad reward amount, ad length, and the
     offerwall slot config (house text or pasted third-party HTML). */
  let cfg = {}
  try {
    const res = await fetch(API_BASE + "/config")
    if (res.ok) {
      cfg = await res.json()
    }
  } catch (e) {
    /* keep defaults */
  }
  if (cfg.offerwall_enabled === false) {
    openNoticeModal("No ads to display right now. Check back later.", "NO ADS")
    return
  }
  if (typeof cfg.ad_reward === "number" && cfg.ad_reward > 0) {
    state.adReward = cfg.ad_reward
  }
  if (typeof cfg.ad_seconds === "number" && cfg.ad_seconds > 0) {
    state.adSeconds = cfg.ad_seconds
  }
  applyRewardCopy(state.adReward)
  openAdModal(cfg.offerwall_config || {})
}

/* Keep the visible "+N" amounts across the claim page in sync with the
   admin's configured reward. */
function applyRewardCopy(reward) {
  $$(".reward-amount").forEach(el => { el.textContent = reward })
}

function trackAd(eventType) {
  try {
    fetch(API_BASE + "/ads/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot: "offerwall", event_type: eventType, device_id: state.deviceId }),
    }).catch(() => {})
  } catch (e) {
    /* fire-and-forget */
  }
}

function openAdModal(slotCfg) {
  /* TODO(real-offerwall): mount the real offerwall / AdSense iframe here
     once the SDK accounts are approved. For now, a sandbox countdown —
     and if the admin has pasted third-party HTML for the offerwall slot,
     it is rendered into the reward frame with the sandbox gate still
     running around it as the anti-abuse layer. */
  const modal = $("#rewardModal")
  modal.classList.add("is-open")

  const frame = $("#rewardAdFrame")
  const sandbox = $("#rewardSandbox")
  if (slotCfg && slotCfg.source === "third_party" && slotCfg.third_party_html) {
    sandbox.style.display = "none"
    frame.style.display = "block"
    frame.innerHTML = slotCfg.third_party_html
  } else {
    frame.style.display = "none"
    sandbox.style.display = "block"
  }

  startAdCountdown("WATCHING\u2026")
  $("#rewardCancel").focus()
  trackAd("impression")
}

function startAdCountdown(hintText) {
  if (state.adTimer) {
    window.clearInterval(state.adTimer)
    state.adTimer = null
  }
  const timerEl = $("#rewardTimer")
  const hintEl = $("#rewardHint")
  const claimBtn = $("#rewardClaim")

  state.adRemaining = state.adSeconds
  // EDIT-ME (testing): set to false to keep CLAIM always enabled while the ad runs
  claimBtn.disabled = true
  hintEl.textContent = hintText
  timerEl.textContent = state.adRemaining

  state.adTimer = window.setInterval(() => {
    state.adRemaining -= 1
    timerEl.textContent = state.adRemaining
    if (state.adRemaining <= 0) {
      window.clearInterval(state.adTimer)
      state.adTimer = null
      hintEl.textContent = "AD COMPLETE \u2014 CREDIT READY"
      // EDIT-ME (testing): set to true to enable CLAIM immediately when the ad ends
      claimBtn.disabled = false
      claimBtn.focus()
    }
  }, 1000)
}

/* Leaving the tab cancels the ad entirely — switching away means the watch
   is wasted and the modal closes as if the user pressed CLOSE. They have to
   watch the whole ad again, staying in the tab, to claim the credits. When
   they return, a popup explains why the ad closed. */
document.addEventListener("visibilitychange", () => {
  if (document.hidden && state.adTimer) {
    state.noticeFromTabLeave = true
    closeAdModal(true)
  } else if (!document.hidden && state.noticeFromTabLeave) {
    state.noticeFromTabLeave = false
    openNoticeModal()
  }
})

function closeAdModal(fromTabLeave) {
  if (state.adTimer) {
    window.clearInterval(state.adTimer)
    state.adTimer = null
  }
  $("#rewardModal").classList.remove("is-open")
  $("#rewardClaim").disabled = true
  if (!fromTabLeave) trackAd("close")
}

function openNoticeModal(body, title) {
  if (body) $("#noticeBody").textContent = body
  if (title) $("#noticeTitle").textContent = title
  $("#noticeModal").classList.add("is-open")
  $("#noticeClose").focus()
}

function closeNoticeModal() {
  $("#noticeModal").classList.remove("is-open")
}

async function claimReward() {
  const btn = $("#rewardClaim")
  btn.disabled = true
  trackAd("click")
  try {
    const res = await claimSandbox(state.deviceId)
    applyBalance(res.credits_balance)
    closeAdModal()
    loadHistory(state.deviceId)
    window.postMessage(
      { type: "automcq-claim", delta: res.delta, balance: res.credits_balance },
      "*"
    )
    deferEarnedFlash(state.adReward)
  } catch (err) {
    if (err.status === 429) {
      setCooldownError(err)
    } else {
      setApiError(err)
    }
    closeAdModal()
  } finally {
    btn.disabled = false
  }
}

/* The "+3 CREDITS EARNED" stamp is held until the sponsor card overlay is
   closed, so the sponsor creative gets full attention first. The overlay is
   injected by the extension content script, which posts
   "automcq-sponsor-closed" when the user presses CLOSE. If no card appears
   (extension not installed), the fallback timer plays the stamp anyway. */
let earnedFlashTimer = null

function deferEarnedFlash(amount) {
  if (earnedFlashTimer) {
    window.clearTimeout(earnedFlashTimer)
    earnedFlashTimer = null
  }
  state.pendingFlash = amount
  earnedFlashTimer = window.setTimeout(playEarnedFlash, 4000)
}

function playEarnedFlash() {
  if (earnedFlashTimer) {
    window.clearTimeout(earnedFlashTimer)
    earnedFlashTimer = null
  }
  if (state.pendingFlash) {
    flashEarned(state.pendingFlash)
    state.pendingFlash = null
  }
}

window.addEventListener("message", (event) => {
  if (event.source !== window) return
  const data = event.data
  if (!data || data.type !== "automcq-sponsor-closed") return
  playEarnedFlash()
})

function flashEarned(amount) {
  const existing = document.getElementById("earnedStamp")
  if (existing) existing.remove()
  const stamp = document.createElement("span")
  stamp.className = "stamp stamp--earned"
  stamp.id = "earnedStamp"
  stamp.textContent = "CREDITS EARNED +" + amount
  $("#balanceCount").closest(".balance-panel").appendChild(stamp)
  window.setTimeout(() => {
    if (stamp.parentNode) stamp.parentNode.removeChild(stamp)
  }, 2600)
}

document.addEventListener("DOMContentLoaded", init)
