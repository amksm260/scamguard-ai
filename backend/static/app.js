/* Kavach AI - frontend logic.
   Vanilla JS on purpose: one service to deploy, no build step, and every
   line here is something a beginner can read and change directly. */

let currentMode = "message";
let currentLang = "en";
let lastResult = null;   // last API payload, so language toggle can re-render without a new request
let speaking = false;

// Minimal built-in fallback so the UI still works if /api/i18n fails.
let i18n = {
  app_name: "Kavach AI", tagline: "Before you click, pay, or share - check it here.",
  tab_message: "Check a Message", tab_screenshot: "Check a Screenshot",
  tab_url: "Check a Link", tab_qr: "Check a QR Code", tab_call: "Check a Call",
  placeholder_message: "Paste the message you received here...",
  placeholder_url: "Paste the website link here...",
  placeholder_call: "Type or paste what the caller said...",
  upload_hint: "Tap to upload a photo or screenshot", button_check: "Check This Now",
  result_low: "LOW RISK", result_review: "REVIEW", result_high: "HIGH RISK",
  why_heading: "Why?", action_heading: "What should I do?",
  no_signals: "No specific warning signs were detected in the text provided.",
  read_aloud: "Read Aloud", stop_reading: "Stop", ask_trusted: "Ask a Trusted Person",
  trusted_intro: "Kavach AI checked something for me. Result:",
  footer_note: "Kavach AI gives guidance based on available evidence. It is not a guarantee. When unsure, always verify through an official source.",
  detected_text: "Text we analysed", no_qr_found: "We couldn't find a QR code in that image. Try a clearer photo.",
  upi_detected: "This QR code is a UPI payment request.", upi_payee: "Paying to", upi_amount: "Amount",
};

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (i18n[key]) el.textContent = i18n[key];
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (i18n[key]) el.setAttribute("placeholder", i18n[key]);
  });
}

async function setLang(lang) {
  currentLang = lang;
  document.getElementById("lang-en").classList.toggle("active", lang === "en");
  document.getElementById("lang-hi").classList.toggle("active", lang === "hi");
  try {
    const res = await fetch(`/api/i18n/${lang}`);
    if (res.ok) {
      i18n = await res.json();
      applyI18n();
    }
  } catch (e) { /* keep existing i18n on failure */ }
  if (lastResult) renderResult(lastResult); // re-render in new language, no new API call
}

document.querySelectorAll(".mode-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
    ["message", "screenshot", "url", "qr", "call"].forEach(m => {
      document.getElementById(`panel-${m}`).classList.toggle("hidden", m !== currentMode);
    });
    document.getElementById("result-region").innerHTML = "";
    lastResult = null;
  });
});

function wirePreview(fileInputId, previewId) {
  const input = document.getElementById(fileInputId);
  const preview = document.getElementById(previewId);
  input.addEventListener("change", () => {
    const file = input.files[0];
    if (!file) { preview.classList.add("hidden"); return; }
    const reader = new FileReader();
    reader.onload = e => {
      preview.src = e.target.result;
      preview.classList.remove("hidden");
    };
    reader.readAsDataURL(file);
  });
}
wirePreview("file-screenshot", "preview-screenshot");
wirePreview("file-qr", "preview-qr");

function setLoading(isLoading) {
  const btn = document.getElementById("check-btn");
  btn.disabled = isLoading;
  btn.innerHTML = isLoading
    ? `<span class="spinner"></span>${i18n.button_check}`
    : i18n.button_check;
}

async function runCheck() {
  const region = document.getElementById("result-region");
  region.innerHTML = "";
  setLoading(true);

  try {
    let res, data;

    if (currentMode === "message") {
      const text = document.getElementById("input-message").value.trim();
      if (!text) { setLoading(false); return; }
      res = await fetch("/api/analyze/text", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

    } else if (currentMode === "call") {
      const transcript = document.getElementById("input-call").value.trim();
      if (!transcript) { setLoading(false); return; }
      res = await fetch("/api/analyze/call", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript }),
      });

    } else if (currentMode === "url") {
      const url = document.getElementById("input-url").value.trim();
      if (!url) { setLoading(false); return; }
      res = await fetch("/api/analyze/url", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

    } else if (currentMode === "screenshot") {
      const file = document.getElementById("file-screenshot").files[0];
      if (!file) { setLoading(false); return; }
      const form = new FormData();
      form.append("file", file);
      res = await fetch("/api/analyze/screenshot", { method: "POST", body: form });

    } else if (currentMode === "qr") {
      const file = document.getElementById("file-qr").files[0];
      if (!file) { setLoading(false); return; }
      const form = new FormData();
      form.append("file", file);
      res = await fetch("/api/analyze/qr", { method: "POST", body: form });
    }

    if (!res.ok) throw new Error("Server error");
    data = await res.json();
    lastResult = data;
    renderResult(data);

  } catch (err) {
    region.innerHTML = `<p class="error-text">Something went wrong. Please try again.</p>`;
  } finally {
    setLoading(false);
  }
}

