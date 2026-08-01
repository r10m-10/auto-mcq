const API_BASE = "https://automcq.reyaanshsharma.com"
let CLICK_COSTS = { normal: 1, fast: 4 }

const status = document.querySelector(".cur-status")
const balanceEl = document.querySelector(".credits-balance")
const popupContent = document.getElementById("popupContent")
const toggle = document.getElementById("extensionToggle")
const toastOverlay = document.getElementById("toastOverlay")
const toastMessage = document.getElementById("toastMessage")
const toastClose = document.getElementById("toastClose")
const infoBtn = document.querySelector(".info-btn")
const infoOverlay = document.getElementById("infoOverlay")
const claimBtn = document.getElementById("claimBtn")
const menuBtn = document.getElementById("menuBtn")
const menu = document.getElementById("menu")
const themeSwitch = document.getElementById("themeSwitch")
const copyIdBtn = document.getElementById("copyIdBtn")
const ledgerBtn = document.getElementById("ledgerBtn")
const privacyBtn = document.getElementById("privacyBtn")
const homeBtn = document.getElementById("homeBtn")
const resetIdBtn = document.getElementById("resetIdBtn")
const resetOverlay = document.getElementById("resetOverlay")
const resetConfirmBtn = document.getElementById("resetConfirmBtn")
const resetCancelBtn = document.getElementById("resetCancelBtn")
const sponsorOverlay = document.getElementById("sponsorOverlay")
const sponsorDelta = document.getElementById("sponsorDelta")
const sponsorClose = document.getElementById("sponsorClose")
const sponsorAdCta = document.getElementById("sponsorAdCta")

let deviceId = null
let creditsBalance = null
let currentMode = "normal"
let extensionEnabled = true
let sponsorCardEnabled = true

/* Respect the admin's sponsor_card_enabled switch: when ads are off, the
   popup sponsor card never appears, and any pending claim is dropped so it
   can't resurface if the switch is later turned back on. Fail-open (default
   true) so a config fetch failure never hides a card that should show.

   Also picks up the card's house ad copy (name/sub/CTA + URL) and the
   credit economy (normal/fast costs, ad reward) so the popup reflects the
   admin's config. */
async function loadSponsorCardSetting() {
    try {
        const res = await fetch(API_BASE + "/config")
        if (!res.ok) return
        const cfg = await res.json()
        sponsorCardEnabled = cfg.sponsor_card_enabled !== false
        if (!sponsorCardEnabled) {
            await chrome.storage.local.remove("last_claim")
        }
        applyCardConfig(cfg.card_config)
        applyEconomy(cfg)
    } catch {
        /* keep default */
    }
}

function applyCardConfig(slotCfg) {
    if (!slotCfg) return
    const nameEl = document.getElementById("sponsorAdName")
    const subEl = document.getElementById("sponsorAdSub")
    const ctaEl = document.getElementById("sponsorAdCta")
    if (nameEl && slotCfg.ad_name) nameEl.textContent = slotCfg.ad_name
    if (subEl && slotCfg.ad_sub) subEl.textContent = slotCfg.ad_sub
    if (ctaEl && slotCfg.ad_cta) ctaEl.textContent = slotCfg.ad_cta
}

function applyEconomy(cfg) {
    if (typeof cfg.normal_cost === "number") CLICK_COSTS.normal = cfg.normal_cost
    if (typeof cfg.fast_cost === "number") CLICK_COSTS.fast = cfg.fast_cost
}

/* Fire-and-forget ad metric; never blocks the card. */
function trackCard(eventType) {
    try {
        chrome.storage.local.get("device_id").then(function (stored) {
            fetch(API_BASE + "/ads/event", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slot: "card",
                    event_type: eventType,
                    device_id: stored.device_id || null,
                }),
            }).catch(function () {})
        })
    } catch (e) {
        /* ignore */
    }
}

function getClickType() {
    return currentMode === "fast" ? "premium_click" : "normal_click"
}

