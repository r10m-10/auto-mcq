const status = document.querySelector(".cur-status")

document.addEventListener("DOMContentLoaded", async function () {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true })
    chrome.tabs.sendMessage(tabs[0].id, { action: "get-state" })
    const response = await chrome.tabs.sendMessage(tabs[0].id, { action: "get-state" })
    const btn = document.querySelector(`.circle-btn[data-option="${response.opt}"]`)
    btn.classList.add("selected")
    console.log(response.stat)
    status.textContent = response.stat

})

document.addEventListener('click', async function (event) {
    const button = event.target.closest(".circle-btn")
    if (!button) {
        return
    }
    document.querySelectorAll(".circle-btn").forEach(btn => {
        btn.classList.remove("selected")
    })
    button.classList.add("selected")
    curStat = 
    status.textContent = `CLICKING ${button.dataset.option}...`
    const selectedOption = { action: "set-option", "option": button.dataset.option }
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true })
    chrome.tabs.sendMessage(tabs[0].id, selectedOption)
})

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    const clicked = message.clicked
    const opt = message.option
    if (clicked) {
        const btn = document.querySelector(`.circle-btn[data-option="${opt}"]`)
        btn.classList.remove("selected")
        status.textContent = "CLICKED!"
        setTimeout(() => {
        }, 5000)
        status.textContent = "ACTIVE"
    }
})