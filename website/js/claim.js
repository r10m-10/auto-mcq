"use strict"

// EDIT-ME (testing): ad length in seconds. Set to 2-3 for quick tests instead of waiting 25s.
// Overridden at runtime by the admin's offerwall_config.ad_seconds when reachable.
// In video mode the video's own duration overrides this entirely.
const AD_SECONDS = 25
const AD_REWARD = 3
const BALANCE_BUBBLES = 12
const HEADER_BUBBLES = 8
const RING_CIRCUMFERENCE = 2 * Math.PI * 52

const state = {
  deviceId: null,
  balance: null,
  balanceGrid: null,
  headerGrid: null,
  adTimer: null,
  adActive: false,
  adRemaining: 0,
  adSeconds: AD_SECONDS,
  adReward: AD_REWARD,
  videoHandlers: null,
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
  // Ad length lives on the offerwall slot config; fall back to the flat
  // legacy key (derived server-side) if the slot doesn't carry it yet.
  if (cfg.offerwall_config && typeof cfg.offerwall_config.ad_seconds === "number" && cfg.offerwall_config.ad_seconds > 0) {
    state.adSeconds = cfg.offerwall_config.ad_seconds
  } else if (typeof cfg.ad_seconds === "number" && cfg.ad_seconds > 0) {
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
     once the SDK accounts are approved. Three modes today:
       - third_party: pasted HTML rendered into the reward frame, with the
         sandbox gate still running around it as the anti-abuse layer.
       - video:      an in-house MP4 (admin-supplied URL) plays; the ad
         runs exactly as long as the video, and CLAIM unlocks on 'ended'.
       - text:       the sandbox countdown player.
     CLOSE/CANCEL stays enabled the whole time — the ring is informational;
     you can cancel anytime without charge. */
  const modal = $("#rewardModal")
  modal.classList.add("is-open")

  const frame = $("#rewardAdFrame")
  const sandbox = $("#rewardSandbox")
  const video = $("#rewardVideo")
  state.adActive = true

  const isThirdParty = slotCfg && slotCfg.source === "third_party" && slotCfg.third_party_html
  const isVideo = slotCfg && slotCfg.source === "house" && slotCfg.ad_type === "video" && slotCfg.video_url

  if (isThirdParty) {
    sandbox.style.display = "none"
    frame.style.display = "block"
    frame.innerHTML = slotCfg.third_party_html
    startTextAd("WATCHING\u2026")
  } else if (isVideo) {
    frame.style.display = "none"
    sandbox.style.display = "block"
    video.style.display = "block"
    startVideoAd(slotCfg.video_url)
  } else {
    frame.style.display = "none"
    video.style.display = "none"
    sandbox.style.display = "block"
    startTextAd("WATCHING\u2026")
  }

  $("#rewardCancel").focus()
  trackAd("impression")
}

/* Circular countdown ring: full at the start, depleting to empty as the ad
   runs. Purely informational — CLOSE stays enabled the whole time. */
function updateRing(totalSeconds, remaining) {
  const ring = $("#rewardRing")
  if (!ring) return
  const progress = totalSeconds > 0 ? Math.max(0, Math.min(1, remaining / totalSeconds)) : 0
  ring.style.strokeDasharray = String(RING_CIRCUMFERENCE)
  ring.style.strokeDashoffset = String(RING_CIRCUMFERENCE * (1 - progress))
}

function startTextAd(hintText) {
  stopAd()
  const timerEl = $("#rewardTimer")
  const hintEl = $("#rewardHint")
  const claimBtn = $("#rewardClaim")

  state.adRemaining = state.adSeconds
  // EDIT-ME (testing): set to false to keep CLAIM always enabled while the ad runs
  claimBtn.disabled = true
  hintEl.textContent = hintText
  timerEl.textContent = state.adRemaining
  updateRing(state.adSeconds, state.adRemaining)

  state.adTimer = window.setInterval(() => {
    state.adRemaining -= 1
    timerEl.textContent = state.adRemaining
    updateRing(state.adSeconds, state.adRemaining)
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

/* In-house MP4 mode. The video's own duration drives the countdown and the
   ring; CLAIM unlocks when the video actually ends. If the video fails to
   load, fall back to the text sandbox so the flow never dead-ends. */
function startVideoAd(videoUrl) {
  stopAd()
  const video = $("#rewardVideo")
  const timerEl = $("#rewardTimer")
  const hintEl = $("#rewardHint")
  const claimBtn = $("#rewardClaim")

  claimBtn.disabled = true
  hintEl.textContent = "WATCHING\u2026"
  timerEl.textContent = "\u2014"
  updateRing(0, 1)

  const onLoaded = () => {
    if (Number.isFinite(video.duration) && video.duration > 0) {
      state.adSeconds = Math.ceil(video.duration)
      state.adRemaining = state.adSeconds
      timerEl.textContent = state.adRemaining
      updateRing(state.adSeconds, state.adRemaining)
    }
  }
  const onTime = () => {
    if (Number.isFinite(video.duration) && video.duration > 0) {
      state.adRemaining = Math.max(0, Math.ceil(video.duration - video.currentTime))
      timerEl.textContent = state.adRemaining
      updateRing(state.adSeconds, state.adRemaining)
    }
  }
  const onEnded = () => {
    state.adRemaining = 0
    timerEl.textContent = 0
    updateRing(state.adSeconds, 0)
    hintEl.textContent = "AD COMPLETE \u2014 CREDIT READY"
    claimBtn.disabled = false
    claimBtn.focus()
  }
  const onError = () => {
    video.style.display = "none"
    startTextAd("WATCHING\u2026")
  }

  state.videoHandlers = { loadedmetadata: onLoaded, timeupdate: onTime, ended: onEnded, error: onError }
  Object.entries(state.videoHandlers).forEach(([ev, fn]) => video.addEventListener(ev, fn))

  video.muted = true
  video.setAttribute("playsinline", "")
  video.src = videoUrl
  video.play().catch(() => {
    hintEl.textContent = "PRESS PLAY TO WATCH THE AD"
  })
}

function stopAd() {
  if (state.adTimer) {
    window.clearInterval(state.adTimer)
    state.adTimer = null
  }
  const video = $("#rewardVideo")
  if (state.videoHandlers) {
    Object.entries(state.videoHandlers).forEach(([ev, fn]) => video.removeEventListener(ev, fn))
    state.videoHandlers = null
  }
  video.pause()
  video.removeAttribute("src")
  video.load()
}

/* Leaving the tab cancels the ad entirely — switching away means the watch
   is wasted and the modal closes as if the user pressed CLOSE. They have to
   watch the whole ad again, staying in the tab, to claim the credits. When
   they return, a popup explains why the ad closed. */
document.addEventListener("visibilitychange", () => {
  if (document.hidden && state.adActive) {
    state.noticeFromTabLeave = true
    closeAdModal(true)
  } else if (!document.hidden && state.noticeFromTabLeave) {
    state.noticeFromTabLeave = false
    openNoticeModal()
  }
})

function closeAdModal(fromTabLeave) {
  stopAd()
  state.adActive = false
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
