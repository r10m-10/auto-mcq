// Watches the claim page for a successful sandbox credit claim and:
//   1. forwards it to the extension background so the popup can show the
//      sponsor card too, and
//   2. renders a full-screen sponsor card directly into the page.
//
// Why inject into the page instead of opening the popup? Browsers forbid a
// website from opening an extension popup, and popups close on any click
// outside them. Rendering the card in-page guarantees the sponsor creative
// is actually seen, and it stays until the user presses CLOSE.
//
// Content scripts share the page DOM, so the injected card uses the site's
// own CSS variables (--paper/--ink/--pen-red/...) and themes automatically.
//
// TODO(real-offerwall): mount the real offerwall / AdSense creative inside
// .automcq-promo once SDK accounts are approved.

const API_BASE = "https://automcq.reyaanshsharma.com"

window.addEventListener("message", function (event) {
    if (event.source !== window) return
    const data = event.data
    if (!data || data.type !== "automcq-claim") return

    /* Fetch the ad config once and apply every switch:
       - sponsor_card_enabled → passed to the background so the popup card
         is only stored/accumulated while cards are allowed. When cards are
         off, nothing is stored, so no stale claim can resurface later.
       - sponsor_overlay_enabled → skip the in-page overlay when off.
       On a config fetch failure everything stays on (fail-open) so a
       network blip never blocks a card the user should see. */
    fetchAdConfig().then(function (cfg) {
        const cardEnabled = cfg.sponsor_card_enabled !== false
        const overlayEnabled = cfg.sponsor_overlay_enabled !== false

        chrome.runtime.sendMessage({
            action: "claim",
            delta: data.delta,
            balance: data.balance,
            sponsorCardEnabled: cardEnabled,
        })

        if (overlayEnabled) {
            showSponsorCard(data.delta, cfg.overlay_config)
        } else {
            /* No overlay is going to render, so the page must not wait out
               its 4s fallback timer — tell it the (skipped) sponsor card is
               done so the "+N CREDITS EARNED" stamp plays immediately. */
            window.postMessage({ type: "automcq-sponsor-closed" }, "*")
        }
    })
})

function fetchAdConfig() {
    return fetch(API_BASE + "/config")
        .then(function (res) {
            if (!res.ok) return {}
            return res.json()
        })
        .catch(function () {
            return {}
        })
}

function esc(text) {
    const div = document.createElement("div")
    div.textContent = String(text)
    return div.innerHTML
}

/* Fire-and-forget ad metric. Fail-open: never let a tracking blip block
   the sponsor card itself. */
function track(slot, eventType) {
    try {
        chrome.storage.local.get("device_id").then(function (stored) {
            fetch(API_BASE + "/ads/event", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slot: slot,
                    event_type: eventType,
                    device_id: stored.device_id || null,
                }),
            }).catch(function () {})
        })
    } catch (e) {
        /* ignore */
    }
}