function applyDisabledState(disabled) {
    popupContent.classList.toggle("disabled", disabled)
    status.textContent = disabled ? "DISABLED" : "ACTIVE"
    toggle.classList.toggle("is-off", disabled)
    toggle.setAttribute("aria-pressed", String(!disabled))
    toggle.setAttribute("aria-label", disabled ? "Enable AutoMCQ" : "Disable AutoMCQ")
}

function showToast(msg) {
    toastMessage.textContent = msg
    toastOverlay.classList.add("visible")
}

function hideToast() {
    toastOverlay.classList.remove("visible")
}

toastClose.addEventListener("click", hideToast)
toastOverlay.addEventListener("click", function (e) {
    if (e.target === toastOverlay) hideToast()
})

function showInfo() {
    infoOverlay.classList.add("visible")
}

function hideInfo() {
    infoOverlay.classList.remove("visible")
}

infoBtn.addEventListener("click", showInfo)
infoOverlay.addEventListener("click", function (e) {
    if (e.target === infoOverlay) hideInfo()
})

document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
        hideToast()
        hideInfo()
        setMenuOpen(false)
        hideReset()
    }
})

claimBtn.addEventListener("click", async function () {
    const stored = await chrome.storage.local.get("device_id")
    const id = stored.device_id || deviceId
    chrome.tabs.create({ url: `${API_BASE}/claim?device_id=${encodeURIComponent(id)}` })
})

/* ---------- Menu ---------- */

const THEME_KEY = "theme"

function setMenuOpen(open) {
    menu.classList.toggle("is-open", open)
    menu.setAttribute("aria-hidden", String(!open))
    menuBtn.setAttribute("aria-expanded", String(open))
}

menuBtn.addEventListener("click", function () {
    setMenuOpen(!menu.classList.contains("is-open"))
})

document.addEventListener("click", function (e) {
    if (!menu.classList.contains("is-open")) return
    if (menu.contains(e.target) || menuBtn.contains(e.target)) return
    setMenuOpen(false)
})

function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme)
    themeSwitch.setAttribute("aria-checked", String(theme === "dark"))
}

themeSwitch.addEventListener("click", async function () {
    const next =
        document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"
    applyTheme(next)
    await chrome.storage.local.set({ [THEME_KEY]: next })
})

copyIdBtn.addEventListener("click", async function () {
    const stored = await chrome.storage.local.get("device_id")
    const id = stored.device_id || deviceId
    if (!id) {
        showToast("NO DEVICE ID YET")
        setMenuOpen(false)
        return
    }
    try {
        await navigator.clipboard.writeText(id)
        showToast("DEVICE ID COPIED")
    } catch (e) {
        showToast("COPY FAILED \u2014 TRY AGAIN")
    }
    setMenuOpen(false)
})

ledgerBtn.addEventListener("click", function () {
    const id = encodeURIComponent(deviceId || "")
    chrome.tabs.create({ url: `${API_BASE}/claim?device_id=${id}` })
    setMenuOpen(false)
})

privacyBtn.addEventListener("click", function () {
    chrome.tabs.create({ url: `${API_BASE}/privacy` })
    setMenuOpen(false)
})

homeBtn.addEventListener("click", function () {
    chrome.tabs.create({ url: API_BASE })
    setMenuOpen(false)
})

function showReset() {
    setMenuOpen(false)
    resetOverlay.classList.add("visible")
}

function hideReset() {
    resetOverlay.classList.remove("visible")
}

resetIdBtn.addEventListener("click", showReset)

resetOverlay.addEventListener("click", function (e) {
    if (e.target === resetOverlay) hideReset()
})

resetCancelBtn.addEventListener("click", hideReset)

