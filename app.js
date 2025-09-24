// app.js
const BACKEND_URL = "https://inf2005-acw1-521929210751.asia-east1.run.app"; // no trailing slash

// =============== ENCODE ===============
const form = document.getElementById("encodeForm");
if (!form) {
  console.debug("encodeForm not found; app.js loaded on a non-encode page.");
} else {
  const statusEl      = document.getElementById("status");
  const resultSection = document.getElementById("resultSection");
  const resultMsg     = document.getElementById("resultMessage");
  const previewRow    = document.getElementById("previewRow");
  const coverImg      = document.getElementById("coverImg");
  const encodedImg    = document.getElementById("encodedImg");
  const diffImg       = document.getElementById("diffImg");
  const downloadBtn   = document.getElementById("downloadEncoded");

  // --- File/Text toggle elements (must match your HTML ids) ---
  const rowPayloadFile   = document.getElementById("rowPayloadFile"); // container row for file input
  const rowPayloadText   = document.getElementById("rowPayloadText"); // container row for text input
  const payloadSrcRadios = document.querySelectorAll('input[name="payload_src"]');
  const payloadFileInput = document.getElementById("payloadInput");   // <input type="file" name="payload" id="payloadInput">
  const payloadTextArea  = document.getElementById("payloadText");    // <textarea name="payload_text" id="payloadText">

  // --- Capacity elements ---
  const coverInput   = document.querySelector('input[name="cover"]');
  const lsbSelect    = document.querySelector('select[name="lsb"]');
  const capacityHint = document.getElementById("capacityHint");

  // --- Anchor selection elements ---
  const rowUseAnchor     = document.getElementById("rowUseAnchor");
  const rowAnchorMethod  = document.getElementById("rowAnchorMethod");
  const rowAnchorTyping  = document.getElementById("rowAnchorTyping");
  const rowAnchorClick   = document.getElementById("rowAnchorClick");

  const anchorRadios     = document.querySelectorAll('input[name="use_anchor"]');
  const methodRadios     = document.querySelectorAll('input[name="anchor_method"]');
  const anchorXInput     = document.getElementById("anchorX");
  const anchorYInput     = document.getElementById("anchorY");
  const openPickerBtn    = document.getElementById("openAnchorPicker");
  const anchorPicked     = document.getElementById("anchorPicked");

  const anchorDialog     = document.getElementById("anchorDialog"); // <dialog>
  const anchorImg        = document.getElementById("anchorImage");  // <img> inside dialog
  const anchorCloseBtn   = document.getElementById("closeAnchorDialog");

  // ---------- Helpers ----------
  function fmtBits(n) { return n.toLocaleString('en-US') + " bits"; }
  function fmtBytesApprox(bits) {
    const bytes = Math.floor(bits / 8);
    const kib = bytes / 1024, mib = kib / 1024;
    if (mib >= 1) return `${bytes.toLocaleString('en-US')} bytes (~${mib.toFixed(2)} MiB)`;
    if (kib >= 1) return `${bytes.toLocaleString('en-US')} bytes (~${kib.toFixed(2)} KiB)`;
    return `${bytes.toLocaleString('en-US')} bytes`;
  }
  function currentPayloadMode() {
    const r = Array.from(payloadSrcRadios || []).find(x => x.checked);
    return r ? r.value : "file"; // default
  }
  function isImageFile(file) {
    return file && /^image\//i.test(file.type);
  }

  // ---------- File/Text toggle ----------
  function applyPayloadModeUI() {
    const mode = currentPayloadMode();
    if (rowPayloadFile) rowPayloadFile.classList.toggle("hidden", mode !== "file");
    if (rowPayloadText) rowPayloadText.classList.toggle("hidden", mode !== "text");
    updateCapacityHint(); // recalc whenever the mode changes
  }

  // ---------- Capacity Hint ----------
  // Need bits calculator (works for both file & text)
  function computeNeedBits() {
    // header = 16 (boot) + 26 (fixed main) + nameLen (≤255)
    if (currentPayloadMode() === "file") {
      const f = payloadFileInput?.files?.[0];
      if (!f) return null;
      const nameLen = (f.name || "").length;
      const overheadBytes = 16 + 26 + Math.min(nameLen, 255);
      return (overheadBytes + f.size) * 8;
    } else {
      const text = payloadTextArea?.value ?? "";
      const encoder = new TextEncoder();
      const textBytes = encoder.encode(text).length;
      const overheadBytes = 16 + 26 + 0; // no filename for text payload
      return (overheadBytes + textBytes) * 8;
    }
  }

  function updateCapacityHint() {
    if (!capacityHint) return;

    const coverFile = coverInput?.files?.[0];
    const lsb = parseInt(lsbSelect?.value || "1", 10);
    if (!coverFile || !lsb || isNaN(lsb)) {
      capacityHint.textContent = "";
      return;
    }

    const url = URL.createObjectURL(coverFile);
    const img = new Image();
    img.onload = () => {
      const W = img.naturalWidth, H = img.naturalHeight;
      const channels = 3; // RGB
      const capacityBits = W * H * channels * lsb;

      // Always show base capacity
      let line = `Cover capacity (Image, ${W}×${H}, ${channels} channels, ${lsb} LSB): `
               + `${fmtBits(capacityBits)} (${fmtBytesApprox(capacityBits)})`;

      // If we already have payload (file selected or text typed), append fit/need note
      const needBits = computeNeedBits();
      if (needBits !== null) {
        if (needBits > capacityBits) {
          line += `\n(Payload too large: need ${fmtBits(needBits)}.)`;
        } else {
          line += `\n(Payload fits: needs ${fmtBits(needBits)}.)`;
        }
      }

      capacityHint.textContent = line;
      URL.revokeObjectURL(url);
    };
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  }

  // ---------- Anchor visibility logic ----------
  function refreshAnchorVisibility() {
    const coverFile = coverInput?.files?.[0];
    const coverIsImage = isImageFile(coverFile);

    rowUseAnchor?.classList.toggle("hidden", !coverIsImage);

    const useAnchor =
      (document.querySelector('input[name="use_anchor"]:checked')?.value === "yes");
    rowAnchorMethod?.classList.toggle("hidden", !(coverIsImage && useAnchor));

    const methodEl = document.querySelector('input[name="anchor_method"]:checked');
    const method = (methodEl ? methodEl.value : "type");
    rowAnchorTyping?.classList.toggle("hidden", !(coverIsImage && useAnchor && method === "type"));
    rowAnchorClick?.classList.toggle("hidden",  !(coverIsImage && useAnchor && method === "click"));
  }

  coverInput?.addEventListener("change", () => {
    refreshAnchorVisibility();
    // also prep the dialog image source so it matches the chosen cover
    const f = coverInput.files?.[0];
    if (isImageFile(f)) {
      const url = URL.createObjectURL(f);
      anchorImg.src = url; // used when dialog opens
      anchorImg.onload = () => URL.revokeObjectURL(url);
    } else {
      anchorImg.removeAttribute("src");
    }
    updateCapacityHint(); // show capacity immediately after choosing cover
  });

  anchorRadios.forEach(r => r.addEventListener("change", refreshAnchorVisibility));
  methodRadios.forEach(r => r.addEventListener("change", refreshAnchorVisibility));

  // ---------- Anchor picker dialog ----------
  openPickerBtn?.addEventListener("click", () => {
    if (!anchorImg.src) {
      const f = coverInput?.files?.[0];
      if (!isImageFile(f)) {
        alert("Please choose an image cover first.");
        return;
      }
    }
    if (typeof anchorDialog.showModal === "function") {
      anchorDialog.showModal();
    } else {
      anchorDialog.setAttribute("open", "");
    }
  });

  anchorCloseBtn?.addEventListener("click", () => {
    anchorDialog.close?.();
    anchorDialog.removeAttribute("open");
  });

  // Pick (x,y) with a click inside the dialog image
  anchorImg?.addEventListener("click", (e) => {
    const rect = anchorImg.getBoundingClientRect();
    const scaleX = anchorImg.naturalWidth  / anchorImg.clientWidth;
    const scaleY = anchorImg.naturalHeight / anchorImg.clientHeight;
    const x = Math.floor((e.clientX - rect.left) * scaleX);
    const y = Math.floor((e.clientY - rect.top)  * scaleY);

    if (Number.isFinite(x) && Number.isFinite(y) && x >= 0 && y >= 0) {
      if (anchorXInput) anchorXInput.value = String(x);
      if (anchorYInput) anchorYInput.value = String(y);
      if (anchorPicked) anchorPicked.textContent = `Selected: (${x}, ${y})`;
    }
    anchorDialog.close?.();
    anchorDialog.removeAttribute("open");
  });

  // ---------- Wire capacity listeners & initial UI ----------
  lsbSelect?.addEventListener("change", updateCapacityHint);
  payloadFileInput?.addEventListener("change", updateCapacityHint);
  payloadTextArea?.addEventListener("input", updateCapacityHint);
  payloadSrcRadios.forEach(r => r.addEventListener("change", () => {
    applyPayloadModeUI();
    refreshAnchorVisibility();
  }));

  // Kick once on load (for back/forward navigation, etc.)
  applyPayloadModeUI();
  refreshAnchorVisibility();
  updateCapacityHint();

  // ---------- Encode UI feedback ----------
  function showError(msg) {
    if (resultMsg) {
      resultMsg.textContent = msg;
      resultMsg.classList.add("error");
    }
    previewRow?.classList.add("hidden");
    downloadBtn?.classList.add("hidden");
    resultSection?.classList.remove("hidden");
    if (statusEl) statusEl.textContent = "";
    resultSection?.scrollIntoView({ behavior: "smooth" });
  }

  function showSuccess(data) {
    if (resultMsg) {
      resultMsg.textContent = "";
      resultMsg.classList.remove("error");
    }
    previewRow?.classList.remove("hidden");
    downloadBtn?.classList.remove("hidden");

    // small previews for cover & diff
    if (coverImg)   coverImg.src   = data.cover_preview || "";
    if (diffImg)    diffImg.src    = data.diff_preview  || "";

    // full encoded PNG for center image & download
    if (encodedImg) encodedImg.src = data.encoded || "";
    if (downloadBtn) {
      downloadBtn.href = data.encoded || "#";
      downloadBtn.download = data.download_name || "encoded.png";
    }

    resultSection?.classList.remove("hidden");
    if (statusEl) statusEl.textContent = "";
    resultSection?.scrollIntoView({ behavior: "smooth" });
  }

  // ---------- Submit (handles file or text payload + optional anchor) ----------
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (statusEl) statusEl.textContent = "Encoding... (Process will take longer for larger file)";

    const fd = new FormData(form);

    // Payload: ensure only the selected type is sent
    const mode = currentPayloadMode();
    if (mode === "text") {
      fd.delete("payload"); // remove accidental file
      const textVal = payloadTextArea?.value ?? "";
      fd.set("payload_text", textVal);
    } else {
      fd.delete("payload_text");
    }

    // Anchor: send as separate fields (no longer part of key)
    const useAnchor = document.querySelector('input[name="use_anchor"]:checked')?.value === "yes";
    const methodEl = document.querySelector('input[name="anchor_method"]:checked');
    const method = (methodEl ? methodEl.value : "type");

    fd.set("use_anchor", useAnchor ? "yes" : "no");
    if (useAnchor) {
      const ax = (anchorXInput?.value || "").trim();
      const ay = (anchorYInput?.value || "").trim();
      if (ax !== "" && ay !== "") {
        fd.set("anchor_x", ax);
        fd.set("anchor_y", ay);
      } else if (method === "type") {
        alert("Please provide both x and y for the anchor, or switch to Mouse-click.");
        if (statusEl) statusEl.textContent = "";
        return;
      }
    } else {
      fd.delete("anchor_x");
      fd.delete("anchor_y");
    }

    try {
      const res = await fetch(`${BACKEND_URL}/api/encode`, { method: "POST", body: fd });
      const raw = await res.text();
      let json = null; try { json = JSON.parse(raw); } catch {}
      if (!res.ok) {
        const msg = (json && json.error) ? json.error : `HTTP ${res.status}`;
        showError(msg);
        return;
      }
      showSuccess(json);
    } catch (err) {
      showError(err.message || "Network error");
    }
  });
}

