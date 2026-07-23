const API_BASE = "https://automcq.reyaanshsharma.com"
const CLICK_COSTS = { normal: 1, fast: 4 }

const status = document.querySelector(".cur-status")
const balanceEl = document.querySelector(".credits-balance")
const popupContent = document.getElementById("popupContent")
const toggle = document.getElementById("extensionToggle")

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

document.addEventListener("DOMContentLoaded", async function () {
    const stored = await chrome.storage.local.get(["device_id", "extension_enabled"])
    if (stored.device_id) {
        deviceId = stored.device_id
    } else {
        deviceId = crypto.randomUUID()
        await chrome.storage.local.set({ device_id: deviceId })
    }

    extensionEnabled = stored.extension_enabled !== false
    toggle.checked = extensionEnabled
    applyDisabledState(!extensionEnabled)

    if (extensionEnabled) {
        await linkAndFetchBalance()

        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
            const resp = await chrome.tabs.sendMessage(tab.id, { action: "get-state" })
            if (resp.opt) {
                const btn = document.querySelector(`.circle-btn[data-option="${resp.opt}"]`)
                if (btn) btn.classList.add("selected")
            }
            status.textContent = resp.stat
        } catch {
            // no content script available on this tab
        }
    }
})

document.addEventListener("click", async function (event) {
    const modeBtn = event.target.closest(".mode-btn")
    if (modeBtn) {
        document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"))
        modeBtn.classList.add("active")
        currentMode = modeBtn.dataset.mode
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
        status.textContent = `Not enough credits for ${currentMode} mode (need ${cost}, have ${creditsBalance})`
        btn.classList.remove("selected")
        setTimeout(() => { status.textContent = "ACTIVE" }, 3000)
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
            const resp = await chrome.tabs.sendMessage(tab.id, { action: "get-state" })
            if (resp.opt) {
                const btn = document.querySelector(`.circle-btn[data-option="${resp.opt}"]`)
                if (btn) btn.classList.add("selected")
            }
            status.textContent = resp.stat
        } else {
            await chrome.tabs.sendMessage(tab.id, { action: "disable" })
        }
    } catch {
        // no content script available
    }
})

chrome.runtime.onMessage.addListener(function (message) {
    if (!message.clicked) return

    status.textContent = "CLICKED!"

    const btn = document.querySelector(`.circle-btn[data-option="${message.option}"]`)
    if (btn) btn.classList.remove("selected")

    const clickType = message.mode || "normal_click"
    consumeCredits(clickType)

    setTimeout(() => {
        status.textContent = "ACTIVE"
    }, 2000)
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
        status.textContent = "API ERROR"
        setTimeout(() => { status.textContent = "ACTIVE" }, 3000)
    }
}

async function consumeCredits(clickType) {
    try {
        const resp = await fetch(`${API_BASE}/consume-click`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_id: deviceId, click_type: clickType }),
        })
        if (resp.ok) {
            const data = await resp.json()
            creditsBalance = data.credits_balance
            balanceEl.textContent = creditsBalance
        } else if (resp.status === 402) {
            const data = await resp.json()
            console.error("Credit sync:", data.detail)
            balanceEl.textContent = `${creditsBalance}?`
        } else {
            console.error("consume-click failed:", resp.status)
        }
    } catch (e) {
        console.error("Network error consuming credits:", e)
    }
}
