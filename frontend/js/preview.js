/**
 * Mini Print Studio — Thermal Preview Manager
 */
window.PreviewManager = {
  container: null,
  imageElement: null,
  badge: null,
  ditherSelect: null,
  ditherHint: null,
  zoomRange: null,
  debounceTimer: null,

  DITHER_TIPS: {
    "": "Using each image block's processing preset (Photo → Floyd–Steinberg, Manga → Bayer, Text/QR → Threshold)",
    "atkinson": "Use for: high-detail photos, sketches",
    "floyd-steinberg": "Use for: photos, smooth gradients (photo default)",
    "stucki": "Use for: smooth gradients with richer blacks",
    "bayer": "Use for: manga, logos, icons, flat graphics",
    "threshold": "Use for: text, QR codes, barcodes, line art",
  },

  init() {
    this.container = document.getElementById("thermalPaperContainer");
    this.imageElement = document.getElementById("paperImagePreview");
    this.badge = document.getElementById("previewDimensionBadge");
    this.ditherSelect = document.getElementById("ditherSelect");
    this.ditherHint = document.getElementById("ditherHint");
    this.zoomRange = document.getElementById("zoomRange");

    if (this.ditherSelect) {
      this.ditherSelect.addEventListener("change", () => {
        this.updateDitherHint();
        this.updatePreview();
      });
      this.updateDitherHint();
    }

    if (this.zoomRange) {
      this.zoomRange.addEventListener("input", (e) => {
        const scale = e.target.value;
        if (this.container) {
          this.container.style.transform = `scale(${scale})`;
        }
      });
    }
  },

  updateDitherHint() {
    if (this.ditherHint && this.ditherSelect) {
      const mode = this.ditherSelect.value;
      this.ditherHint.textContent = this.DITHER_TIPS[mode] || "";
    }
  },

  scheduleUpdate() {
    clearTimeout(this.debounceTimer);
    this.debounceTimer = setTimeout(() => {
      this.updatePreview();
    }, 250);
  },

  async updatePreview() {
    if (!window.EditorManager) return;

    const printReq = window.EditorManager.getPrintRequest();
    if (!printReq.blocks || printReq.blocks.length === 0) {
      this.imageElement.src = "";
      this.imageElement.style.display = "none";
      if (this.badge) this.badge.textContent = "Empty";
      return;
    }

    // Dither selection is applied centrally in EditorManager.getPrintRequest(),
    // so preview, print, and export all honour the toolbar choice.

    try {
      const res = await API.getPrintPreview(printReq);
      if (res && res.preview_url) {
        this.imageElement.src = res.preview_url;
        this.imageElement.style.display = "block";
        if (this.container) {
          this.container.style.width = `${Math.min(600, res.width_px)}px`;
        }
        if (this.badge) {
          const heightMm = Math.round(res.height_px / 8);
          this.badge.textContent = `${res.width_px} px | ${res.paper_width_mm} mm (~${heightMm}mm length)`;
        }
      }
    } catch (err) {
      console.warn("Failed to update thermal preview:", err);
    }
  }
};
