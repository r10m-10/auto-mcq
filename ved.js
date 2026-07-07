let selection = null
let stat = "ACTIVE"

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.action == "get-state"){
        sendResponse({opt: selection, stat: stat})
    }
    else if (message.action == "set-option"){
        selection = message.option
        stat = `CLICKING ${selection}...`
    }
})

async function checkForQuiz() {
    console.log("Checking for quiz...")
    const selectedElement = document.querySelector(`[data-option="${selection}"]`)
    if (selectedElement) {
        selectedElement.click()
        selection = null
        chrome.runtime.sendMessage({option: selection, clicked: true})
    }
}

const observer = new MutationObserver(checkForQuiz)

document.addEventListener("DOMContentLoaded", function () {
    observer.observe(document.body, {
        childList: true,
        subtree: true
    })
})