import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const paths = process.argv.slice(2);
for (const path of paths) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
  const sheets = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
  const matches = await workbook.inspect({
    kind: "match",
    searchTerm: "苹果手机|华为手机|同义词|跨子树|不同子树",
    options: { useRegex: true, maxResults: 100 },
    maxChars: 12000,
  });
  const firstSheet = workbook.worksheets.getItemAt(0);
  const used = firstSheet.getUsedRange();
  const previewRange = path.includes("小样本") ? "A1:F15" : "A1:F10";
  const preview = await workbook.inspect({ kind: "table", sheetId: firstSheet.name, range: previewRange, include: "values,formulas", tableMaxRows: 20, tableMaxCols: 8, maxChars: 10000 });
  process.stdout.write(`\n=== ${path} ===\n${sheets.ndjson}\n${matches.ndjson}\n${preview.ndjson}\n`);
}
