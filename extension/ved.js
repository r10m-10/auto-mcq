let selection = null
let mode = null
let stat = "ACTIVE"
let clickPending = false
let clickTimer = null

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action == "get-state"){
        sendResponse({opt: selection, stat: stat})
    }
    else if (message.action == "set-option"){
        if (clickTimer) {
            clearTimeout(clickTimer)
            clickTimer = null
        }
        clickPending = false
        selection = message.option
        mode = message.mode
        stat = `CLICKING ${selection}...`
    }
    else if (message.action == "disable"){
        if (clickTimer) {
            clearTimeout(clickTimer)
            clickTimer = null
        }
        clickPending = false
        selection = null
        mode = null
        stat = "DISABLED"
    }
})

async function checkForQuiz() {
    if (clickPending || !selection) return

    const selectedElement = document.querySelector(`[data-option="${selection}"]`)
    if (!selectedElement) return

    const capturedOption = selection
    const capturedMode = mode
    clickPending = true
    selection = null
    mode = null
    stat = "ACTIVE"

    function doClick() {
        selectedElement.click()
        clickPending = false
        chrome.runtime.sendMessage({option: capturedOption, clicked: true, mode: capturedMode})
    }

    if (capturedMode === "normal_click") {
        clickTimer = setTimeout(doClick, 5000)
    } else {
        doClick()
    }
}

const observer = new MutationObserver(checkForQuiz)

document.addEventListener("DOMContentLoaded", function () {
    observer.observe(document.body, {
        childList: true,
        subtree: true
    })
})
