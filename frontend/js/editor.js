/**
 * Mini Print Studio — Block-Based Print Editor
 */
window.EditorManager = {
  canvas: null,
  docTitleInput: null,
  blocks: [],
  undoStack: [],
  redoStack: [],
  lastActiveBlockId: null,

  init() {
    this.canvas = document.getElementById("blocksCanvas");
    this.docTitleInput = document.getElementById("docTitleInput");

    // Add button listeners
    document.getElementById("btnAddText")?.addEventListener("click", () => this.addBlock("text"));
    document.getElementById("btnAddImage")?.addEventListener("click", () => this.addBlock("image"));
    document.getElementById("btnAddQr")?.addEventListener("click", () => this.addBlock("qr"));
    document.getElementById("btnAddBarcode")?.addEventListener("click", () => this.addBlock("barcode"));
    document.getElementById("btnAddLine")?.addEventListener("click", () => this.addBlock("line"));
    document.getElementById("btnAddSpace")?.addEventListener("click", () => this.addBlock("space"));

    if (this.docTitleInput) {
      this.docTitleInput.addEventListener("input", () => {
        if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
      });
    }

    // Track the last focused block for duplicate/delete shortcuts
    this.canvas?.addEventListener("click", (e) => {
      const card = e.target.closest(".block-card");
      if (card) this.lastActiveBlockId = card.dataset.id;
    });
    this.canvas?.addEventListener("focusin", (e) => {
      const card = e.target.closest(".block-card");
      if (card) this.lastActiveBlockId = card.dataset.id;
    });

    this.initDragDrop();

    // Load default starter block
    this.addBlock("text", {
      content: "MINI PRINT STUDIO",
      font_size: "title",
      bold: true,
      align: "center",
      invert: true
    });
    this.addBlock("line", { line_style: "solid" });
    this.addBlock("text", {
      content: "Welcome to your local thermal printing workspace! Control text, images, QR codes, and labels directly.",
      font_size: "normal",
      align: "left"
    });
    this.addBlock("space", { space_height: 16 });
    this.undoStack = [];
    this.redoStack = [];
  },

  // ── Undo / Redo ────────────────────────────────────────────
  _pushUndo() {
    const snapshot = JSON.stringify(this.blocks);
    if (this.undoStack[this.undoStack.length - 1] === snapshot) return;
    this.undoStack.push(snapshot);
    if (this.undoStack.length > 50) this.undoStack.shift();
    this.redoStack = [];
    this._updateUndoButtons();
  },

  undo() {
    if (!this.undoStack.length) return;
    this.redoStack.push(JSON.stringify(this.blocks));
    this.blocks = JSON.parse(this.undoStack.pop());
    this.render();
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
    this._updateUndoButtons();
  },

  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(JSON.stringify(this.blocks));
    this.blocks = JSON.parse(this.redoStack.pop());
    this.render();
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
    this._updateUndoButtons();
  },

  _updateUndoButtons() {
    const btnU = document.getElementById("btnUndo");
    const btnR = document.getElementById("btnRedo");
    if (btnU) { btnU.disabled = this.undoStack.length === 0; btnU.style.opacity = this.undoStack.length === 0 ? 0.4 : 1; }
    if (btnR) { btnR.disabled = this.redoStack.length === 0; btnR.style.opacity = this.redoStack.length === 0 ? 0.4 : 1; }
  },

  duplicateActiveBlock() {
    const id = this.lastActiveBlockId;
    if (!id) return;
    const idx = this.blocks.findIndex(b => b.id === id);
    if (idx === -1) return;
    const copy = JSON.parse(JSON.stringify(this.blocks[idx]));
    copy.id = "block_" + Math.random().toString(36).substr(2, 9);
    this._pushUndo();
    this.blocks.splice(idx + 1, 0, copy);
    this.lastActiveBlockId = copy.id;
    this.render();
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
  },

  // ── Drag & drop reorder ────────────────────────────────────
  initDragDrop() {
    if (!this.canvas) return;
    this.canvas.addEventListener("dragstart", (e) => {
      const card = e.target.closest(".block-card");
      if (!card) return;
      if (e.target.closest("input, select, textarea, button, label")) {
        e.preventDefault();
        return;
      }
      this._dragId = card.dataset.id;
      e.dataTransfer.setData("text/plain", card.dataset.id);
      e.dataTransfer.effectAllowed = "move";
      card.classList.add("dragging");
    });
    this.canvas.addEventListener("dragover", (e) => {
      const card = e.target.closest(".block-card");
      if (!card) return;
      e.preventDefault();
      card.classList.add("drag-over");
    });
    this.canvas.addEventListener("dragleave", (e) => {
      const card = e.target.closest(".block-card");
      if (card) card.classList.remove("drag-over");
    });
    this.canvas.addEventListener("drop", (e) => {
      const card = e.target.closest(".block-card");
      if (!card) return;
      e.preventDefault();
      const srcId = this._dragId;
      const tgtId = card.dataset.id;
      this.canvas.querySelectorAll(".drag-over").forEach(c => c.classList.remove("drag-over"));
      if (!srcId || srcId === tgtId) return;
      const srcIdx = this.blocks.findIndex(b => b.id === srcId);
      const tgtIdx = this.blocks.findIndex(b => b.id === tgtId);
      if (srcIdx === -1 || tgtIdx === -1) return;
      this._pushUndo();
      const [moved] = this.blocks.splice(srcIdx, 1);
      this.blocks.splice(tgtIdx, 0, moved);
      this.render();
      if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
    });
    this.canvas.addEventListener("dragend", () => {
      this.canvas.querySelectorAll(".dragging, .drag-over").forEach(c => c.classList.remove("dragging", "drag-over"));
      this._dragId = null;
    });
  },

  addBlock(type, initialValues = {}) {
    const block = this._buildBlock(type, initialValues);
    this._pushUndo();
    this.blocks.push(block);
    this.render();
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
  },

  _buildBlock(type, initialValues = {}) {
    const id = "block_" + Math.random().toString(36).substr(2, 9);
    let block = { id, type };

    if (type === "text") {
      block = {
        ...block,
        content: initialValues.content || "",
        font_size: initialValues.font_size || "normal",
        custom_font_size: initialValues.custom_font_size || null,
        font_family: initialValues.font_family || "arial",
        line_spacing: initialValues.line_spacing || 1.3,
        letter_spacing: initialValues.letter_spacing || 0,
        bold: initialValues.bold || false,
        italic: initialValues.italic || false,
        monospace: initialValues.monospace || false,
        align: initialValues.align || "left",
        invert: initialValues.invert || false,
        underline: initialValues.underline || false
      };
    } else if (type === "image") {
      block = {
        ...block,
        image_data: initialValues.image_data || null,
        // null = follow the global toolbar dither selection; templates may
        // set an explicit mode that must be respected instead.
        dither_mode: initialValues.dither_mode || null,
        brightness: initialValues.brightness || 1.0,
        contrast: initialValues.contrast || 1.0,
        sharpen: initialValues.sharpen || 1.0,
        align: initialValues.align || "center",
        invert: initialValues.invert || false
      };
    } else if (type === "qr") {
      block = {
        ...block,
        qr_payload: initialValues.qr_payload || "https://github.com",
        qr_size: initialValues.qr_size || 4,
        qr_ecc: initialValues.qr_ecc || "M",
        align: initialValues.align || "center"
      };
    } else if (type === "barcode") {
      block = {
        ...block,
        barcode_payload: initialValues.barcode_payload || "123456789012",
        barcode_type: initialValues.barcode_type || "code128",
        barcode_height: initialValues.barcode_height || 45,
        show_barcode_text: initialValues.show_barcode_text !== undefined ? initialValues.show_barcode_text : true,
        align: initialValues.align || "center"
      };
    } else if (type === "line") {
      block = {
        ...block,
        line_style: initialValues.line_style || "solid"
      };
    } else if (type === "space") {
      block = {
        ...block,
        space_height: initialValues.space_height || 16
      };
    } else if (type === "table") {
      block = {
        ...block,
        table_headers: initialValues.table_headers || [],
        table_rows: initialValues.table_rows || [["Item 1", "1", "$0.00"]],
        table_col_widths: initialValues.table_col_widths || null
      };
    } else if (type === "totals") {
      block = {
        ...block,
        totals_lines: initialValues.totals_lines || [
          { label: "Subtotal", value: "", dotted: true, bold: false },
          { label: "TOTAL", value: "", dotted: true, bold: true }
        ]
      };
    }

    return block;
  },

  removeBlock(id) {
    this._pushUndo();
    this.blocks = this.blocks.filter(b => b.id !== id);
    this.render();
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
  },

  moveBlock(id, direction) {
    const idx = this.blocks.findIndex(b => b.id === id);
    if (idx === -1) return;
    const targetIdx = idx + direction;
    if (targetIdx < 0 || targetIdx >= this.blocks.length) return;

    this._pushUndo();
    const temp = this.blocks[idx];
    this.blocks[idx] = this.blocks[targetIdx];
    this.blocks[targetIdx] = temp;

    this.render();
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
  },

  loadTemplate(blocks, title = "Template Note") {
    this._pushUndo();
    this.blocks = blocks.map(b => this._buildBlock(b.type, b));
    if (this.docTitleInput) this.docTitleInput.value = title;
    this.render();
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
  },

  getPrintRequest() {
    const title = this.docTitleInput ? this.docTitleInput.value : "Untitled Print Job";
    // Strip frontend ID
    const cleanBlocks = this.blocks.map(b => {
      const { id, ...rest } = b;
      return rest;
    });

    // Apply the preview toolbar dither selection to image blocks that do not
    // have their own explicit mode (e.g. set by a template), so preview,
    // print, and export all use the chosen mode consistently.
    const ditherSelect = document.getElementById("ditherSelect");
    if (ditherSelect) {
      const selectedDither = ditherSelect.value || "atkinson";
      cleanBlocks.forEach(b => {
        if (b.type === "image" && !b.dither_mode) b.dither_mode = selectedDither;
      });
    }

    let widthPx = 384;
    if (window.ActivePrinter && window.ActivePrinter.printable_width_px) {
      widthPx = window.ActivePrinter.printable_width_px;
    } else if (window.AppSettings && window.AppSettings.printer) {
      widthPx = window.AppSettings.printer.printable_width_px;
    }

    let marginPx = 8;
    if (window.AppSettings && window.AppSettings.printer) {
      marginPx = window.AppSettings.printer.margin_px;
    }

    const copiesInput = document.getElementById("copiesInput");
    const copies = copiesInput ? Math.max(1, parseInt(copiesInput.value) || 1) : 1;

    return {
      title,
      blocks: cleanBlocks,
      width_px: widthPx,
      margin_px: marginPx,
      feed_lines: 3,
      cut_paper: false,
      copies
    };
  },

  getDocumentData() {
    const title = this.docTitleInput ? this.docTitleInput.value : "Untitled Print Job";
    const cleanBlocks = this.blocks.map(b => {
      const { id, ...rest } = b;
      return rest;
    });
    return { title, blocks: cleanBlocks };
  },

  render() {
    if (!this.canvas) return;
    this.canvas.innerHTML = "";

    if (this.blocks.length === 0) {
      this.canvas.innerHTML = `
        <div class="empty-canvas-notice">
          <i data-lucide="file-text" style="width: 48px; height: 48px; stroke-width: 1.5;"></i>
          <p>Your print layout is empty.</p>
          <p style="font-size: 0.85rem;">Click the buttons above or select a template to add content blocks.</p>
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    this.blocks.forEach((block, index) => {
      const card = document.createElement("div");
      card.className = "block-card";
      card.dataset.id = block.id;

      let typeIcon = "file-text";
      if (block.type === "image") typeIcon = "image";
      else if (block.type === "qr") typeIcon = "qr-code";
      else if (block.type === "barcode") typeIcon = "barcode";
      else if (block.type === "line") typeIcon = "minus";
      else if (block.type === "space") typeIcon = "move-vertical";
      else if (block.type === "table") typeIcon = "table-2";
      else if (block.type === "totals") typeIcon = "receipt";

      // Card Header
      const headerHTML = `
        <div class="block-card-header">
          <div class="block-type-badge">
            <i data-lucide="${typeIcon}"></i> ${block.type.toUpperCase()} BLOCK
          </div>
          <div class="block-actions">
            <button class="btn-icon" onclick="EditorManager.moveBlock('${block.id}', -1)" title="Move Up" ${index === 0 ? 'disabled style="opacity:0.3"' : ''}>
              <i data-lucide="chevron-up"></i>
            </button>
            <button class="btn-icon" onclick="EditorManager.moveBlock('${block.id}', 1)" title="Move Down" ${index === this.blocks.length - 1 ? 'disabled style="opacity:0.3"' : ''}>
              <i data-lucide="chevron-down"></i>
            </button>
            <button class="btn-icon delete" onclick="EditorManager.removeBlock('${block.id}')" title="Delete Block">
              <i data-lucide="trash-2"></i>
            </button>
          </div>
        </div>
      `;

      let bodyHTML = "";

      // Text Controls
      if (block.type === "text") {
        bodyHTML = `
          <div class="form-group">
            <label>Text Content:</label>
            <textarea class="form-control" placeholder="Type text here..." oninput="EditorManager.updateBlock('${block.id}', 'content', this.value)">${block.content || ''}</textarea>
          </div>
          <div class="controls-grid">
            <div class="form-group">
              <label>Font Size:</label>
              <select class="form-control" onchange="EditorManager.updateBlock('${block.id}', 'font_size', this.value)">
                <option value="small" ${block.font_size === 'small' ? 'selected' : ''}>Small (Font B)</option>
                <option value="normal" ${block.font_size === 'normal' ? 'selected' : ''}>Normal (Font A)</option>
                <option value="large" ${block.font_size === 'large' ? 'selected' : ''}>Large (2x)</option>
                <option value="title" ${block.font_size === 'title' ? 'selected' : ''}>Title (3x)</option>
              </select>
            </div>
            <div class="form-group">
              <label>Custom Size (px):</label>
              <input type="number" class="form-control" min="6" max="72" value="${block.custom_font_size || ''}" placeholder="auto" onchange="EditorManager.updateBlock('${block.id}', 'custom_font_size', this.value ? parseInt(this.value) : null)">
            </div>
            <div class="form-group">
              <label>Font:</label>
              <select class="form-control" onchange="EditorManager.updateBlock('${block.id}', 'font_family', this.value)">
                <option value="arial" ${(block.font_family || 'arial') === 'arial' ? 'selected' : ''}>Arial</option>
                <option value="courier" ${(block.font_family || '') === 'courier' ? 'selected' : ''}>Courier New</option>
                <option value="times" ${(block.font_family || '') === 'times' ? 'selected' : ''}>Times New Roman</option>
                <option value="tahoma" ${(block.font_family || '') === 'tahoma' ? 'selected' : ''}>Tahoma</option>
                <option value="verdana" ${(block.font_family || '') === 'verdana' ? 'selected' : ''}>Verdana</option>
                <option value="georgia" ${(block.font_family || '') === 'georgia' ? 'selected' : ''}>Georgia</option>
                <option value="comic" ${(block.font_family || '') === 'comic' ? 'selected' : ''}>Comic Sans MS</option>
                <option value="impact" ${(block.font_family || '') === 'impact' ? 'selected' : ''}>Impact</option>
                <option value="consolas" ${(block.font_family || '') === 'consolas' ? 'selected' : ''}>Consolas</option>
                <option value="calibri" ${(block.font_family || '') === 'calibri' ? 'selected' : ''}>Calibri</option>
              </select>
            </div>
            <div class="form-group">
              <label>Alignment:</label>
              <select class="form-control" onchange="EditorManager.updateBlock('${block.id}', 'align', this.value)">
                <option value="left" ${block.align === 'left' ? 'selected' : ''}>Left</option>
                <option value="center" ${block.align === 'center' ? 'selected' : ''}>Center</option>
                <option value="right" ${block.align === 'right' ? 'selected' : ''}>Right</option>
              </select>
            </div>
            <div class="form-group">
              <label>Line Spacing: <span class="range-readout" id="readout-${block.id}-line_spacing">${block.line_spacing || 1.3}</span></label>
              <input type="range" min="0.8" max="2.0" step="0.05" value="${block.line_spacing || 1.3}" oninput="EditorManager.updateBlock('${block.id}', 'line_spacing', parseFloat(this.value))">
            </div>
            <div class="form-group">
              <label>Letter Spacing: <span class="range-readout" id="readout-${block.id}-letter_spacing">${block.letter_spacing || 0}</span> px</label>
              <input type="range" min="0" max="8" step="1" value="${block.letter_spacing || 0}" oninput="EditorManager.updateBlock('${block.id}', 'letter_spacing', parseInt(this.value))">
            </div>
          </div>
          <div class="toggle-group">
            <label class="toggle-checkbox"><input type="checkbox" ${block.bold ? 'checked' : ''} onchange="EditorManager.updateBlock('${block.id}', 'bold', this.checked)"> Bold</label>
            <label class="toggle-checkbox"><input type="checkbox" ${block.italic ? 'checked' : ''} onchange="EditorManager.updateBlock('${block.id}', 'italic', this.checked)"> Italic</label>
            <label class="toggle-checkbox"><input type="checkbox" ${block.monospace ? 'checked' : ''} onchange="EditorManager.updateBlock('${block.id}', 'monospace', this.checked)"> Monospace</label>
            <label class="toggle-checkbox"><input type="checkbox" ${block.invert ? 'checked' : ''} onchange="EditorManager.updateBlock('${block.id}', 'invert', this.checked)"> Invert (W/B)</label>
            <label class="toggle-checkbox"><input type="checkbox" ${block.underline ? 'checked' : ''} onchange="EditorManager.updateBlock('${block.id}', 'underline', this.checked)"> Underline</label>
          </div>
        `;
      }
      // Image Controls
      else if (block.type === "image") {
        bodyHTML = `
          <div class="form-group">
            <label>Upload Image (PNG, JPG, WEBP):</label>
            <div style="display: flex; gap: 8px; align-items: center;">
              <input type="file" class="form-control" accept="image/*" onchange="EditorManager.handleImageUpload('${block.id}', this)">
              ${block.image_data ? `<button class="btn-secondary small" style="white-space: nowrap;" onclick="window.App.openCropModal('${block.id}')"><i data-lucide="crop" style="width: 13px; height: 13px;"></i> Crop</button>` : ''}
            </div>
          </div>
          ${block.image_data ? `<img src="${block.image_data}" style="max-height: 100px; object-fit: contain; margin: 6px 0; border-radius: 4px; border: 1px solid var(--border-color);">` : ''}
          <div class="controls-grid">
            <div class="form-group">
              <label>Brightness: <span class="range-readout" id="readout-${block.id}-brightness">${block.brightness}</span></label>
              <input type="range" min="0.5" max="2.0" step="0.1" value="${block.brightness}" oninput="EditorManager.updateBlock('${block.id}', 'brightness', parseFloat(this.value))">
            </div>
            <div class="form-group">
              <label>Contrast: <span class="range-readout" id="readout-${block.id}-contrast">${block.contrast}</span></label>
              <input type="range" min="0.5" max="2.0" step="0.1" value="${block.contrast}" oninput="EditorManager.updateBlock('${block.id}', 'contrast', parseFloat(this.value))">
            </div>
            <div class="form-group">
              <label>Sharpen: <span class="range-readout" id="readout-${block.id}-sharpen">${block.sharpen}</span></label>
              <input type="range" min="1.0" max="3.0" step="0.2" value="${block.sharpen}" oninput="EditorManager.updateBlock('${block.id}', 'sharpen', parseFloat(this.value))">
            </div>
          </div>
          <div class="toggle-group">
            <label class="toggle-checkbox"><input type="checkbox" ${block.invert ? 'checked' : ''} onchange="EditorManager.updateBlock('${block.id}', 'invert', this.checked)"> Invert Colors</label>
          </div>
        `;
      }
      // QR Code Controls
      else if (block.type === "qr") {
        bodyHTML = `
          <div class="form-group">
            <label>QR Code Data Payload:</label>
            <input type="text" class="form-control" value="${block.qr_payload || ''}" placeholder="URL, Wi-Fi info, or text..." oninput="EditorManager.updateBlock('${block.id}', 'qr_payload', this.value)">
          </div>
          <div class="controls-grid">
            <div class="form-group">
              <label>Size Multiplier:</label>
              <input type="number" class="form-control" min="1" max="10" value="${block.qr_size}" onchange="EditorManager.updateBlock('${block.id}', 'qr_size', parseInt(this.value))">
            </div>
            <div class="form-group">
              <label>Error Correction:</label>
              <select class="form-control" onchange="EditorManager.updateBlock('${block.id}', 'qr_ecc', this.value)">
                <option value="L" ${block.qr_ecc === 'L' ? 'selected' : ''}>Low (7%)</option>
                <option value="M" ${block.qr_ecc === 'M' ? 'selected' : ''}>Medium (15%)</option>
                <option value="Q" ${block.qr_ecc === 'Q' ? 'selected' : ''}>Quality (25%)</option>
                <option value="H" ${block.qr_ecc === 'H' ? 'selected' : ''}>High (30%)</option>
              </select>
            </div>
          </div>
        `;
      }
      // Barcode Controls
      else if (block.type === "barcode") {
        bodyHTML = `
          <div class="form-group">
            <label>Barcode Text Payload:</label>
            <input type="text" class="form-control" value="${block.barcode_payload || ''}" placeholder="Serial, SKU, code..." oninput="EditorManager.updateBlock('${block.id}', 'barcode_payload', this.value)">
          </div>
          <div class="controls-grid">
            <div class="form-group">
              <label>Barcode Type:</label>
              <select class="form-control" onchange="EditorManager.updateBlock('${block.id}', 'barcode_type', this.value)">
                <option value="code128" ${block.barcode_type === 'code128' ? 'selected' : ''}>CODE 128</option>
                <option value="ean13" ${block.barcode_type === 'ean13' ? 'selected' : ''}>EAN 13</option>
                <option value="ean8" ${block.barcode_type === 'ean8' ? 'selected' : ''}>EAN 8</option>
                <option value="upca" ${block.barcode_type === 'upca' ? 'selected' : ''}>UPC-A</option>
              </select>
            </div>
            <div class="form-group">
              <label>Height (px):</label>
              <input type="number" class="form-control" min="20" max="100" value="${block.barcode_height}" onchange="EditorManager.updateBlock('${block.id}', 'barcode_height', parseInt(this.value))">
            </div>
          </div>
        `;
      }
      // Line Divider Controls
      else if (block.type === "line") {
        bodyHTML = `
          <div class="form-group">
            <label>Line Style:</label>
            <select class="form-control" onchange="EditorManager.updateBlock('${block.id}', 'line_style', this.value)">
              <option value="solid" ${block.line_style === 'solid' ? 'selected' : ''}>Solid Line (───────)</option>
              <option value="dashed" ${block.line_style === 'dashed' ? 'selected' : ''}>Dashed Line ( - - - - )</option>
              <option value="dotted" ${block.line_style === 'dotted' ? 'selected' : ''}>Dotted Line ( . . . . )</option>
              <option value="double" ${block.line_style === 'double' ? 'selected' : ''}>Double Line (═══════)</option>
            </select>
          </div>
        `;
      }
      // Spacer Controls
      else if (block.type === "space") {
        bodyHTML = `
          <div class="form-group">
            <label>Spacer Height: <span class="range-readout" id="readout-${block.id}-space_height">${block.space_height}</span> px</label>
            <input type="range" class="form-control" min="4" max="100" step="4" value="${block.space_height}" oninput="EditorManager.updateBlock('${block.id}', 'space_height', parseInt(this.value))">
          </div>
        `;
      }
      // Table Controls (receipt / label designer)
      else if (block.type === "table") {
        const headersText = (block.table_headers || []).join(", ");
        const rowsText = (block.table_rows || []).map(r => (r || []).join(", ")).join("\n");
        const widthsText = (block.table_col_widths || []).join(", ");
        bodyHTML = `
          <div class="settings-note">Each line = one row. Cells separated by commas. Prefix a line with <b>!</b> for a separator row.</div>
          <div class="form-group">
            <label>Headers (comma separated, optional):</label>
            <input type="text" class="form-control table-headers-input" value="${this.escapeHtml(headersText)}" placeholder="Item, Qty, Price" oninput="EditorManager.updateTableBlockFromInputs('${block.id}')">
          </div>
          <div class="form-group">
            <label>Rows (one per line):</label>
            <textarea class="form-control table-rows-input" rows="4" placeholder="Widget, 2, $4.50&#10;Gadget, 1, $9.99" oninput="EditorManager.updateTableBlockFromInputs('${block.id}')">${this.escapeHtml(rowsText)}</textarea>
          </div>
          <div class="form-group">
            <label>Column Widths (px, comma separated, optional):</label>
            <input type="text" class="form-control table-widths-input" value="${this.escapeHtml(widthsText)}" placeholder="120, 60, 180" oninput="EditorManager.updateTableBlockFromInputs('${block.id}')">
          </div>
        `;
      }
      // Totals Controls
      else if (block.type === "totals") {
        const linesText = (block.totals_lines || [])
          .map(l => (l.bold ? "*" : "") + (l.label || "") + " | " + (l.value || ""))
          .join("\n");
        bodyHTML = `
          <div class="settings-note">One line per row: <b>Label | Value</b>. Prefix a line with <b>*</b> to emphasize (TOTAL).</div>
          <div class="form-group">
            <label>Total Lines:</label>
            <textarea class="form-control" rows="4" placeholder="Subtotal | $14.49&#10;*TOTAL | $14.49" oninput="EditorManager.updateTotalsBlock('${block.id}', this.value)">${this.escapeHtml(linesText)}</textarea>
          </div>
        `;
      }

      card.innerHTML = headerHTML + bodyHTML;
      this.canvas.appendChild(card);
    });

    if (window.lucide) window.lucide.createIcons();
  },

  updateBlock(id, key, value) {
    const block = this.blocks.find(b => b.id === id);
    if (block) {
      if (block[key] === value) return;
      this._pushUndo();
      block[key] = value;
      // Update the live readout in place so the slider the user is dragging
      // is never destroyed/recreated mid-drag.
      const rangeKeys = ["brightness", "contrast", "sharpen", "space_height", "line_spacing", "letter_spacing"];
      if (rangeKeys.includes(key)) {
        const readout = document.getElementById(`readout-${id}-${key}`);
        if (readout) readout.textContent = value;
      }
      if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
    }
  },

  // ── Table block parsing (receipt designer) ─────────────────
  updateTableBlockFromInputs(id) {
    const card = this.canvas && this.canvas.querySelector(`.block-card[data-id="${id}"]`);
    if (!card) return;
    const headersEl = card.querySelector(".table-headers-input");
    const rowsEl = card.querySelector(".table-rows-input");
    const widthsEl = card.querySelector(".table-widths-input");
    const headers = (headersEl ? headersEl.value : "").split(",").map(s => s.trim()).filter(s => s.length > 0);
    const rows = (rowsEl ? rowsEl.value : "").split("\n")
      .map(line => line.trim())
      .filter(line => line.length > 0)
      .map(line => line.split(",").map(c => c.trim()));
    const widths = (widthsEl ? widthsEl.value : "").split(",")
      .map(s => parseInt(s.trim(), 10))
      .filter(n => !isNaN(n) && n > 0);

    const block = this.blocks.find(b => b.id === id);
    if (!block) return;
    const sig = JSON.stringify([headers, rows, widths.length ? widths : null]);
    if (sig === JSON.stringify([block.table_headers || [], block.table_rows || [], block.table_col_widths || null])) return;
    this._pushUndo();
    block.table_headers = headers;
    block.table_rows = rows;
    block.table_col_widths = widths.length ? widths : null;
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
  },

  // ── Totals block parsing ───────────────────────────────────
  updateTotalsBlock(id, linesText) {
    const block = this.blocks.find(b => b.id === id);
    if (!block) return;
    const lines = (linesText || "").split("\n")
      .map(line => line.trim())
      .filter(line => line.length > 0)
      .map(line => {
        let bold = false;
        let text = line;
        if (text.startsWith("*")) { bold = true; text = text.slice(1).trim(); }
        const sep = text.indexOf("|");
        const label = sep >= 0 ? text.slice(0, sep).trim() : text;
        const value = sep >= 0 ? text.slice(sep + 1).trim() : "";
        return { label, value, dotted: true, bold };
      });
    const sig = JSON.stringify(lines);
    if (sig === JSON.stringify(block.totals_lines || [])) return;
    this._pushUndo();
    block.totals_lines = lines;
    if (window.PreviewManager) window.PreviewManager.scheduleUpdate();
  },

  handleImageUpload(id, input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    const reader = new FileReader();

    reader.onload = (e) => {
      this.updateBlock(id, "image_data", e.target.result);
      this.render();
    };
    reader.readAsDataURL(file);
  }
};