// =============== DECODE ===============
(() => {
  const decForm = document.getElementById("decodeForm");
  if (!decForm) return; // run this section only on the decode page

  const decStatus     = document.getElementById("decStatus");
  const decResult     = document.getElementById("decResult");
  const decMeta       = document.getElementById("decMeta");
  const decPreviewRow = document.getElementById("decPreviewRow");
  const decEncodedImg = document.getElementById("decEncodedImg");
  const decDecodedImg = document.getElementById("decDecodedImg");   // image payloads
  const decDecodedText= document.getElementById("decDecodedText");  // text payloads (<pre> or similar)
  const decodedLabel  = document.getElementById("decodedLabel");
  const dlDecoded     = document.getElementById("downloadDecoded");
  const decClearBtn   = document.getElementById("decClear");

  function decError(msg) {
    if (decMeta) { decMeta.textContent = msg; decMeta.classList.add("error"); }
    decPreviewRow?.classList.add("hidden");
    dlDecoded?.classList.add("hidden");
    decResult?.classList.remove("hidden");
    if (decStatus) decStatus.textContent = "";
    decResult?.scrollIntoView({ behavior: "smooth" });
  }

  function decSuccess(data) {
    if (decMeta) {
      decMeta.textContent = data.meta_text || "";
      decMeta.classList.remove("error");
    }

    const isText = data.payload_type === "text" || (!!data.decoded_text && !data.decoded_preview);

    if (decodedLabel) decodedLabel.textContent = isText ? "Decoded TEXT payload" : "Decoded";

    if (decEncodedImg) decEncodedImg.src = data.encoded_preview || "";

    if (isText) {
      if (decDecodedImg) { decDecodedImg.classList.add("hidden"); decDecodedImg.removeAttribute("src"); }
      if (decDecodedText) { decDecodedText.classList.remove("hidden"); decDecodedText.textContent = data.decoded_text || "(empty)"; }
    } else {
      if (decDecodedText) { decDecodedText.classList.add("hidden"); decDecodedText.textContent = ""; }
      if (decDecodedImg) {
        if (data.decoded_preview) {
          decDecodedImg.classList.remove("hidden");
          decDecodedImg.src = data.decoded_preview;
        } else {
          decDecodedImg.classList.add("hidden");
          decDecodedImg.removeAttribute("src");
        }
      }
    }

    if (dlDecoded) {
      dlDecoded.classList.remove("hidden");
      dlDecoded.onclick = null;

      if (isText) {
        dlDecoded.textContent = "Download TXT File";
        dlDecoded.onclick = (e) => {
          e.preventDefault();
          const txt = data.decoded_text || "";
          let suggested =
            data.download_name ||
            (data.meta_name ? `decoded_${data.meta_name}` : "decoded_payload.txt");
          if (!/\.txt$/i.test(suggested)) {
            suggested = suggested.replace(/\.[^./\\]+$/, "") + ".txt";
          }
          const blob = new Blob([txt], { type: "text/plain;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = suggested;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 3000);
        };
      } else {
        dlDecoded.textContent = "Download Decoded File";
        dlDecoded.onclick = async (e) => {
          e.preventDefault();
          const fd = new FormData(decForm);
          try {
            const res = await fetch(`${BACKEND_URL}/api/decode/download`, {
              method: "POST",
              body: fd,
            });
            if (!res.ok) {
              let msg = `HTTP ${res.status}`;
              try { const j = await res.json(); if (j?.error) msg = j.error; } catch {}
              decError(msg);
              return;
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = data.download_name || "decoded_payload.bin";
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 3000);
          } catch (err) {
            decError(err.message || "Network error");
          }
        };
      }
    }

    decPreviewRow?.classList.remove("hidden");
    decResult?.classList.remove("hidden");
    if (decStatus) decStatus.textContent = "";
    decResult?.scrollIntoView({ behavior: "smooth" });
  }

  // submit
  decForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (decStatus) decStatus.textContent = "Decoding... (Process will take longer for larger file)";

    const fd = new FormData(decForm);
    try {
      const res = await fetch(`${BACKEND_URL}/api/decode`, { method: "POST", body: fd });
      const raw = await res.text();
      let json = null; try { json = JSON.parse(raw); } catch {}
      if (!res.ok) {
        const msg = (json && json.error) ? json.error : `HTTP ${res.status}`;
        decError(msg);
        return;
      }
      if (json?.download_name && dlDecoded) dlDecoded.setAttribute("data-fn", json.download_name);
      decSuccess(json);
    } catch (err) {
      decError(err.message || "Network error");
    }
  });

  // clear (same UX as encode page)
  function resetDecodingUI() {
    try { decForm.reset(); } catch {}
    if (decStatus) decStatus.textContent = "";
    if (decMeta) { decMeta.textContent = ""; decMeta.classList.remove("error"); }
    decPreviewRow?.classList.add("hidden");
    decResult?.classList.add("hidden");
    if (decEncodedImg) { decEncodedImg.src = ""; decEncodedImg.removeAttribute("src"); }
    if (decDecodedImg) { decDecodedImg.src = ""; decDecodedImg.classList.add("hidden"); decDecodedImg.removeAttribute("src"); }
    if (decDecodedText) { decDecodedText.textContent = ""; decDecodedText.classList.add("hidden"); }
    if (decodedLabel) decodedLabel.textContent = "Decoded";
    if (dlDecoded) { dlDecoded.classList.add("hidden"); dlDecoded.textContent = "Download Decoded File"; dlDecoded.onclick = null; }
    decForm.scrollIntoView({ behavior: "smooth" });
  }

  if (decClearBtn) {
    decClearBtn.addEventListener("click", (e) => {
      e.preventDefault();
      resetDecodingUI();
    });
  }
})();
