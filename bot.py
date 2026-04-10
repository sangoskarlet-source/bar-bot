const SPREADSHEET_ID = "1kXzNlk6ZvxK_HqUuI6zDjubD7V6L0oAFNl5s6rB91-o";

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);

    // 1. ПОЛУЧЕНИЕ ГРАФИКА
    if (data.action === "get_schedule") {
      const sheet = ss.getSheetByName("График");
      return ContentService.createTextOutput(JSON.stringify(sheet.getDataRange().getValues())).setMimeType(ContentService.MimeType.JSON);
    }

    // 2. ПРОВЕРКА ВЫПОЛНЕНИЯ (для напоминаний)
    if (data.action === "check_completion") {
      const sheetsToCheck = ["1 этаж", "2 этаж", "Чеклист", "Ежедневная уборка"];
      let report = {};
      const today = new Date().toLocaleDateString('ru-RU');

      sheetsToCheck.forEach(name => {
        const s = ss.getSheetByName(name);
        if (!s) { report[name] = false; return; }
        const values = s.getDataRange().getValues();
        report[name] = values.some(row => {
          let cell = row[1]; // Дата обычно в колонке B
          if (cell instanceof Date) return cell.toLocaleDateString('ru-RU') === today;
          return cell.toString().includes(today);
        });
      });
      return ContentService.createTextOutput(JSON.stringify(report)).setMimeType(ContentService.MimeType.JSON);
    }

    // 3. ЗАПИСЬ ДАННЫХ
    const sheetName = data.sheet;
    const sheet = ss.getSheetByName(sheetName);
    if (!sheet) return ContentService.createTextOutput("Лист не найден");

    if (sheetName === "Переносы" || sheetName === "Списания") {
      sheet.appendRow([new Date(), data.user, data.item, data.qty, data.direction || ""]);
      return ContentService.createTextOutput("OK");
    }

    // СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ЕЖЕДНЕВНОЙ УБОРКИ
    if (sheetName === "Ежедневная уборка") {
      const headers = sheet.getRange(2, 1, 1, sheet.getLastColumn()).getValues()[0]; // Заголовки на 2-й строке
      const targetTask = data.task.toLowerCase().trim();
      let colIndex = -1;

      for (let i = 0; i < headers.length; i++) {
        if (headers[i].toString().toLowerCase().trim().includes(targetTask)) {
          colIndex = i + 1;
          break;
        }
      }

      if (colIndex !== -1) {
        let newRow = new Array(headers.length).fill("");
        newRow[0] = data.user; // Сотрудник
        newRow[1] = new Date(); // Дата
        newRow[colIndex - 1] = "✅";
        sheet.appendRow(newRow);
        return ContentService.createTextOutput("OK");
      }
    }

    // ОБЫЧНЫЕ ЧЕКЛИСТЫ И ТЕМПЕРАТУРЫ
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const targetItem = (data.fridge || data.task || "").toString().toLowerCase().trim();
    const valueToSet = data.temp || data.val || "";
    const sessionId = data.session_id;

    let colIndex = -1;
    for (let i = 0; i < headers.length; i++) {
      if (headers[i].toString().toLowerCase().trim() === targetItem) {
        colIndex = i + 1; break;
      }
    }
    
    if (colIndex !== -1) {
      const lastRow = sheet.getLastRow();
      let rowToUpdate = -1;
      if (lastRow > 1) {
        const ids = sheet.getRange(2, 3, lastRow - 1, 1).getValues();
        for (let i = 0; i < ids.length; i++) {
          if (ids[i][0].toString() === sessionId) { rowToUpdate = i + 2; break; }
        }
      }
      if (rowToUpdate === -1) {
        let newRow = new Array(headers.length).fill("");
        newRow[0] = data.user; newRow[1] = new Date(); newRow[2] = sessionId;
        newRow[colIndex - 1] = valueToSet;
        sheet.appendRow(newRow);
      } else {
        sheet.getRange(rowToUpdate, colIndex).setValue(valueToSet);
      }
    }

    return ContentService.createTextOutput("OK");
  } catch (err) {
    return ContentService.createTextOutput("ERROR: " + err.toString());
  }
}
