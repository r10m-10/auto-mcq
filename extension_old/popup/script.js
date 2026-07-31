const API_BASE = "https://automcq.reyaanshsharma.com"
const CLICK_COSTS = { normal: 1, fast: 4 }

const status = document.querySelector(".cur-status")
const balanceEl = document.querySelector(".credits-balance")
const popupContent = document.getElementById("popupContent")
const toggle = document.getElementById("extensionToggle")
const toastOverlay = document.getElementById("toastOverlay")
const toastMessage = document.getElementById("toastMessage")
const toastClose = document.getElementById("toastClose")

let deviceId = null
let creditsBalance = null
let currentMode = "normal"
let extensionEnabled = true

function getClickType() {
    return currentMode === "fast" ? "premium_click" : "normal_click"
}

function applyDisabledState(disabled) {
    popupContent.classList.toggle("disabled", disabled)
    status.textContent = disabled ? "DISABLED" : "ACTIVE"
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
    const stored = await chrome.storage.local.get(["device_id", "extension_enabled", "selected_mode"])
    if (stored.device_id) {
        deviceId = stored.device_id
    } else {
        deviceId = crypto.randomUUID()
        await chrome.storage.local.set({ device_id: deviceId })
    }

    extensionEnabled = stored.extension_enabled !== false
    toggle.checked = extensionEnabled
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
        status.textContent = "Loading balance..."
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
        status.textContent = "No tab to send to"
        btn.classList.remove("selected")
        setTimeout(() => { status.textContent = "ACTIVE" }, 2000)
    }
})

toggle.addEventListener("change", async function () {
    extensionEnabled = toggle.checked
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
    if (area === "local" && changes.credits_balance) {
        creditsBalance = changes.credits_balance.newValue
        balanceEl.textContent = creditsBalance
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
