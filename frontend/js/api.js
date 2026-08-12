/**
 * Mini Print Studio — API Client Layer
 */
const API = {
  baseUrl: "/api",

  async request(endpoint, options = {}) {
    const config = {
      headers: {
        "Content-Type": "application/json",
      },
      ...options,
    };

    if (config.body && typeof config.body === "object") {
      config.body = JSON.stringify(config.body);
    }

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, config);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || "API Request Failed");
      }
      return await response.json();
    } catch (err) {
      console.error(`API Error [${endpoint}]:`, err);
      throw err;
    }
  },

  // Printer Endpoints
  getPrinters() {
    return this.request("/printers");
  },
  getPrinterStatus() {
    return this.request("/printers/status");
  },
  connectPrinter(printerId, connectionType, address, protocol) {
    return this.request("/printers/connect", {
      method: "POST",
      body: { printer_id: printerId, connection_type: connectionType, address, protocol },
    });
  },
  disconnectPrinter() {
    return this.request("/printers/disconnect", { method: "POST" });
  },
  testPrint() {
    return this.request("/printers/test", { method: "POST" });
  },

  // Print Job Endpoints
  submitPrintJob(printRequest) {
    return this.request("/print", {
      method: "POST",
      body: printRequest,
    });
  },
  printCsvLabels(csvRequest) {
    return this.request("/print/csv", {
      method: "POST",
      body: csvRequest,
    });
  },
  getPrintJobStatus(jobId) {
    return this.request(`/print/jobs/${jobId}`);
  },
  getPrintQueue() {
    return this.request("/print/queue");
  },
  getPrintPreview(printRequest) {
    return this.request("/print/preview", {
      method: "POST",
      body: printRequest,
    });
  },
  cancelPrintJob(jobId) {
    return this.request("/print/cancel", {
      method: "POST",
      body: jobId ? { job_id: jobId } : {},
    });
  },
  exportPrint(printRequest, format = "png") {
    return fetch(`${this.baseUrl}/print/export?fmt=${format}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(printRequest),
    }).then(async (response) => {
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Export failed" }));
        throw new Error(errorData.detail || "Export failed");
      }
      return response.blob();
    });
  },

  // Image Processing Endpoints
  processImage(imageProcessRequest) {
    return this.request("/images/process", {
      method: "POST",
      body: imageProcessRequest,
    });
  },
  compareImage(imageProcessRequest) {
    return this.request("/images/compare", {
      method: "POST",
      body: imageProcessRequest,
    });
  },
  calibrateImage(payload) {
    return this.request("/print/calibrate", {
      method: "POST",
      body: payload,
    });
  },

  // Settings Endpoints
  getSettings() {
    return this.request("/settings");
  },
  saveSettings(settings) {
    return this.request("/settings", {
      method: "POST",
      body: settings,
    });
  },

  // Templates Endpoints
  getTemplates() {
    return this.request("/templates");
  },
  getTemplate(id) {
    return this.request(`/templates/${id}`);
  },
  saveTemplate(template) {
    return this.request("/templates", {
      method: "POST",
      body: template,
    });
  },
  deleteTemplate(id) {
    return this.request(`/templates/${id}`, { method: "DELETE" });
  },

  // History Endpoints
  getHistory() {
    return this.request("/history");
  },
  getHistoryStats() {
    return this.request("/history/stats");
  },
  clearHistory() {
    return this.request("/history", { method: "DELETE" });
  },

  // Template Endpoints
  setTemplateFavorite(templateId, favorite) {
    return this.request(`/templates/${templateId}/favorite`, {
      method: "POST",
      body: { favorite },
    });
  },

  // Document Endpoints
  getDocuments() {
    return this.request("/documents");
  },
  saveDocument(documentData) {
    return this.request("/documents", {
      method: "POST",
      body: documentData,
    });
  },
  deleteDocument(id) {
    return this.request(`/documents/${id}`, { method: "DELETE" });
  },

  // Debug Endpoints
  getDebugTrace() {
    return this.request("/debug/trace");
  },
  getDebugLastPayload() {
    return this.request("/debug/last-payload");
  },
};