function showSponsorCard(delta, slotCfg) {
    if (document.getElementById("automcq-sponsor-overlay")) return

    /* House ad copy comes from the admin's overlay_config; defaults keep
       the original hardcoded creative as a fail-open fallback. */
    slotCfg = slotCfg || {}
    const name = slotCfg.ad_name || "VEDPREP CRASH COURSE"
    const sub = slotCfg.ad_sub || "JEE & NEET 2027 mock tests with instant solutions."
    const cta = slotCfg.ad_cta || "LEARN MORE"
    const url = slotCfg.ad_url || API_BASE

    const overlay = document.createElement("div")
    overlay.id = "automcq-sponsor-overlay"
    overlay.setAttribute("role", "dialog")
    overlay.setAttribute("aria-modal", "true")
    overlay.setAttribute("aria-label", "Credits added")
    overlay.style.cssText = [
        "position:fixed",
        "inset:0",
        "z-index:2147483647",
        "display:flex",
        "align-items:center",
        "justify-content:center",
        "padding:18px",
        "background:var(--paper, #ECEFF4)",
        "font-family:var(--font-mono, ui-monospace, monospace)",
        "color:var(--ink, #1E2128)",
    ].join(";")

    overlay.innerHTML =
        '<style>' +
        '#automcq-sponsor-overlay .automcq-sponsor-card{' +
        // EDIT-ME: sponsor card width (increase to make it bigger, e.g. width:min(820px,100%))
        // EDIT-ME: uniform card scale — increase to grow the WHOLE card (text, padding,
        // shadow) proportionally like a zoom, keeping the same shape. e.g. scale(1.15)
        'transform:scale(1);' +
        'width:min(560px,100%);' +
        // EDIT-ME: sponsor card max height (e.g. 'max-height:80vh;' or remove for auto)
        'max-height:calc(100vh - 36px);' +
        'overflow-y:auto;' +
        'background-color:var(--paper, #ECEFF4);' +
        'background-image:linear-gradient(to right, transparent 95%, var(--grid-line, rgba(30,33,40,0.025)) 95%),' +
        'repeating-linear-gradient(0deg, transparent, transparent 31px, var(--grid-line-weak, rgba(30,33,40,0.03)) 31px, var(--grid-line-weak, rgba(30,33,40,0.03)) 32px);' +
        'border:2px solid var(--ink, #1E2128);' +
        'border-radius:0;' +
        'box-shadow:8px 8px 0 var(--shadow-color, rgba(30,33,40,0.85));' +
        // EDIT-ME: sponsor card padding
        'padding:28px 22px 18px;' +
        'text-align:center;' +
        '}' +
        '.automcq-kicker{margin:0 0 6px;font-size:11px;letter-spacing:0.2em;color:var(--pencil, #6B7280);}' +
        // EDIT-ME: "+N" number size (increase for a bigger number, e.g. font-size:96px)
        '.automcq-amount{margin:0;font-size:72px;font-weight:700;line-height:1;color:var(--pen-red, #C1440E);}' +
        '.automcq-heading{margin:6px 0 0;font-size:15px;font-weight:700;letter-spacing:0.18em;color:var(--ink, #1E2128);}' +
        '.automcq-divider{border:none;border-top:2px solid var(--ink, #1E2128);margin:18px 0;}' +
        '.automcq-bylabel{margin:0 0 12px;font-size:10px;letter-spacing:0.22em;color:var(--pencil, #6B7280);}' +
        '.automcq-promo{position:relative;border:2px dashed var(--pen-red, #C1440E);border-radius:0;padding:20px 14px 14px;margin-bottom:16px;}' +
        '.automcq-promo-tag{position:absolute;top:-9px;left:8px;background:var(--paper, #ECEFF4);padding:0 6px;font-size:9px;font-weight:700;letter-spacing:0.2em;color:var(--pen-red, #C1440E);}' +
        '.automcq-promo-name{margin:0 0 4px;font-size:12px;font-weight:700;letter-spacing:0.08em;color:var(--ink, #1E2128);}' +
        '.automcq-promo-sub{margin:0 0 12px;font-family:var(--font-sans, system-ui, sans-serif);font-size:11px;line-height:1.5;color:var(--pencil, #6B7280);}' +
        '.automcq-promo-cta{display:inline-block;border:2px solid var(--pen-red, #C1440E);border-radius:0;background:var(--pen-red, #C1440E);color:#fff;text-decoration:none;font-size:10px;font-weight:700;letter-spacing:0.14em;padding:8px 16px;}' +
        '.automcq-close{display:block;width:100%;padding:12px 0;font-family:var(--font-mono, ui-monospace, monospace);font-weight:700;letter-spacing:0.16em;font-size:12px;border:2px solid var(--ink, #1E2128);border-radius:0;cursor:pointer;background:transparent;color:var(--ink, #1E2128);}' +
        '.automcq-close:hover{background:var(--ink, #1E2128);color:var(--paper, #ECEFF4);}' +
        '</style>' +
        '<div class="automcq-sponsor-card">' +
        '<p class="automcq-kicker">CLAIM COMPLETE</p>' +
        '<p class="automcq-amount">+' + delta + '</p>' +
        '<p class="automcq-heading">CREDITS ADDED!</p>' +
        '<hr class="automcq-divider">' +
        '<p class="automcq-bylabel">SPONSORED BY</p>' +
        '<div class="automcq-promo">' +
        '<span class="automcq-promo-tag">AD</span>' +
        '<p class="automcq-promo-name">' + esc(name) + '</p>' +
        '<p class="automcq-promo-sub">' + esc(sub) + '</p>' +
        '<a class="automcq-promo-cta" href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(cta) + '</a>' +
        '</div>' +
        '<button class="automcq-close" type="button">CLOSE</button>' +
        '</div>'

    document.documentElement.appendChild(overlay)

    track("overlay", "impression")

    overlay.querySelector(".automcq-promo-cta").addEventListener("click", function () {
        track("overlay", "click")
    })

    overlay.querySelector(".automcq-close").addEventListener("click", function () {
        overlay.remove()
        track("overlay", "close")
        /* Tell the page the sponsor card is dismissed so it can play the
           "+N CREDITS EARNED" stamp animation now that the ad is gone. */
        window.postMessage({ type: "automcq-sponsor-closed" }, "*")
    })
}