resetConfirmBtn.addEventListener("click", async function () {
    const oldId = deviceId
    if (oldId) {
        try {
            await fetch(`${API_BASE}/device?device_id=${encodeURIComponent(oldId)}`, {
                method: "DELETE",
            })
        } catch {
            // device may already be gone or unreachable; reset locally anyway
        }
    }
    deviceId = crypto.randomUUID()
    await chrome.storage.local.set({ device_id: deviceId })
    hideReset()
    await linkAndFetchBalance()
    showToast("DEVICE ID RESET")
})

/* ---------- Sponsor card ---------- */

function showSponsor(claim) {
    if (!sponsorCardEnabled) return
    sponsorDelta.textContent = String(claim.delta)
    sponsorOverlay.classList.add("visible")
    trackCard("impression")
}

function hideSponsor() {
    sponsorOverlay.classList.remove("visible")
}

/* The card stays until the user physically clicks CLOSE. Only then is the
   pending claim cleared from storage, so reopening the popup without
   closing the card shows it again. */
function dismissSponsor() {
    hideSponsor()
    trackCard("close")
    chrome.storage.local.remove("last_claim")
}

sponsorClose.addEventListener("click", dismissSponsor)

sponsorAdCta.addEventListener("click", function () {
    trackCard("click")
    chrome.storage.local.get("last_claim").then(function () {
        fetch(API_BASE + "/config")
            .then(function (res) { return res.ok ? res.json() : null })
            .then(function (cfg) {
                const url = (cfg && cfg.card_config && cfg.card_config.ad_url) || API_BASE
                chrome.tabs.create({ url: url })
            })
            .catch(function () { chrome.tabs.create({ url: API_BASE }) })
    })
})

document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setMenuOpen(false)
})

function applyStateFromResponse(resp, resetStatus) {
    document.querySelectorAll(".circle-btn").forEach(b => b.classList.remove("selected"))
    if (resp.opt) {
        const btn = document.querySelector(`.circle-btn[data-option="${resp.opt}"]`)
        if (btn) btn.classList.add("selected")
    }

    if (resp.mode) {
        const modeName = resp.mode === "premium_click" ? "fast" : "normal"
        document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"))
        const modeBtn = document.querySelector(`.mode-btn[data-mode="${modeName}"]`)
        if (modeBtn) modeBtn.classList.add("active")
        currentMode = modeName
        chrome.storage.local.set({ selected_mode: currentMode })
    }

    if (resetStatus) {
        status.textContent = "ACTIVE"
    } else if (resp.clickPending) {
        status.textContent = "CLICK PENDING..."
    } else {
        status.textContent = resp.stat === "DISABLED" ? "ACTIVE" : (resp.stat || "ACTIVE")
    }
}

document.addEventListener("DOMContentLoaded", async function () {
    await loadSponsorCardSetting()
    const stored = await chrome.storage.local.get(["device_id", "extension_enabled", "selected_mode", THEME_KEY, "last_claim"])

    const manifestVersion = chrome.runtime.getManifest().version
    document.getElementById("menuVersion").textContent = "AutoMCQ v" + manifestVersion

    const savedTheme = stored[THEME_KEY]
    applyTheme(savedTheme || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"))

    if (stored.last_claim) {
        showSponsor(stored.last_claim)
    }

    if (stored.device_id) {
        deviceId = stored.device_id
    } else {
        deviceId = crypto.randomUUID()
        await chrome.storage.local.set({ device_id: deviceId })
    }

    extensionEnabled = stored.extension_enabled !== false
    applyDisabledState(!extensionEnabled)

    if (stored.selected_mode && ["normal", "fast"].includes(stored.selected_mode)) {
        currentMode = stored.selected_mode
        const modeBtn = document.querySelector(`.mode-btn[data-mode="${currentMode}"]`)
        if (modeBtn) {
            document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"))
            modeBtn.classList.add("active")
        }
    }

    if (extensionEnabled) {
        await linkAndFetchBalance()

        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
            const resp = await chrome.tabs.sendMessage(tab.id, { action: "get-state" })
            applyStateFromResponse(resp, false)
        } catch {
            // no content script available on this tab
        }
    } else {
        document.querySelectorAll(".circle-btn").forEach(b => b.classList.remove("selected"))
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
            await chrome.tabs.sendMessage(tab.id, { action: "disable" })
        } catch {
            // no content script available
        }
    }
})

