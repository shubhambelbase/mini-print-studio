/**
 * Mini Print Studio — Main Application Controller
 */

window.AppSettings = null;

window.App = {
  async init() {
    console.log("Initializing Mini Print Studio...");

    // Initialize Lucide Icons
    if (window.lucide) window.lucide.createIcons();

    // Initialize sub-managers
    if (window.EditorManager) window.EditorManager.init();
    if (window.PreviewManager) window.PreviewManager.init();

    // Load initial settings & printer status
    await this.loadSettings();
    await this.checkPrinterStatus();
    this.loadBatchFromStorage();

    // Bind event listeners
    this.bindEvents();

    // Live job/printer events over SSE (fallback: 5s polling below)
    this.initEventSource();

    // Periodic printer status poller (every 5 seconds)
    setInterval(() => this.checkPrinterStatus(), 5000);
  },

  initEventSource() {
    if (this._eventSource) return;
    try {
      const es = new EventSource("/api/events");
      this._eventSource = es;
      es.onmessage = (e) => {
        let evt = null;
        try { evt = JSON.parse(e.data); } catch (err) { return; }
        if (!evt) return;
        if (evt.type === "printer") {
          this.checkPrinterStatus();
        } else if (evt.type === "job") {
          // Refresh queue status (batch tab) and job records
          this.pollQueue();
          const rec = (this._batchJobs || []).find(j => j.id === evt.job_id);
          if (rec) rec.status = evt.status;
          const allTerminal = this._batchJobs && this._batchJobs.length > 0 &&
            this._batchJobs.every(j => ["completed", "failed", "cancelled"].includes(j.status));
          if (allTerminal) {
            this.showToast(`Batch complete: ${this._batchJobs.length}/${this._batchJobs.length} jobs finished.`, "success");
            this._batchJobs = [];
            this.pollQueue();
          }
        }
      };
      es.onerror = () => {
        // EventSource auto-reconnects; fall back to polling in the meantime.
      };
    } catch (err) {
      console.warn("SSE unavailable, falling back to polling:", err);
    }
  },

  async loadSettings() {
    try {
      window.AppSettings = await API.getSettings();
      if (window.AppSettings) {
        this.applyTheme(window.AppSettings.app.theme || "dark");
        // Update setting inputs
        document.getElementById("settingPaperWidthMm").value = window.AppSettings.printer.paper_width_mm;
        document.getElementById("settingPrintWidthPx").value = window.AppSettings.printer.printable_width_px;
        document.getElementById("settingMarginPx").value = window.AppSettings.printer.margin_px;
        document.getElementById("settingDensity").value = window.AppSettings.printer.density;
        document.getElementById("settingFeedDots").value = window.AppSettings.printer.tear_bar_feed_dots ?? 130;
      }
    } catch (err) {
      console.warn("Could not load initial settings:", err);
    }
  },

  async checkPrinterStatus() {
    try {
      const status = await API.getPrinterStatus();
      this.updatePrinterStatusUI(status);
    } catch (err) {
      console.warn("Printer status check failed:", err);
    }
  },

  updatePrinterStatusUI(status) {
    const dot = document.getElementById("statusDot");
    const headerName = document.getElementById("headerPrinterName");
    const cardName = document.getElementById("cardPrinterName");
    const cardWidth = document.getElementById("cardPaperWidth");
    const cardProtocol = document.getElementById("cardProtocol");

    const prevPrinterId = window.ActivePrinter ? window.ActivePrinter.id : null;
    const batteryWrap = document.getElementById("cardBattery");
    const batteryLevel = document.getElementById("batteryLevel");
    const headerBattery = document.getElementById("headerBattery");
    const headerBatteryLevel = document.getElementById("headerBatteryLevel");

    const showBattery = (level) => {
      if (batteryWrap && batteryLevel) {
        batteryLevel.textContent = level;
        batteryWrap.style.display = "";
      }
      if (headerBattery && headerBatteryLevel) {
        headerBatteryLevel.textContent = level;
        headerBattery.style.display = "inline-flex";
        headerBattery.classList.remove("low", "critical");
        if (level <= 20) headerBattery.classList.add("critical");
        else if (level <= 50) headerBattery.classList.add("low");
      }
    };
    const hideBattery = () => {
      if (batteryWrap) batteryWrap.style.display = "none";
      if (headerBattery) headerBattery.style.display = "none";
    };

    const showDeviceInfo = (info) => {
      const el = document.getElementById("cardDeviceInfo");
      if (!el) return;
      if (!info) { el.style.display = "none"; return; }
      const model = info.model || (info.text ? info.text.split(" ")[0] : null);
      const firmware = info.firmware || null;
      const parts = [];
      if (model) parts.push(`Model: ${this.escapeHtml(model)}`);
      if (firmware) parts.push(`FW: ${this.escapeHtml(firmware)}`);
      if (!parts.length) { el.style.display = "none"; return; }
      el.textContent = parts.join(" • ");
      el.style.display = "";
    };

    if (status.connected && status.current_printer) {
      window.ActivePrinter = status.current_printer;
      if (dot) dot.className = "status-dot connected";
      if (headerName) headerName.textContent = status.current_printer.name;
      if (cardName) cardName.textContent = status.current_printer.name;
      if (cardWidth) cardWidth.textContent = `${status.current_printer.paper_width_mm} mm (${status.current_printer.printable_width_px}px)`;
      if (cardProtocol) cardProtocol.textContent = (status.current_printer.protocol || "ESC/POS").toUpperCase();
      if (status.battery_level !== null && status.battery_level !== undefined) {
        showBattery(status.battery_level);
      } else {
        hideBattery();
      }
      showDeviceInfo(status.device_info);
    } else {
      window.ActivePrinter = null;
      if (dot) dot.className = "status-dot";
      if (headerName) headerName.textContent = "Disconnected";
      if (cardName) cardName.textContent = "No Printer Connected";
      hideBattery();
      showDeviceInfo(null);
    }

    if (prevPrinterId !== (window.ActivePrinter ? window.ActivePrinter.id : null)) {
      if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
    }
  },

  bindEvents() {
    // Theme toggle
    document.getElementById("btnThemeToggle")?.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "dark";
      const next = current === "dark" ? "light" : "dark";
      this.applyTheme(next);
      if (window.AppSettings) {
        window.AppSettings.app.theme = next;
        API.saveSettings(window.AppSettings);
      }
    });

    // Workspace Buttons
    document.getElementById("btnNewPrint")?.addEventListener("click", () => {
      if (window.EditorManager) {
        window.EditorManager.loadTemplate([], "Untitled Print Note");
        this.showToast("Started new print document", "info");
      }
      this.openEditorTab();
    });

    // Batch tab
    document.getElementById("btnOpenBatch")?.addEventListener("click", () => this.openBatchTab());
    document.getElementById("btnBatchPrint")?.addEventListener("click", () => this.openBatchTab());
    document.getElementById("btnAddToBatch")?.addEventListener("click", () => this.handleAddToBatch());
    document.getElementById("btnClearBatch")?.addEventListener("click", () => this.clearBatch());
    document.getElementById("btnSendBatchQueue")?.addEventListener("click", () => this.sendBatchToQueue());
    document.getElementById("batchCopies")?.addEventListener("input", () => this.updateBatchTotal());

    // Undo / Redo
    document.getElementById("btnUndo")?.addEventListener("click", () => window.EditorManager && window.EditorManager.undo());
    document.getElementById("btnRedo")?.addEventListener("click", () => window.EditorManager && window.EditorManager.redo());

    // Receipt designer block buttons
    document.getElementById("btnAddTable")?.addEventListener("click", () => window.EditorManager && window.EditorManager.addBlock("table"));
    document.getElementById("btnAddTotals")?.addEventListener("click", () => window.EditorManager && window.EditorManager.addBlock("totals"));

    // Toolbar wizards & tools
    document.getElementById("btnWifiWizard")?.addEventListener("click", () => this.openModal("wifiModal"));
    document.getElementById("btnCloseWifiModal")?.addEventListener("click", () => this.closeModal("wifiModal"));
    document.getElementById("btnCreateWifiQr")?.addEventListener("click", () => this.handleWifiQr());

    document.getElementById("btnContactWizard")?.addEventListener("click", () => this.openModal("contactModal"));
    document.getElementById("btnCloseContactModal")?.addEventListener("click", () => this.closeModal("contactModal"));
    document.getElementById("btnCreateContactQr")?.addEventListener("click", () => this.handleContactQr());

    document.getElementById("btnCsvLabels")?.addEventListener("click", () => this.openCsvModal());
    document.getElementById("btnCloseCsvModal")?.addEventListener("click", () => this.closeModal("csvModal"));
    document.getElementById("csvFileInput")?.addEventListener("change", () => this.previewCsv());
    document.getElementById("btnCreateCsvLabels")?.addEventListener("click", () => this.handleCsvLabels());

    document.getElementById("btnImportClipboard")?.addEventListener("click", () => this.openModal("clipboardModal"));
    document.getElementById("btnCloseClipboardModal")?.addEventListener("click", () => this.closeModal("clipboardModal"));
    document.getElementById("btnImportClipboardText")?.addEventListener("click", () => this.handleClipboardImport());

    // Crop modal
    document.getElementById("btnCloseCropModal")?.addEventListener("click", () => this.closeModal("cropModal"));
    document.getElementById("btnResetCrop")?.addEventListener("click", () => this.initCropSelection());
    document.getElementById("btnApplyCrop")?.addEventListener("click", () => this.applyCrop());

    // Keyboard shortcuts
    document.addEventListener("keydown", (e) => this.handleKeydown(e));

    // Print Buttons
    document.getElementById("btnPrintNow")?.addEventListener("click", () => this.handlePrint());
    document.getElementById("btnTestPrint")?.addEventListener("click", () => this.handleTestPrint());
    document.getElementById("btnCancelPrint")?.addEventListener("click", () => this.handleCancelPrint());
    document.getElementById("btnExportPng")?.addEventListener("click", () => this.handleExport());

    // Document Save / Open
    document.getElementById("btnSaveDocument")?.addEventListener("click", () => this.handleSaveDocument());
    document.getElementById("btnOpenDocuments")?.addEventListener("click", () => this.openDocumentsModal());
    document.getElementById("btnCloseDocumentsModal")?.addEventListener("click", () => this.closeModal("documentsModal"));

    // Navigation Modals
    document.getElementById("btnOpenTemplates")?.addEventListener("click", () => this.openTemplatesModal());
    document.getElementById("btnCloseTemplatesModal")?.addEventListener("click", () => this.closeModal("templatesModal"));

    document.getElementById("btnOpenHistory")?.addEventListener("click", () => this.openHistoryModal());
    document.getElementById("btnCloseHistoryModal")?.addEventListener("click", () => this.closeModal("historyModal"));
    document.getElementById("btnClearHistory")?.addEventListener("click", () => this.handleClearHistory());

    document.getElementById("btnDevicesModal")?.addEventListener("click", () => this.openDevicesModal());
    document.getElementById("btnQuickConnect")?.addEventListener("click", () => this.openDevicesModal());
    document.getElementById("btnCloseDevicesModal")?.addEventListener("click", () => this.closeModal("devicesModal"));
    document.getElementById("btnScanDevices")?.addEventListener("click", () => this.handleScanDevices());
    document.getElementById("btnConnectSelected")?.addEventListener("click", () => this.handleConnectDevice());
    document.getElementById("btnRetryConnect")?.addEventListener("click", () => this.handleRetryConnect());
    document.getElementById("btnDisconnectDevice")?.addEventListener("click", () => this.handleDisconnectDevice());
    document.getElementById("btnCloseConnectModal")?.addEventListener("click", () => this.closeModal("connectModal"));

    document.getElementById("btnOpenSettings")?.addEventListener("click", () => this.openModal("settingsModal"));
    document.getElementById("btnCloseSettingsModal")?.addEventListener("click", () => this.closeModal("settingsModal"));
    document.getElementById("btnSaveSettings")?.addEventListener("click", () => this.handleSaveSettings());

    // Debug packet inspector
    document.getElementById("btnOpenDebug")?.addEventListener("click", () => this.openDebugModal());
    document.getElementById("btnCloseDebugModal")?.addEventListener("click", () => this.closeModal("debugModal"));
    document.getElementById("debugTabPackets")?.addEventListener("click", () => {
      document.getElementById("debugTabPackets")?.classList.add("active");
      document.getElementById("debugTabTrace")?.classList.remove("active");
      this.renderDebugPackets();
    });
    document.getElementById("debugTabTrace")?.addEventListener("click", () => {
      document.getElementById("debugTabTrace")?.classList.add("active");
      document.getElementById("debugTabPackets")?.classList.remove("active");
      this.renderDebugTrace();
    });

    // Connection type select toggling
    document.getElementById("connTypeSelect")?.addEventListener("change", (e) => {
      const addrGroup = document.getElementById("addressGroup");
      if (addrGroup) {
        addrGroup.style.display = e.target.value === "bluetooth_classic" ? "block" : "none";
      }
      this.handleScanDevices();
    });
  },

  applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const icon = document.getElementById("btnThemeToggle");
    if (icon) {
      icon.innerHTML = theme === "dark" ? '<i data-lucide="sun"></i>' : '<i data-lucide="moon"></i>';
      if (window.lucide) window.lucide.createIcons();
    }
  },

  async handlePrint() {
    if (!window.EditorManager) return;
    const printReq = window.EditorManager.getPrintRequest();

    if (!printReq.blocks || printReq.blocks.length === 0) {
      this.showToast("Cannot print empty document. Please add content blocks.", "error");
      return;
    }

    this.setPrintingState(true, "SENDING...");

    try {
      this.showToast("Sending thermal print job to printer...", "info");
      const job = await API.submitPrintJob(printReq);

      if (job.status === "failed") {
        this.showToast(`Print failed: ${job.error_message || 'Hardware output error'}`, "error");
        return;
      }

      // Poll the job until it reaches a terminal state
      const terminal = await this.pollJob(job.id, printReq.copies || 1);
      if (terminal.status === "completed") {
        this.showToast(`Print job '${terminal.title}' sent to printer!`, "success");
      } else if (terminal.status === "cancelled") {
        this.showToast("Print job cancelled.", "info");
      } else {
        this.showToast(`Print failed: ${terminal.error_message || 'Hardware output error'}`, "error");
      }
    } catch (err) {
      this.showToast(`Print failed: ${err.message}`, "error");
    } finally {
      this.setPrintingState(false);
    }
  },

  async pollJob(jobId, copies) {
    const maxAttempts = 1200; // ~60s at 50ms
    for (let i = 0; i < maxAttempts; i++) {
      const job = await API.getPrintJobStatus(jobId);
      const status = job.status || "queued";
      if (status === "printing" || status === "preparing") {
        this.setPrintingState(true, "PRINTING...");
      }
      if (["completed", "failed", "cancelled"].includes(status)) {
        return job;
      }
      await new Promise(r => setTimeout(r, 50));
    }
    return { status: "failed", error_message: "Timed out waiting for print job." };
  },

  setPrintingState(printing, label = "PRINTING...") {
    const btn = document.getElementById("btnPrintNow");
    const cancelBtn = document.getElementById("btnCancelPrint");
    const testBtn = document.getElementById("btnTestPrint");
    const exportBtn = document.getElementById("btnExportPng");
    if (btn) {
      btn.disabled = printing;
      btn.innerHTML = printing
        ? `<i data-lucide="loader"></i> ${label}`
        : '<i data-lucide="printer"></i> PRINT NOW';
      if (window.lucide) window.lucide.createIcons();
    }
    if (cancelBtn) cancelBtn.style.display = printing ? "inline-flex" : "none";
    if (testBtn) testBtn.disabled = printing;
    if (exportBtn) exportBtn.disabled = printing;
  },

  async handleCancelPrint() {
    try {
      const res = await API.cancelPrintJob();
      if (res.cancelled_jobs && res.cancelled_jobs.length > 0) {
        this.showToast(`Cancelled ${res.cancelled_jobs.length} job(s).`, "info");
      } else {
        this.showToast("No active print job to cancel.", "info");
      }
    } catch (err) {
      this.showToast(`Cancel failed: ${err.message}`, "error");
    }
  },

  async handleExport() {
    if (!window.EditorManager) return;
    const printReq = window.EditorManager.getPrintRequest();
    if (!printReq.blocks || printReq.blocks.length === 0) {
      this.showToast("Nothing to export. Please add content blocks.", "error");
      return;
    }
    try {
      this.showToast("Rendering export...", "info");
      const blob = await API.exportPrint(printReq, "png");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(printReq.title || "print").replace(/[^\w\- ]/g, "").slice(0, 40) || "print"}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      this.showToast("Preview exported as PNG.", "success");
    } catch (err) {
      this.showToast(`Export failed: ${err.message}`, "error");
    }
  },

  async handleTestPrint() {
    this.setPrintingState(true, "TESTING...");
    try {
      this.showToast("Generating diagnostic test page...", "info");
      const job = await API.testPrint();
      if (job.status === "failed") {
        this.showToast(`Test print failed: ${job.error_message || 'Hardware error'}`, "error");
        return;
      }
      const terminal = await this.pollJob(job.id, 1);
      if (terminal.status === "completed") {
        this.showToast("Hardware diagnostic test page printed!", "success");
      } else {
        this.showToast(`Test print failed: ${terminal.error_message || 'Hardware error'}`, "error");
      }
    } catch (err) {
      this.showToast(`Test print failed: ${err.message}`, "error");
    } finally {
      this.setPrintingState(false);
    }
  },

  // Templates Modal Handler
  async openTemplatesModal() {
    this.openModal("templatesModal");
    this._templateCategory = this._templateCategory || "All";

    const grid = document.getElementById("templatesGrid");
    const filterBar = document.getElementById("templatesFilterBar");
    if (!grid) return;
    grid.innerHTML = '<div style="color: var(--text-muted);">Loading templates...</div>';

    try {
      const templates = await API.getTemplates();
      // Build the category filter chips
      if (filterBar) {
        const categories = ["All", ...new Set(templates.map(t => t.category).filter(Boolean))];
        filterBar.innerHTML = "";
        categories.forEach(cat => {
          const chip = document.createElement("button");
          chip.className = "tpl-filter-chip" + (cat === this._templateCategory ? " active" : "");
          chip.textContent = cat;
          chip.onclick = () => {
            this._templateCategory = cat;
            this.renderTemplatesGrid(templates);
          };
          filterBar.appendChild(chip);
        });
      }
      this.renderTemplatesGrid(templates);
    } catch (err) {
      grid.innerHTML = `<div style="color: var(--accent-danger);">Failed to load templates: ${err.message}</div>`;
    }
  },

  renderTemplatesGrid(templates) {
    const grid = document.getElementById("templatesGrid");
    if (!grid) return;
    grid.innerHTML = "";

    const cat = this._templateCategory || "All";
    let filtered = cat === "All" ? templates.slice() : templates.filter(t => t.category === cat);
    // Favorites first
    filtered.sort((a, b) => (this.isFavoriteTemplate(b.id) ? 1 : 0) - (this.isFavoriteTemplate(a.id) ? 1 : 0));
    if (filtered.length === 0) {
      grid.innerHTML = '<div style="color: var(--text-muted); padding: 20px; text-align: center;">No templates in this category.</div>';
      return;
    }

    // Re-sync chip active states
    const chips = document.querySelectorAll("#templatesFilterBar .tpl-filter-chip");
    chips.forEach(c => c.classList.toggle("active", c.textContent === cat));

    filtered.forEach(tpl => {
      const item = document.createElement("div");
      item.className = "template-item";
      const fav = this.isFavoriteTemplate(tpl.id);
      item.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <div class="template-name">${this.escapeHtml(tpl.name)}</div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <button class="btn-secondary small batch-add-btn" title="Add to batch basket" data-blocks='${this.escapeHtml(JSON.stringify(tpl.blocks))}' data-name="${this.escapeHtml(tpl.name)}">
              <i data-lucide="layers" style="width: 12px; height: 12px;"></i> Batch
            </button>
            <span class="status-badge" style="font-size: 0.75rem;">${this.escapeHtml(tpl.category)}</span>
            <button class="btn-icon star-btn ${fav ? 'active' : ''}" data-tpl="${this.escapeHtml(tpl.id)}" title="${fav ? 'Remove favorite' : 'Add to favorites'}">
              <i data-lucide="star"></i>
            </button>
          </div>
        </div>
        <div class="template-desc">${this.escapeHtml(tpl.description)}</div>
      `;
      const star = item.querySelector(".star-btn");
      star.addEventListener("click", async (e) => {
        e.stopPropagation();
        const wasFav = this.isFavoriteTemplate(tpl.id);
        const nowFav = await this.toggleTemplateFavorite(tpl.id, !wasFav);
        if (nowFav !== null) {
          star.classList.toggle("active", nowFav);
          star.title = nowFav ? "Remove favorite" : "Add to favorites";
        }
      });
      const batchBtn = item.querySelector(".batch-add-btn");
      batchBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        try {
          const blocks = JSON.parse(batchBtn.dataset.blocks);
          this.addToBatch(tpl.name, blocks, "template");
        } catch (err) {
          this.showToast("Could not add template to batch.", "error");
        }
      });
      item.onclick = () => {
        if (window.EditorManager) {
          window.EditorManager.loadTemplate(tpl.blocks, tpl.name);
        }
        this.closeModal("templatesModal");
        this.showToast(`Loaded template '${tpl.name}'`, "success");
      };
      grid.appendChild(item);
    });
    if (window.lucide) window.lucide.createIcons();
  },

  // Documents Modal Handler
  async handleSaveDocument() {
    if (!window.EditorManager) return;
    const doc = window.EditorManager.getDocumentData();
    if (!doc.blocks || doc.blocks.length === 0) {
      this.showToast("Cannot save an empty document.", "error");
      return;
    }
    try {
      const saved = await API.saveDocument(doc);
      this.showToast(`Document '${saved.title}' saved.`, "success");
    } catch (err) {
      this.showToast(`Failed to save document: ${err.message}`, "error");
    }
  },

  async openDocumentsModal() {
    this.openModal("documentsModal");
    const list = document.getElementById("documentsList");
    if (!list) return;
    list.innerHTML = '<div style="color: var(--text-muted);">Loading documents...</div>';

    try {
      const documents = await API.getDocuments();
      list.innerHTML = "";
      if (documents.length === 0) {
        list.innerHTML = '<div style="color: var(--text-muted); padding: 20px; text-align: center;">No saved documents yet. Click Save in the editor to store one.</div>';
        return;
      }
      documents.forEach(doc => {
        const div = document.createElement("div");
        div.className = "history-item";
        div.style.cursor = "pointer";
        div.innerHTML = `
          <div class="history-info">
            <div class="history-title">${this.escapeHtml(doc.title)}</div>
            <div class="history-meta">${this.escapeHtml(doc.updated_at || "")} • ${doc.blocks.length} block(s)</div>
          </div>
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn-secondary small doc-batch-btn" style="color: var(--accent);" title="Add to batch basket"><i data-lucide="layers" style="width: 12px; height: 12px;"></i> Batch</button>
            <button class="btn-secondary small" style="padding: 4px 10px; font-size: 0.8rem;">Load</button>
            <button class="btn-secondary small" style="padding: 4px 10px; font-size: 0.8rem; color: var(--accent-danger);">Delete</button>
          </div>
        `;
        div.querySelector(".doc-batch-btn")?.addEventListener("click", (e) => {
          e.stopPropagation();
          this.addToBatch(doc.title, doc.blocks, "document");
        });
        div.querySelector("button:nth-child(2)")?.addEventListener("click", (e) => {
          e.stopPropagation();
          if (window.EditorManager) {
            window.EditorManager.loadTemplate(doc.blocks, doc.title);
          }
          this.closeModal("documentsModal");
          this.showToast(`Loaded document '${doc.title}'.`, "success");
        });
        div.querySelector("button:nth-child(3)")?.addEventListener("click", async (e) => {
          e.stopPropagation();
          try {
            await API.deleteDocument(doc.id);
            this.openDocumentsModal();
            this.showToast(`Deleted document '${doc.title}'.`, "info");
          } catch (err) {
            this.showToast(`Failed to delete document: ${err.message}`, "error");
          }
        });
        list.appendChild(div);
      });
    } catch (err) {
      list.innerHTML = `<div style="color: var(--accent-danger);">Failed to load documents: ${err.message}</div>`;
    }
  },

  // History Modal Handler
  async openHistoryModal() {
    this.openModal("historyModal");
    const list = document.getElementById("historyList");
    if (!list) return;
    list.innerHTML = '<div style="color: var(--text-muted);">Loading history...</div>';

    try {
      const history = await API.getHistory();
      const stats = await API.getHistoryStats();

      // Stats bar
      const statsBar = document.getElementById("historyStats");
      if (statsBar) {
        const sc = stats.status_counts || {};
        statsBar.innerHTML = `
          <div class="stat-cell"><b>${stats.total_jobs ?? 0}</b><span>total</span></div>
          <div class="stat-cell"><b>${sc.completed ?? 0}</b><span>printed</span></div>
          <div class="stat-cell"><b>${sc.failed ?? 0}</b><span>failed</span></div>
          <div class="stat-cell"><b>${sc.cancelled ?? 0}</b><span>cancelled</span></div>
          <div class="stat-cell"><b>${stats.today_jobs ?? 0}</b><span>today</span></div>
          <div class="stat-cell"><b>${(stats.est_paper_mm ?? 0).toFixed(0)} mm</b><span>paper</span></div>
        `;
      }
      this.renderHistoryCharts(stats);

      list.innerHTML = "";
      if (history.length === 0) {
        list.innerHTML = '<div style="color: var(--text-muted); padding: 20px; text-align: center;">No print history recorded yet.</div>';
        return;
      }
      history.forEach(item => {
        const div = document.createElement("div");
        div.className = "history-item";
        div.innerHTML = `
          <div style="display: flex; align-items: center; gap: 12px;">
            ${item.preview_url ? `<img src="${item.preview_url}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color);">` : ''}
            <div class="history-info">
              <div class="history-title">${this.escapeHtml(item.title)}</div>
              <div class="history-meta">${this.escapeHtml(item.timestamp)} • ${this.escapeHtml(item.printer_name)}</div>
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="status-badge" style="color: ${item.status === 'completed' ? 'var(--accent-success)' : 'var(--accent-danger)'};">${this.escapeHtml(item.status)}</span>
            ${Array.isArray(item.blocks) && item.blocks.length ? `<button class="btn-secondary small reprint-btn" title="Reprint">↻ Reprint</button>` : ''}
          </div>
        `;
        const reprint = div.querySelector(".reprint-btn");
        if (reprint) {
          reprint.addEventListener("click", async (e) => {
            e.stopPropagation();
            try {
              await API.submitPrintJob({ title: item.title || "Reprint", blocks: item.blocks });
              this.showToast(`Reprint of '${item.title}' queued.`, "success");
            } catch (err) {
              this.showToast(`Reprint failed: ${err.message}`, "error");
            }
          });
        }
        list.appendChild(div);
      });
    } catch (err) {
      list.innerHTML = `<div style="color: var(--accent-danger);">Failed to load history: ${err.message}</div>`;
    }
  },

  async handleClearHistory() {
    try {
      await API.clearHistory();
      this.openHistoryModal();
      this.showToast("Print job history cleared.", "info");
    } catch (err) {
      this.showToast("Failed to clear history.", "error");
    }
  },

  // ── History statistics charts ───────────────────────────────
  renderHistoryCharts(stats) {
    const container = document.getElementById("historyCharts");
    if (!container) return;
    if (!stats || !stats.total_jobs) { container.innerHTML = ""; return; }

    const bar = (label, value, max, color) => `
      <div class="chart-row">
        <span class="chart-label">${this.escapeHtml(label)}</span>
        <div class="chart-track"><div class="chart-bar" style="width: ${max > 0 ? Math.max(2, Math.round(value / max * 100)) : 0}%; background: ${color};"></div></div>
        <span class="chart-value">${value}</span>
      </div>`;

    const sc = stats.status_counts || {};
    const statusMax = Math.max(1, sc.completed || 0, sc.failed || 0, sc.cancelled || 0);
    const types = Object.entries(stats.by_type || {});
    const typeMax = Math.max(1, ...types.map(([, v]) => v));

    const typeRows = types.map(([t, v]) => bar(t, v, typeMax, "var(--accent)")).join("");
    const statusRows =
      bar("Printed", sc.completed || 0, statusMax, "var(--accent-success)") +
      bar("Failed", sc.failed || 0, statusMax, "var(--accent-danger)") +
      bar("Cancelled", sc.cancelled || 0, statusMax, "var(--accent-warning)");

    container.innerHTML = `
      <div class="chart-section">
        <div class="chart-title">STATUS</div>
        ${statusRows}
      </div>
      ${typeRows ? `<div class="chart-section"><div class="chart-title">CONTENT TYPES</div>${typeRows}</div>` : ""}
      <div class="chart-section">
        <div class="chart-title">USAGE</div>
        <div class="chart-row">
          <span class="chart-label">Paper used</span>
          <div class="chart-track"><div class="chart-bar" style="width: ${Math.min(100, Math.round((stats.est_paper_mm || 0) / 10))}%; background: var(--accent);"></div></div>
          <span class="chart-value">${(stats.est_paper_mm || 0).toFixed(0)} mm</span>
        </div>
        <div class="chart-row">
          <span class="chart-label">Printed today</span>
          <div class="chart-track"><div class="chart-bar" style="width: ${Math.min(100, (stats.today_jobs || 0) * 12)}%; background: var(--accent);"></div></div>
          <span class="chart-value">${stats.today_jobs || 0}</span>
        </div>
      </div>`;
  },

  // ── Debug packet inspector ──────────────────────────────────
  async openDebugModal() {
    this.openModal("debugModal");
    this.renderDebugPackets();
  },

  async renderDebugPackets() {
    const view = document.getElementById("debugView");
    const summary = document.getElementById("debugSummary");
    if (!view) return;
    view.innerHTML = '<div style="color: var(--text-muted); padding: 10px;">Loading last job payload...</div>';
    if (summary) summary.innerHTML = "";
    try {
      const res = await API.getDebugLastPayload();
      if (summary && res.note) summary.innerHTML = `<div class="settings-note">${this.escapeHtml(res.note)}</div>`;
      if (summary && res.packet_count) {
        summary.innerHTML = `
          <div class="stat-cell"><b>${res.packet_count}</b><span>packets</span></div>
          <div class="stat-cell"><b>${res.total_bytes}</b><span>bytes</span></div>
          <div class="stat-cell"><b style="color: ${res.crc_failures ? 'var(--accent-danger)' : 'var(--accent-success)'};">${res.crc_failures || 0}</b><span>CRC fails</span></div>
          <div class="stat-cell"><b>${this.escapeHtml((res.protocol || "unknown").toUpperCase())}</b><span>protocol</span></div>`;
      }
      if (!res.packets || !res.packets.length) {
        view.innerHTML = '<div style="color: var(--text-muted); padding: 10px;">No packets to display.</div>';
        return;
      }
      const rows = res.packets.map((p, i) => {
        const name = p.opcode_name || "?";
        const op = p.opcode !== null && p.opcode !== undefined ? "0x" + p.opcode.toString(16).toUpperCase().padStart(2, "0") : "—";
        const crc = p.crc_ok === null ? "—" : (p.crc_ok ? '<span style="color: var(--accent-success);">OK</span>' : '<span style="color: var(--accent-danger);">FAIL</span>');
        const hexClass = p.crc_ok === false ? 'debug-bad' : '';
        return `<tr class="${hexClass}">
          <td>${i + 1}</td>
          <td>${op}</td>
          <td>${this.escapeHtml(name)}</td>
          <td>${p.length !== null && p.length !== undefined ? p.length : "—"}</td>
          <td>${crc}</td>
          <td class="debug-hex-cell"><code>${this.escapeHtml(p.payload_hex || "")}</code></td>
        </tr>`;
      }).join("");
      view.innerHTML = `<table class="debug-table"><thead><tr><th>#</th><th>Opcode</th><th>Command</th><th>Len</th><th>CRC</th><th>Payload (hex)</th></tr></thead><tbody>${rows}</tbody></table>`;
    } catch (err) {
      view.innerHTML = `<div style="color: var(--accent-danger);">Failed to load packets: ${this.escapeHtml(err.message)}</div>`;
    }
  },

  async renderDebugTrace() {
    const view = document.getElementById("debugView");
    const summary = document.getElementById("debugSummary");
    if (!view) return;
    view.innerHTML = '<div style="color: var(--text-muted); padding: 10px;">Loading wire trace...</div>';
    if (summary) summary.innerHTML = "";
    try {
      const res = await API.getDebugTrace();
      if (summary) {
        const dev = res.device_info || {};
        const infoParts = [];
        if (dev.model) infoParts.push(`Model: ${dev.model}`);
        if (dev.firmware) infoParts.push(`FW: ${dev.firmware}`);
        const infoStr = infoParts.length ? infoParts.join(" • ") : "No device info captured";
        summary.innerHTML = `
          <div class="stat-cell"><b>${res.connected ? "●" : "○"}</b><span>connected</span></div>
          <div class="stat-cell"><b>${res.trace_size}</b><span>entries</span></div>
          <div class="stat-cell"><b>${this.escapeHtml((res.protocol || "unknown").toUpperCase())}</b><span>protocol</span></div>
          <div class="stat-cell" style="min-width: 40%;"><span>${this.escapeHtml(infoStr)}</span></div>`;
      }
      const trace = res.trace || [];
      if (!trace.length) {
        view.innerHTML = '<div style="color: var(--text-muted); padding: 10px;">No wire activity recorded yet. Print something first, or check the "Last Job Packets" tab.</div>';
        return;
      }
      const rows = trace.map((t, i) => `
        <tr class="${t.dir === "R" ? "trace-rx" : "trace-tx"}">
          <td>${i + 1}</td>
          <td>${t.dir === "R" ? "RX ←" : "TX →"}</td>
          <td>${t.n_bytes || 0}</td>
          <td class="debug-hex-cell"><code>${this.escapeHtml(t.hex)}</code></td>
        </tr>`).join("");
      view.innerHTML = `<table class="debug-table"><thead><tr><th>#</th><th>Dir</th><th>Bytes</th><th>Hex</th></tr></thead><tbody>${rows}</tbody></table>`;
    } catch (err) {
      view.innerHTML = `<div style="color: var(--accent-danger);">Failed to load trace: ${this.escapeHtml(err.message)}</div>`;
    }
  },

  // Device Manager Modal Handlers
  openDevicesModal() {
    this.openModal("devicesModal");
    this.handleScanDevices();
  },

  async handleScanDevices() {
    const list = document.getElementById("scannedDevicesList");
    const scanBtn = document.getElementById("btnScanDevices");
    if (!list) return;

    if (scanBtn) {
      scanBtn.disabled = true;
      scanBtn.innerHTML = '<i data-lucide="loader" style="animation: spin 1s linear infinite;"></i> Scanning…';
      if (window.lucide) window.lucide.createIcons();
    }

    list.innerHTML = `<div style="color: var(--text-muted); padding: 10px;">Searching for nearby Bluetooth hardware...</div>`;

    try {
      const res = await API.request("/printers");
      list.innerHTML = "";
      if (!res.printers || res.printers.length === 0) {
        list.innerHTML = `<div style="color: var(--text-muted); padding: 10px;">No Bluetooth printers found. Make sure your printer is turned on and Bluetooth is enabled.</div>`;
        return;
      }
      res.printers.forEach(dev => {
        const item = document.createElement("div");
        item.className = "history-item";
        item.style.cursor = "pointer";
        item.innerHTML = `
          <div class="history-info">
            <div class="history-title" style="display:flex; align-items:center; gap:8px;">
              ${this.escapeHtml(dev.name)}
              <span class="status-badge" style="font-size:0.7rem; padding: 2px 6px;">${this.escapeHtml(dev.paper_width_mm)}mm</span>
            </div>
            <div class="history-meta">${this.escapeHtml(dev.connection_type).toUpperCase()} • Protocol: ${this.escapeHtml(dev.protocol || 'escpos').toUpperCase()} • ${this.escapeHtml(dev.address)}</div>
          </div>
          <button class="btn-secondary" style="padding: 4px 12px; font-size: 0.8rem;">Connect</button>
        `;
        item.onclick = () => this.connectToDevice(dev);
        list.appendChild(item);
      });
    } catch (err) {
      list.innerHTML = `<div style="color: var(--accent-danger); padding: 10px;">Scan failed: ${err.message}</div>`;
    } finally {
      if (scanBtn) {
        scanBtn.disabled = false;
        scanBtn.innerHTML = '<i data-lucide="search"></i> Scan BLE Printers';
        if (window.lucide) window.lucide.createIcons();
      }
    }
  },

  // ── Interactive connection flow ────────────────────────────
  connectToDevice(dev) {
    // Called when a scanned device is clicked
    document.getElementById("connTypeSelect").value = dev.connection_type || "ble";
    document.getElementById("connProtocolSelect").value = dev.protocol || "escpos";
    document.getElementById("deviceAddressInput").value = dev.address || "";
    this.handleConnectDevice();
  },

  async handleConnectDevice() {
    const connType = document.getElementById("connTypeSelect").value;
    const protocol = document.getElementById("connProtocolSelect").value;
    const address = document.getElementById("deviceAddressInput").value;
    if (!address) {
      this.showToast("Enter the printer address (BLE MAC or COM port).", "error");
      return;
    }
    this._lastConn = { connType, protocol, address };

    this._startConnecting();

    try {
      const status = await API.connectPrinter(`printer-${Date.now()}`, connType, address, protocol);
      if (status.connected) {
        await this._finishConnectingSuccess(status);
      } else {
        this._failConnecting(status.message || "Printer did not respond.");
      }
    } catch (err) {
      this._failConnecting(err.message || "Connection failed.");
    }
  },

  _setStepIcon(step, iconName) {
    const wrapper = step.querySelector(".conn-step-icon");
    if (!wrapper) return;
    wrapper.innerHTML = `<i data-lucide="${iconName}"></i>`;
    if (window.lucide) window.lucide.createIcons();
  },

  _startConnecting() {
    const panel = document.getElementById("connPanel");
    const connected = document.getElementById("connConnected");
    if (panel) panel.style.display = "block";
    if (connected) connected.style.display = "none";
    document.getElementById("connError")?.style.setProperty("display", "none");
    document.getElementById("connWaiting")?.style.setProperty("display", "none");
    document.getElementById("btnConnectSelected").disabled = true;
    document.getElementById("btnScanDevices").disabled = true;
    this.openModal("connectModal");

    // Animate the progress steps while the real connect call runs.
    // When the steps are exhausted, keep the last one pulsing and show a
    // "waiting for response" line so the UI never looks frozen.
    const steps = document.querySelectorAll("#connProgress .conn-step");
    steps.forEach(s => { s.className = "conn-step"; });
    let i = 0;
    if (this._connStepTimer) clearInterval(this._connStepTimer);
    this._connStepTimer = setInterval(() => {
      if (i >= steps.length) {
        clearInterval(this._connStepTimer);
        this._connStepTimer = null;
        steps.forEach(s => s.classList.remove("active"));
        const last = steps[steps.length - 1];
        if (last) last.classList.add("active");
        const waiting = document.getElementById("connWaiting");
        if (waiting) waiting.style.display = "flex";
        return;
      }
      steps.forEach((s, idx) => {
        if (idx === i) s.classList.add("active");
        else s.classList.remove("active");
      });
      i++;
    }, 450);

    const headerName = document.getElementById("headerPrinterName");
    if (headerName) headerName.textContent = "Connecting…";
  },

  async _finishConnectingSuccess(status) {
    if (this._connStepTimer) { clearInterval(this._connStepTimer); this._connStepTimer = null; }
    document.getElementById("connWaiting")?.style.setProperty("display", "none");
    const steps = document.querySelectorAll("#connProgress .conn-step");
    steps.forEach(s => {
      s.className = "conn-step done";
      this._setStepIcon(s, "check");
    });

    // Small pause so the user sees the completed animation, then show the connected card
    await new Promise(r => setTimeout(r, 450));
    this.openModal("connectModal");

    const panel = document.getElementById("connPanel");
    if (panel) panel.style.display = "none";
    const connected = document.getElementById("connConnected");
    if (connected) connected.style.display = "block";

    const dev = status.current_printer || {};
    document.getElementById("connDeviceName").textContent = dev.name || "Printer";
    document.getElementById("connDeviceMeta").textContent =
      `${(dev.connection_type || "ble").toUpperCase()} • ${(dev.protocol || "escpos").toUpperCase()} • ${dev.address || ""} • ${dev.paper_width_mm || 58}mm (${dev.printable_width_px || 384}px)`;

    const battery = document.getElementById("connDeviceBattery");
    if (status.battery_level !== null && status.battery_level !== undefined) {
      document.getElementById("connBatteryLevel").textContent = status.battery_level;
      battery.style.display = "flex";
    } else {
      battery.style.display = "none";
    }

    const infoEl = document.getElementById("connDeviceInfo");
    if (infoEl) {
      const info = status.device_info || null;
      const model = info && (info.model || (info.text ? info.text.split(" ")[0] : null));
      const firmware = info && info.firmware;
      const parts = [];
      if (model) parts.push(`Model: ${model}`);
      if (firmware) parts.push(`Firmware: ${firmware}`);
      if (info && info.raw) parts.push(`RAW: ${info.raw}`);
      if (parts.length) {
        infoEl.textContent = parts.join("  •  ");
        infoEl.style.display = "";
      } else {
        infoEl.style.display = "none";
      }
    }

    this.updatePrinterStatusUI(status);
    document.getElementById("btnConnectSelected").disabled = false;
    document.getElementById("btnScanDevices").disabled = false;
    this.showToast(`Connected to ${dev.name || "printer"}!`, "success");
    if (window.lucide) window.lucide.createIcons();
  },

  _failConnecting(message) {
    if (this._connStepTimer) { clearInterval(this._connStepTimer); this._connStepTimer = null; }
    document.getElementById("connWaiting")?.style.setProperty("display", "none");
    this.openModal("connectModal");
    const steps = document.querySelectorAll("#connProgress .conn-step");
    steps.forEach((s, idx) => {
      if (idx === steps.length - 1 || s.classList.contains("active")) {
        s.className = "conn-step fail";
        this._setStepIcon(s, "x");
      } else {
        s.className = "conn-step";
      }
    });
    document.getElementById("connErrorMsg").textContent = `Connection failed: ${message}`;
    document.getElementById("connError").style.display = "flex";
    document.getElementById("btnConnectSelected").disabled = false;
    document.getElementById("btnScanDevices").disabled = false;
    const headerName = document.getElementById("headerPrinterName");
    if (headerName) headerName.textContent = "Disconnected";
    if (window.lucide) window.lucide.createIcons();
  },

  async handleDisconnectDevice() {
    try {
      const status = await API.disconnectPrinter();
      this.updatePrinterStatusUI(status);
      this.closeModal("connectModal");
      this.showToast("Printer disconnected.", "info");
    } catch (err) {
      this.showToast(`Disconnect failed: ${err.message}`, "error");
    }
  },

  async handleRetryConnect() {
    if (!this._lastConn) return;
    const { connType, protocol, address } = this._lastConn;
    document.getElementById("connTypeSelect").value = connType;
    document.getElementById("connProtocolSelect").value = protocol;
    document.getElementById("deviceAddressInput").value = address;
    await this.handleConnectDevice();
  },

  // Save Settings Handler
  async handleSaveSettings() {
    const paperWidth = parseInt(document.getElementById("settingPaperWidthMm").value) || 58;
    const printWidth = parseInt(document.getElementById("settingPrintWidthPx").value) || 384;
    const margin = parseInt(document.getElementById("settingMarginPx").value) || 8;
    const density = parseInt(document.getElementById("settingDensity").value) || 8;
    const feedDots = parseInt(document.getElementById("settingFeedDots").value) || 0;

    const newSettings = {
      printer: {
        name: window.ActivePrinter ? window.ActivePrinter.name : "Configured Printer",
        connection_type: window.ActivePrinter ? window.ActivePrinter.connection_type : "ble",
        mac_address: window.ActivePrinter ? window.ActivePrinter.address : null,
        protocol: window.ActivePrinter ? window.ActivePrinter.protocol : "iprint",
        printable_width_px: printWidth,
        paper_width_mm: paperWidth,
        margin_px: margin,
        density: density,
        speed: 4,
        default_alignment: "center",
        auto_feed_mm: 10,
        tear_bar_feed_dots: feedDots
      },
      image: {
        default_brightness: 1.0,
        default_contrast: 1.0,
        default_dither: "floyd-steinberg",
        default_sharpen: 1.0,
        default_scaling: "fit"
      },
      app: {
        theme: document.documentElement.getAttribute("data-theme") || "dark",
        default_template: "simple_note",
        history_retention_days: 30,
        debug_mode: false
      }
    };

    try {
      window.AppSettings = await API.saveSettings(newSettings);
      this.closeModal("settingsModal");
      if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
      this.showToast("Printer settings updated successfully!", "success");
    } catch (err) {
      this.showToast(`Failed to save settings: ${err.message}`, "error");
    }
  },

  // Modal helpers
  openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add("active");
  },
  closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove("active");
  },

  // ── Keyboard shortcuts ─────────────────────────────────────
  handleKeydown(e) {
    const mod = e.ctrlKey || e.metaKey;
    if (!mod) return;
    const k = e.key.toLowerCase();
    const tag = document.activeElement ? document.activeElement.tagName : "";

    if (k === "z") {
      // Let the textarea keep its native undo
      if (tag === "TEXTAREA") return;
      e.preventDefault();
      if (e.shiftKey) window.EditorManager && window.EditorManager.redo();
      else window.EditorManager && window.EditorManager.undo();
    } else if (k === "y") {
      e.preventDefault();
      window.EditorManager && window.EditorManager.redo();
    } else if (k === "s") {
      e.preventDefault();
      this.handleSaveDocument();
    } else if (k === "p") {
      e.preventDefault();
      this.handlePrint();
    } else if (k === "d" && tag !== "INPUT" && tag !== "TEXTAREA") {
      e.preventDefault();
      window.EditorManager && window.EditorManager.duplicateActiveBlock();
    }
  },

  // ── Wi-Fi QR wizard ────────────────────────────────────────
  handleWifiQr() {
    const ssid = document.getElementById("wifiSsid").value.trim();
    const pass = document.getElementById("wifiPassword").value;
    const sec = document.getElementById("wifiSecurity").value;
    if (!ssid) { this.showToast("Enter a network name (SSID).", "error"); return; }
    const payload = `WIFI:S:${ssid};T:${sec};P:${pass};;`;
    window.EditorManager && window.EditorManager.addBlock("qr", { qr_payload: payload, qr_size: 5, align: "center" });
    this.closeModal("wifiModal");
    this.showToast(`Wi-Fi QR for '${ssid}' added.`, "success");
  },

  // ── Contact QR wizard ──────────────────────────────────────
  handleContactQr() {
    const name = document.getElementById("contactName").value.trim();
    const phone = document.getElementById("contactPhone").value.trim();
    const email = document.getElementById("contactEmail").value.trim();
    const company = document.getElementById("contactCompany").value.trim();
    if (!name && !phone && !email) { this.showToast("Enter at least a name or phone.", "error"); return; }
    const vcard = [
      "BEGIN:VCARD", "VERSION:3.0",
      name ? `FN:${name}` : "",
      company ? `ORG:${company}` : "",
      phone ? `TEL:${phone}` : "",
      email ? `EMAIL:${email}` : "",
      "END:VCARD"
    ].filter(Boolean).join("\n");
    window.EditorManager && window.EditorManager.addBlock("qr", { qr_payload: vcard, qr_size: 4, align: "center" });
    this.closeModal("contactModal");
    this.showToast(`Contact QR for '${name || phone}' added.`, "success");
  },

  // ── CSV labels ─────────────────────────────────────────────
  openCsvModal() {
    this.openModal("csvModal");
    document.getElementById("csvPreviewNote").textContent = "Load a CSV to see a preview of the first rows.";
  },

  previewCsv() {
    const input = document.getElementById("csvFileInput");
    const note = document.getElementById("csvPreviewNote");
    if (!input.files || !input.files[0]) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target.result;
      this._csvText = text;
      const lines = text.split(/\r?\n/).filter(l => l.trim());
      const head = lines.slice(0, 3).map(l => l.length > 80 ? l.slice(0, 80) + "…" : l);
      note.textContent = `Preview:\n${head.join("\n")}${lines.length > 3 ? `\n… +${lines.length - 3} more rows` : ""}`;
    };
    reader.readAsText(input.files[0]);
  },

  async handleCsvLabels() {
    if (!this._csvText) { this.showToast("Load a CSV file first.", "error"); return; }
    const payload = {
      csv_text: this._csvText,
      name_col: parseInt(document.getElementById("csvNameCol").value) || 0,
      sku_col: parseInt(document.getElementById("csvSkuCol").value) || 1,
      price_col: parseInt(document.getElementById("csvPriceCol").value) || 2,
      has_header: document.getElementById("csvHasHeader").checked,
      copies: parseInt(document.getElementById("csvCopies").value) || 1,
      title_prefix: "Label"
    };
    try {
      this.showToast("Generating barcode labels...", "info");
      const res = await API.printCsvLabels(payload);
      this.closeModal("csvModal");
      const skipMsg = res.skipped_rows && res.skipped_rows.length ? ` (skipped rows: ${res.skipped_rows.join(", ")})` : "";
      this.showToast(`${res.submitted} label job(s) queued.${skipMsg}`, res.submitted > 0 ? "success" : "error");
    } catch (err) {
      this.showToast(`CSV labels failed: ${err.message}`, "error");
    }
  },

  // ── Batch basket (added from the dashboard) ────────────────
  openBatchTab() {
    const editor = document.querySelector(".editor-panel");
    const batch = document.getElementById("batchView");
    if (editor) editor.style.display = "none";
    if (batch) batch.style.display = "flex";
    this._setNavActive("btnOpenBatch");
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
    this.renderBatchBasket();
    this.startQueuePolling();
  },

  openEditorTab() {
    const editor = document.querySelector(".editor-panel");
    const batch = document.getElementById("batchView");
    if (editor) editor.style.display = "flex";
    if (batch) batch.style.display = "none";
    this._setNavActive("btnNewPrint");
    this.stopQueuePolling();
  },

  _setNavActive(activeId) {
    document.querySelectorAll(".btn-nav").forEach(b => b.classList.remove("active"));
    const btn = document.getElementById(activeId);
    if (btn) btn.classList.add("active");
  },

  // ── Basket storage (localStorage so it survives refresh) ───
  _batchItems: [],

  loadBatchFromStorage() {
    try {
      this._batchItems = JSON.parse(localStorage.getItem("mps_batch") || "[]");
    } catch (e) {
      this._batchItems = [];
    }
    // Auto-dedupe: same title + same blocks = the same item, keep the newest
    const seen = new Map();
    this._batchItems.forEach(item => {
      const key = item.title + "|" + JSON.stringify(item.blocks);
      seen.set(key, item);
    });
    this._batchItems = Array.from(seen.values());
    this.saveBatchToStorage();
    this.updateBatchBadge();
  },

  saveBatchToStorage() {
    try {
      localStorage.setItem("mps_batch", JSON.stringify(this._batchItems));
    } catch (e) { /* storage full or unavailable */ }
    this.updateBatchBadge();
  },

  updateBatchBadge() {
    const btn = document.getElementById("btnOpenBatch");
    if (!btn) return;
    const count = this._batchItems.length;
    let label = btn.querySelector(".batch-count");
    if (count > 0) {
      if (!label) {
        label = document.createElement("span");
        label.className = "batch-count";
        btn.appendChild(label);
      }
      label.textContent = count;
    } else if (label) {
      label.remove();
    }
  },

  addToBatch(title, blocks, source = "custom") {
    if (!blocks || blocks.length === 0) {
      this.showToast("Nothing to add — the document is empty.", "error");
      return false;
    }
    // Prevent duplicate items in the basket
    const key = title + "|" + JSON.stringify(blocks);
    if (this._batchItems.some(b => b.title + "|" + JSON.stringify(b.blocks) === key)) {
      this.showToast(`'${title}' is already in the batch.`, "info");
      return false;
    }
    this._batchItems.push({
      id: "batch_" + Date.now() + "_" + Math.random().toString(36).substr(2, 6),
      title: title || "Untitled",
      blocks: JSON.parse(JSON.stringify(blocks)),
      source,
      added_at: new Date().toLocaleTimeString()
    });
    this.saveBatchToStorage();
    this.renderBatchBasket();
    this.showToast(`'${title}' added to the batch (${this._batchItems.length} item${this._batchItems.length > 1 ? "s" : ""}).`, "success");
    return true;
  },

  handleAddToBatch() {
    if (!window.EditorManager) return;
    const doc = window.EditorManager.getDocumentData();
    if (!doc.blocks || doc.blocks.length === 0) {
      this.showToast("Cannot add an empty document to the batch.", "error");
      return;
    }
    this.addToBatch(doc.title, doc.blocks, "custom");
  },

  removeFromBatch(id) {
    this._batchItems = this._batchItems.filter(b => b.id !== id);
    this.saveBatchToStorage();
    this.renderBatchBasket();
  },

  clearBatch() {
    if (this._batchItems.length === 0) return;
    this._batchItems = [];
    this.saveBatchToStorage();
    this.renderBatchBasket();
    this.showToast("Batch basket cleared.", "info");
  },

  editBatchItem(item) {
    if (window.EditorManager) {
      window.EditorManager.loadTemplate(item.blocks, item.title);
      this.openEditorTab();
      this.showToast(`'${item.title}' loaded — customize, then Add to Batch or Print.`, "info");
    }
  },

  renderBatchBasket() {
    const list = document.getElementById("batchTemplateList");
    if (!list) return;
    list.innerHTML = "";

    if (this._batchItems.length === 0) {
      list.innerHTML = '<div style="color: var(--text-muted); padding: 24px; text-align: center; line-height: 1.7;">Batch basket is empty.<br><span style="font-size: 12px;">In the editor, click <b>Add to Batch</b> — or use the <b>+ Batch</b> button on any template or saved document.</span></div>';
    }

    this._batchItems.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "batch-item";
      const sourceLabel = item.source === "template" ? "Template" : item.source === "document" ? "Document" : "Custom";
      row.innerHTML = `
        <span class="batch-num">${String(index + 1).padStart(2, "0")}</span>
        <span class="batch-name">${this.escapeHtml(item.title)}</span>
        <span class="status-badge" style="font-size: 0.68rem;">${sourceLabel}</span>
        <span class="history-meta">${item.blocks.length} block(s) · added ${this.escapeHtml(item.added_at || "")}</span>
        <button class="btn-icon batch-edit-btn" title="Edit before printing"><i data-lucide="pencil"></i></button>
        <button class="btn-icon delete" title="Remove from batch"><i data-lucide="trash-2"></i></button>
      `;
      row.querySelector(".batch-edit-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        this.editBatchItem(item);
      });
      row.querySelector(".delete").addEventListener("click", (e) => {
        e.stopPropagation();
        this.removeFromBatch(item.id);
      });
      list.appendChild(row);
    });

    const countEl = document.getElementById("batchSelectedCount");
    if (countEl) countEl.textContent = `${this._batchItems.length} item${this._batchItems.length === 1 ? "" : "s"}`;
    const sendBtn = document.getElementById("btnSendBatchQueue");
    if (sendBtn) sendBtn.disabled = this._batchItems.length === 0;
    this.updateBatchTotal();
    if (window.lucide) window.lucide.createIcons();
  },

  updateBatchTotal() {
    const el = document.getElementById("batchTotalPrints");
    if (!el) return;
    const copiesInput = document.getElementById("batchCopies");
    const copies = copiesInput ? Math.max(1, parseInt(copiesInput.value) || 1) : 1;
    const items = this._batchItems.length;
    if (items === 0) { el.textContent = ""; return; }
    el.textContent = `${items} × ${copies} = ${items * copies} prints`;
  },

  async sendBatchToQueue() {
    if (this._batchSending) return; // guard against double-fire
    if (this._batchItems.length === 0) { this.showToast("Batch basket is empty — add items first.", "error"); return; }
    this._batchSending = true;
    const sendBtn = document.getElementById("btnSendBatchQueue");
    if (sendBtn) { sendBtn.disabled = true; }

    const copiesInput = document.getElementById("batchCopies");
    const copies = copiesInput ? Math.max(1, parseInt(copiesInput.value) || 1) : 1;

    try {
      this._batchJobs = [];
      for (const item of this._batchItems) {
        const job = await API.submitPrintJob({ title: item.title, blocks: item.blocks, copies });
        this._batchJobs.push(job);
      }
      this.showToast(`${this._batchJobs.length} job(s) sent to the queue${copies > 1 ? ` (×${copies} copies)` : ""}.`, "success");
      this.pollQueue();
    } catch (err) {
      this.showToast(`Batch failed: ${err.message}`, "error");
    } finally {
      this._batchSending = false;
      if (sendBtn) sendBtn.disabled = this._batchItems.length === 0;
    }
  },

  startQueuePolling() {
    if (this._queuePollTimer) return;
    this.pollQueue();
    this._queuePollTimer = setInterval(() => this.pollQueue(), 2000);
  },

  stopQueuePolling() {
    if (this._queuePollTimer) {
      clearInterval(this._queuePollTimer);
      this._queuePollTimer = null;
    }
  },

  async pollQueue() {
    try {
      const q = await API.getPrintQueue();
      const badge = document.getElementById("batchQueueBadge");
      if (badge) badge.textContent = `QUEUE: ${q.queue_length ?? 0}`;

      const statusEl = document.getElementById("batchQueueStatus");
      if (!statusEl) return;
      const parts = [];
      if (q.active_job) {
        parts.push(`<div class="queue-row active"><span class="queue-dot"></span><b>${this.escapeHtml(q.active_job.title)}</b><span class="status-badge">${this.escapeHtml(q.active_job.status)}</span></div>`);
      }
      (q.queued || []).forEach(j => {
        parts.push(`<div class="queue-row"><span class="queue-dot idle"></span><span>${this.escapeHtml(j.title)}</span><span class="status-badge">${this.escapeHtml(j.status)}</span></div>`);
      });
      if (!q.active_job && (!q.queued || q.queued.length === 0)) {
        parts.push('<div style="color: var(--text-muted); font-size: 12px; padding: 6px 0;">Queue is idle — send your batch to start printing.</div>');
      }
      statusEl.innerHTML = parts.join("");

      if (this._batchJobs && this._batchJobs.length) {
        let done = 0;
        for (const job of this._batchJobs) {
          try {
            const rec = await API.getPrintJobStatus(job.id);
            job.status = rec.status;
            if (["completed", "failed", "cancelled"].includes(rec.status)) done++;
          } catch (e) { /* job may have left the records */ }
        }
        if (this._batchJobs.length && done === this._batchJobs.length) {
          this.showToast(`Batch complete: ${done}/${this._batchJobs.length} jobs finished.`, "success");
          this._batchJobs = [];
        }
      }
    } catch (err) {
      // server unreachable or transient — ignore, next poll retries
    }
  },

  // ── Clipboard import ───────────────────────────────────────
  handleClipboardImport() {
    const text = document.getElementById("clipboardText").value;
    const lines = text.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
    if (lines.length === 0) { this.showToast("Nothing to import.", "error"); return; }
    if (window.EditorManager) {
      lines.forEach(line => window.EditorManager.addBlock("text", { content: line, font_size: "normal" }));
      this.closeModal("clipboardModal");
      this.showToast(`Imported ${lines.length} line(s) as text blocks.`, "success");
    }
  },

  // ── Image crop tool ────────────────────────────────────────
  openCropModal(blockId) {
    const block = window.EditorManager && window.EditorManager.blocks.find(b => b.id === blockId);
    if (!block || !block.image_data) return;
    this._cropBlockId = blockId;
    this._cropOriginal = block.image_data;
    const img = document.getElementById("cropImage");
    img.src = block.image_data;
    this._bindCropMouse();
    img.onload = () => {
      this._cropNatural = { w: img.naturalWidth, h: img.naturalHeight };
      this.initCropSelection();
    };
    this.openModal("cropModal");
  },

  initCropSelection() {
    const wrap = document.getElementById("cropCanvasWrap");
    const sel = document.getElementById("cropSelection");
    if (!wrap || !sel) return;
    const r = wrap.getBoundingClientRect();
    this._cropRect = { x: r.width * 0.1, y: r.height * 0.1, w: r.width * 0.8, h: r.height * 0.8 };
    this._renderCropSelection();
  },

  _renderCropSelection() {
    const sel = document.getElementById("cropSelection");
    if (!sel || !this._cropRect) return;
    sel.style.left = `${this._cropRect.x}px`;
    sel.style.top = `${this._cropRect.y}px`;
    sel.style.width = `${this._cropRect.w}px`;
    sel.style.height = `${this._cropRect.h}px`;
  },

  _bindCropMouse() {
    const wrap = document.getElementById("cropCanvasWrap");
    if (!wrap || wrap.dataset.bound) return;
    wrap.dataset.bound = "1";
    let start = null;
    let rect = null;

    wrap.addEventListener("mousedown", (e) => {
      if (e.target.id === "cropSelection") return;
      const r = wrap.getBoundingClientRect();
      start = { x: e.clientX - r.left, y: e.clientY - r.top };
      rect = { x: start.x, y: start.y, w: 0, h: 0 };
      this._cropRect = rect;
      this._renderCropSelection();
    });

    wrap.addEventListener("mousemove", (e) => {
      if (!start) return;
      const r = wrap.getBoundingClientRect();
      const cx = Math.min(Math.max(e.clientX - r.left, 0), r.width);
      const cy = Math.min(Math.max(e.clientY - r.top, 0), r.height);
      rect.x = Math.min(start.x, cx);
      rect.y = Math.min(start.y, cy);
      rect.w = Math.abs(cx - start.x);
      rect.h = Math.abs(cy - start.y);
      this._renderCropSelection();
    });

    wrap.addEventListener("mouseup", () => {
      start = null;
      if (rect && rect.w < 10 && rect.h < 10) this.initCropSelection();
    });
  },

  applyCrop() {
    const img = document.getElementById("cropImage");
    const wrap = document.getElementById("cropCanvasWrap");
    if (!this._cropRect || !img.naturalWidth) return;
    const wr = wrap.getBoundingClientRect();
    const scaleX = img.naturalWidth / wr.width;
    const scaleY = img.naturalHeight / wr.height;
    const sx = Math.round(this._cropRect.x * scaleX);
    const sy = Math.round(this._cropRect.y * scaleY);
    const sw = Math.round(this._cropRect.w * scaleX);
    const sh = Math.round(this._cropRect.h * scaleY);

    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, sw);
    canvas.height = Math.max(1, sh);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
    const cropped = canvas.toDataURL("image/png");

    if (window.EditorManager) {
      window.EditorManager.updateBlock(this._cropBlockId, "image_data", cropped);
    }
    this.closeModal("cropModal");
    this.showToast("Image cropped.", "success");
  },

  // ── Template favorites ─────────────────────────────────────
  async toggleTemplateFavorite(templateId, favorite) {
    try {
      const res = await API.setTemplateFavorite(templateId, favorite);
      if (window.AppSettings) {
        window.AppSettings.app.favorite_templates = res.favorite_templates || [];
      }
      return res.favorite;
    } catch (err) {
      this.showToast(`Favorite failed: ${err.message}`, "error");
      return null;
    }
  },

  isFavoriteTemplate(templateId) {
    const favs = window.AppSettings && window.AppSettings.app && window.AppSettings.app.favorite_templates;
    return Array.isArray(favs) && favs.includes(templateId);
  },

  // Toast Notification System
  escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  },

  showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    let iconName = "info";
    if (type === "success") iconName = "check-circle";
    if (type === "error") iconName = "alert-circle";

    toast.innerHTML = `<i data-lucide="${iconName}"></i> <span>${message}</span>`;
    container.appendChild(toast);
    if (window.lucide) window.lucide.createIcons();

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.App.init();
});