function riskLabel(level) {
  if (level === "HIGH") return i18n.result_high;
  if (level === "REVIEW") return i18n.result_review;
  return i18n.result_low;
}

function riskIcon(level) {
  if (level === "HIGH") return "⛔";
  if (level === "REVIEW") return "⚠️";
  return "✅";
}

function renderResult(data) {
  const region = document.getElementById("result-region");

  if (data.no_qr_found) {
    region.innerHTML = `<div class="result REVIEW"><p class="action-text">${i18n.no_qr_found}</p></div>`;
    return;
  }

  const level = data.risk_level || "REVIEW";
  const why = (data.signals || []).map(s => currentLang === "hi" ? s.why_hi : s.why_en);
  const action = currentLang === "hi" ? data.action_hi : data.action_en;

  let html = `<div class="result ${level}">`;
  html += `<span class="badge">${riskIcon(level)} ${riskLabel(level)}</span>`;

  if (data.upi) {
    html += `<p><strong>${i18n.upi_detected}</strong></p>`;
    if (data.upi.payee_name || data.upi.payee_vpa) {
      html += `<p>${i18n.upi_payee}: ${escapeHtml(data.upi.payee_name || data.upi.payee_vpa)}</p>`;
    }
    if (data.upi.amount) html += `<p>${i18n.upi_amount}: ₹${escapeHtml(data.upi.amount)}</p>`;
  }

  html += `<h3>${i18n.why_heading}</h3>`;
  if (why.length) {
    html += "<ul>" + why.map(w => `<li>${escapeHtml(w)}</li>`).join("") + "</ul>";
  } else {
    html += `<p>${i18n.no_signals}</p>`;
  }

  html += `<h3>${i18n.action_heading}</h3>`;
  html += `<p class="action-text">${escapeHtml(action || "")}</p>`;

  if (data.analysed_text) {
    html += `<div class="detected-text-box"><strong>${i18n.detected_text}:</strong><br>${escapeHtml(data.analysed_text)}</div>`;
  }
  if (data.url) {
    html += `<div class="detected-text-box"><strong>${i18n.detected_text}:</strong><br>${escapeHtml(data.url)}</div>`;
  }

  html += `<div class="result-actions">`;
  html += `<button class="pill-btn" onclick="toggleReadAloud()">🔊 <span id="read-aloud-label">${i18n.read_aloud}</span></button>`;
  html += `<button class="pill-btn" onclick="askTrustedPerson()">🤝 ${i18n.ask_trusted}</button>`;
  html += `</div>`;

  html += `</div>`;
  region.innerHTML = html;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function summaryForShareOrSpeech() {
  if (!lastResult) return "";
  const level = riskLabel(lastResult.risk_level || "REVIEW");
  const why = (lastResult.signals || [])
    .map(s => currentLang === "hi" ? s.why_hi : s.why_en);
  const action = currentLang === "hi" ? lastResult.action_hi : lastResult.action_en;
  const parts = [level, ...why, action].filter(Boolean);
  return parts.join(". ");
}

function toggleReadAloud() {
  const label = document.getElementById("read-aloud-label");
  if (speaking) {
    window.speechSynthesis.cancel();
    speaking = false;
    if (label) label.textContent = i18n.read_aloud;
    return;
  }
  const text = summaryForShareOrSpeech();
  if (!text || !("speechSynthesis" in window)) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = currentLang === "hi" ? "hi-IN" : "en-IN";
  utter.onend = () => { speaking = false; if (label) label.textContent = i18n.read_aloud; };
  speaking = true;
  if (label) label.textContent = i18n.stop_reading;
  window.speechSynthesis.speak(utter);
}

function askTrustedPerson() {
  const summary = `${i18n.trusted_intro}\n\n${summaryForShareOrSpeech()}`;
  if (navigator.share) {
    navigator.share({ title: i18n.app_name, text: summary }).catch(() => {});
  } else {
    const url = `https://wa.me/?text=${encodeURIComponent(summary)}`;
    window.open(url, "_blank");
  }
}

// Init
applyI18n();
