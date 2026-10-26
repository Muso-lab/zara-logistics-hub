/**
 * ============================================================================
 * ZARA LOGISTICS MONTEROTONDO - GOOGLE SHEETS CLOUD DATABASE BRIDGE
 * ============================================================================
 * ISTRUZIONI:
 * 1. Crea un nuovo Foglio Google su Google Drive (es. "DB_Zara_Monterotondo").
 * 2. Nel menu in alto del Foglio Google clicca su: Estensioni -> Apps Script.
 * 3. Cancella il codice presente e incolla TUTTO questo codice.
 * 4. Clicca sull'icona del dischetto "Salva progetto" in alto.
 * 5. In alto a destra clicca su "Implementa" (Deploy) -> "Nuova implementazione".
 * 6. Clicca sull'ingranaggio accanto a "Seleziona tipo" -> scegli "Applicazione web".
 * 7. Imposta:
 *    - Descrizione: "DB Zara Monterotondo"
 *    - Esegui come: "Me" (il tuo account)
 *    - Chi ha accesso: "Chiunque" (necessario affinche' Streamlit Cloud possa comunicare)
 * 8. Clicca su "Implementa", autorizza l'accesso (Avanzate -> Vai a Progetto) e
 *    copia l'URL dell'applicazione web (termina con /exec).
 * ============================================================================
 */

const TABLES = [
  "stores",
  "store_delivery_profiles",
  "bolle",
  "runs",
  "forecast_raw",
  "other_items",
  "actual_deliveries",
  "planning_results",
  "spunta_arrivi",
  "sga_flows"
];

/**
 * Legge una o tutte le tabelle dal Foglio Google e le restituisce in JSON.
 */
function doGet(e) {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const requestedTable = (e && e.parameter && e.parameter.table) ? e.parameter.table : null;
    const targetTables = requestedTable ? [requestedTable] : TABLES;
    const result = {};

    targetTables.forEach(function(tableName) {
      const sheet = ss.getSheetByName(tableName);
      if (!sheet) {
        result[tableName] = [];
        return;
      }
      const data = sheet.getDataRange().getValues();
      if (data.length <= 1) {
        result[tableName] = [];
        return;
      }
      const headers = data[0].map(function(h) { return String(h).trim(); });
      const rows = [];
      for (var i = 1; i < data.length; i++) {
        var rowObj = {};
        var hasValue = false;
        for (var j = 0; j < headers.length; j++) {
          var val = data[i][j];
          if (val !== "" && val !== null && val !== undefined) {
            hasValue = true;
          }
          rowObj[headers[j]] = val;
        }
        if (hasValue) {
          rows.push(rowObj);
        }
      }
      result[tableName] = rows;
    });

    return ContentService
      .createTextOutput(JSON.stringify({ status: "ok", tables: result }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Riceve una o piu' tabelle in formato JSON da Streamlit e aggiorna i relativi fogli.
 */
function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(25000);
  try {
    const payload = JSON.parse(e.postData.contents);
    const tablesData = payload.tables || {};
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const updated = [];

    Object.keys(tablesData).forEach(function(tableName) {
      const rows = tablesData[tableName] || [];
      if (rows.length === 0) {
        updated.push(tableName + " (0 righe ignorate - foglio protetto)");
        return;
      }
      let sheet = ss.getSheetByName(tableName);
      if (!sheet) {
        sheet = ss.insertSheet(tableName);
      } else {
        sheet.clearContents();
      }

      // Ricava le intestazioni dalla prima riga (o dall'unione delle chiavi)
      const headerSet = {};
      rows.forEach(function(r) {
        Object.keys(r).forEach(function(k) { headerSet[k] = true; });
      });
      const headers = Object.keys(headerSet);

      const matrix = [headers];
      rows.forEach(function(r) {
        const line = headers.map(function(h) {
          var v = r[h];
          return (v === null || v === undefined) ? "" : v;
        });
        matrix.push(line);
      });

      // Imposta formato testo sulle colonne codice per non perdere zeri o suffissi
      sheet.getRange(1, 1, matrix.length, headers.length).setValues(matrix);
      sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#e2e8f0");
      updated.push(tableName + " (" + rows.length + " righe)");
    });

    return ContentService
      .createTextOutput(JSON.stringify({ status: "ok", updated: updated }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}