document.addEventListener("click", async function (event) {
    const modeBtn = event.target.closest(".mode-btn")
    if (modeBtn) {
        document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"))
        modeBtn.classList.add("active")
        currentMode = modeBtn.dataset.mode
        chrome.storage.local.set({ selected_mode: currentMode })
        return
    }

    const btn = event.target.closest(".circle-btn")
    if (!btn) return

    document.querySelectorAll(".circle-btn").forEach(b => b.classList.remove("selected"))
    btn.classList.add("selected")

    const option = btn.dataset.option
    const clickType = getClickType()
    const cost = CLICK_COSTS[currentMode]

    if (creditsBalance === null) {
        status.textContent = "LOADING BALANCE..."
        btn.classList.remove("selected")
        setTimeout(() => { status.textContent = "ACTIVE" }, 2500)
        return
    }

    if (creditsBalance < cost) {
        btn.classList.remove("selected")
        showToast(`INSUFFICIENT CREDITS\nNEED: ${cost} | HAVE: ${creditsBalance}`)
        return
    }

    status.textContent = `CLICKING ${option} (${currentMode})...`

    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
        await chrome.tabs.sendMessage(tab.id, {
            action: "set-option",
            option: option,
            mode: clickType,
        })
    } catch {
        status.textContent = "INCORRECT TAB"
        btn.classList.remove("selected")
        setTimeout(() => { status.textContent = "ACTIVE" }, 2000)
    }
})

toggle.addEventListener("click", async function () {
    extensionEnabled = !extensionEnabled
    await chrome.storage.local.set({ extension_enabled: extensionEnabled })
    applyDisabledState(!extensionEnabled)

    try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
        if (extensionEnabled) {
            await linkAndFetchBalance()
            const resp = await chrome.tabs.sendMessage(tab.id, { action: "get-state" })
            applyStateFromResponse(resp, true)
        } else {
            document.querySelectorAll(".circle-btn").forEach(b => b.classList.remove("selected"))
            await chrome.tabs.sendMessage(tab.id, { action: "disable" })
        }
    } catch {
        // no content script available
    }
})

let clickStatusTimer = null

chrome.runtime.onMessage.addListener(function (message) {
    if (!message.clicked) return

    if (clickStatusTimer) clearTimeout(clickStatusTimer)
    status.textContent = "CLICKED!"

    const btn = document.querySelector(`.circle-btn[data-option="${message.option}"]`)
    if (btn) btn.classList.remove("selected")

    clickStatusTimer = setTimeout(() => {
        status.textContent = "ACTIVE"
        clickStatusTimer = null
    }, 2000)
})

chrome.storage.onChanged.addListener(function (changes, area) {
    if (area !== "local") return
    if (changes.credits_balance) {
        creditsBalance = changes.credits_balance.newValue
        balanceEl.textContent = creditsBalance
    }
    if (changes.last_claim && changes.last_claim.newValue) {
        showSponsor(changes.last_claim.newValue)
    }
})

async function linkAndFetchBalance() {
    try {
        const linkResp = await fetch(`${API_BASE}/link-device`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_id: deviceId }),
        })
        if (!linkResp.ok) {
            const text = await linkResp.text()
            throw new Error(`link-device ${linkResp.status}: ${text}`)
        }
        const linkData = await linkResp.json()
        creditsBalance = linkData.credits_balance
        balanceEl.textContent = creditsBalance
    } catch (e) {
        console.error("API error:", e)
        balanceEl.textContent = "?"
        creditsBalance = 0
        status.textContent = "API ERROR"
        setTimeout(() => { status.textContent = "ACTIVE" }, 3000)
    }
}
