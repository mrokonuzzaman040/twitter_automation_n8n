/**
 * Social Agents - Google Sheets web app (version 2).
 *
 * Install: open the spreadsheet -> Extensions -> Apps Script -> replace the code with this file ->
 * Deploy -> Manage deployments -> edit the existing deployment -> Version: New version -> Deploy.
 * (Editing the existing deployment keeps the same web app URL. Execute as: Me, access: Anyone.)
 *
 * Every request is a POST with a JSON body. Actions:
 *   {action:"version"}                              -> {version:2}            (writes nothing)
 *   {action:"append", sheet, row}                   -> appends row to an existing tab
 *   {action:"log", row}                             -> appends row to today's Log_YYYY-MM-DD tab (created if needed)
 *   {action:"upsert", sheet, header, row}           -> creates the tab with header if needed, then updates the
 *                                                      row whose first cell equals row[0], or appends it
 *   {action:"ensure", sheet, header}                -> creates the tab with header if it does not exist
 * "append" and "log" behave exactly like the earlier script, so existing n8n workflows keep working.
 */
var VERSION = 2;
var LOG_HEADER = ["Timestamp", "Action_Type", "Target_User", "Related_Tweet_ID", "Details_Content", "Result_Status"];

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    if (data.action === "version") return reply({ version: VERSION });

    if (data.action === "log") {
      var today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd");
      ensureSheet(ss, "Log_" + today, LOG_HEADER).appendRow(data.row);
      return reply({ success: true });
    }

    if (data.action === "ensure") {
      ensureSheet(ss, data.sheet, data.header);
      return reply({ success: true });
    }

    if (data.action === "upsert") {
      var lock = LockService.getScriptLock();
      lock.waitLock(20000);
      try {
        var sheet = ensureSheet(ss, data.sheet, data.header);
        var key = String(data.row[0]);
        var last = sheet.getLastRow();
        var keys = last > 1 ? sheet.getRange(2, 1, last - 1, 1).getDisplayValues() : [];
        for (var i = 0; i < keys.length; i++) {
          if (keys[i][0] === key) {
            sheet.getRange(i + 2, 1, 1, data.row.length).setValues([data.row]);
            return reply({ success: true, updated: true });
          }
        }
        sheet.appendRow(data.row);
        return reply({ success: true, updated: false });
      } finally {
        lock.releaseLock();
      }
    }

    // "append" (and anything unknown, as before): add the row to an existing tab
    var target = ss.getSheetByName(data.sheet);
    if (!target) return reply({ error: "Sheet not found: " + data.sheet });
    target.appendRow(data.row);
    return reply({ success: true });
  } catch (err) {
    return reply({ error: err.toString() });
  }
}

function ensureSheet(ss, name, header) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    if (header && header.length) {
      sheet.appendRow(header);
      sheet.getRange(1, 1, 1, header.length).setFontWeight("bold").setBackground("#0F1419").setFontColor("#FFFFFF");
      sheet.setFrozenRows(1);
    }
  }
  return sheet;
}

function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
