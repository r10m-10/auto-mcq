const API_BASE = "https://automcq.reyaanshsharma.com"

chrome.runtime.onMessage.addListener(async function (message, sender, sendResponse) {
    if (message.action === "claim") {
        // Accumulate into any pending claim so multiple ads (e.g. two +3
        // claims = +6) show as one total until the popup card is closed.
        // dismissSponsor() clears last_claim, so the next claim starts fresh.
        const stored = await chrome.storage.local.get("last_claim")
        const prev = stored.last_claim
        await chrome.storage.local.set({
            last_claim: {
                delta: (prev ? prev.delta : 0) + message.delta,
                balance: message.balance,
                ts: Date.now(),
            },
        })
        return
    }
    if (message.clicked) {
        await consumeCredits(message.mode || "normal_click")
    }
})

async function consumeCredits(clickType) {
    try {
        const { device_id } = await chrome.storage.local.get("device_id")
        if (!device_id) return

        const resp = await fetch(`${API_BASE}/consume-click`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ device_id, click_type: clickType }),
        })
        if (resp.ok) {
            const data = await resp.json()
            await chrome.storage.local.set({ credits_balance: data.credits_balance })
        } else if (resp.status === 402) {
            const data = await resp.json()
            console.error("Credit sync:", data.detail)
        }
    } catch (e) {
        console.error("Background consume credits error:", e)
    }
}
