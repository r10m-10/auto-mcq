"use strict"

// EDIT-ME (testing): ad length in seconds. Set to 2-3 for quick tests instead of waiting 25s.
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
  pendingFlash: null,
  noticeFromTabLeave: false,
}

function $(sel) {
  return document.querySelector(sel)
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
     Fail-open (default true) so a config fetch failure never blocks ads. */
  let enabled = true
  try {
    const res = await fetch(API_BASE + "/config")
    if (res.ok) {
      const cfg = await res.json()
      enabled = cfg.offerwall_enabled !== false
    }
  } catch (e) {
    /* keep default */
  }
  if (!enabled) {
    openNoticeModal("No ads to display right now. Check back later.", "NO ADS")
    return
  }
  openAdModal()
}

function openAdModal() {
  /* TODO(real-offerwall): mount the real offerwall / AdSense iframe here
     once the SDK accounts are approved. For now, a sandbox countdown. */
  const modal = $("#rewardModal")
  modal.classList.add("is-open")
  startAdCountdown("WATCHING\u2026")
  $("#rewardCancel").focus()
}

function startAdCountdown(hintText) {
  if (state.adTimer) {
    window.clearInterval(state.adTimer)
    state.adTimer = null
  }
  const timerEl = $("#rewardTimer")
  const hintEl = $("#rewardHint")
  const claimBtn = $("#rewardClaim")

  state.adRemaining = AD_SECONDS
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
    closeAdModal()
  } else if (!document.hidden && state.noticeFromTabLeave) {
    state.noticeFromTabLeave = false
    openNoticeModal()
  }
})

function closeAdModal() {
  if (state.adTimer) {
    window.clearInterval(state.adTimer)
    state.adTimer = null
  }
  $("#rewardModal").classList.remove("is-open")
  $("#rewardClaim").disabled = true
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
  try {
    const res = await claimSandbox(state.deviceId)
    applyBalance(res.credits_balance)
    closeAdModal()
    loadHistory(state.deviceId)
    window.postMessage(
      { type: "automcq-claim", delta: res.delta, balance: res.credits_balance },
      "*"
    )
    deferEarnedFlash(AD_REWARD)
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
