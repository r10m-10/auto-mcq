// Forwards a successful sandbox credit claim from the website to the
// extension. The claim page posts a window message after claimReward()
// succeeds; we relay it so the popup can show the sponsor card.
window.addEventListener("message", function (event) {
    if (event.source !== window) return
    const data = event.data
    if (!data || data.type !== "automcq-claim") return

    chrome.runtime.sendMessage({
        action: "claim",
        delta: data.delta,
        balance: data.balance,
    })
})
