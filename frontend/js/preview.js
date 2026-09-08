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
    "": "Auto: each image uses its preset (photos → smooth hybrid, text/QR → sharp)",
    "hybrid": "Photo: Bayer + Threshold blend — turns on True Grayscale automatically",
    "threshold": "Text: sharp black-and-white, best for text, QR codes and line art",
    // Legacy algorithm names (pre-simplification UI) map to the nearest mode.
    "floyd-steinberg": "Photo: Bayer + Threshold blend — turns on True Grayscale automatically",
    "atkinson": "Photo: Bayer + Threshold blend — turns on True Grayscale automatically",
    "stucki": "Photo: Bayer + Threshold blend — turns on True Grayscale automatically",
    "bayer": "Text: sharp black-and-white, best for text, QR codes and line art",
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
        this.syncGrayscaleToggle();
        this.updateDitherHint();
        this.updatePreview();
      });
      this.syncGrayscaleToggle();
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

  /**
   * Photo mode prints best with the printer's real 16-level grayscale
   * (per-dot heat instead of black/white dither dots), so selecting it
   * turns the True Grayscale toggle on; Text/Default turn it back off.
   * The toggle stays manually overridable at any time — preview, print
   * and export all read it live via EditorManager.getPrintRequest().
   */
  syncGrayscaleToggle() {
    if (!this.ditherSelect) return;
    const raw = this.ditherSelect.value || "";
    const mode = window.normalizeDither ? window.normalizeDither(raw) : raw;
    const grayToggle = document.getElementById("grayPrintToggle");
    if (grayToggle) grayToggle.checked = (mode === "hybrid");
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
