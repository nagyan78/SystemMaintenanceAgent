import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outputDir = process.cwd();
const projectDir = path.resolve(outputDir, "..", "..");
const inputPath = path.join(projectDir, "data", "exports", "file-15_v1.0_version-27_taxonomy.xlsx");
const outputPath = path.join(outputDir, "产品标准体系_v1.1_优化版.xlsx");

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 5000,
  tableMaxRows: 8,
  tableMaxCols: 10,
  tableMaxCellChars: 100,
});
console.log(overview.ndjson);

const sheet = workbook.worksheets.getItemAt(0);
const used = sheet.getUsedRange(true);
const header = sheet.getRange("A1:J8");
const headerValues = await header.values;

if (process.argv.includes("--inspect")) {
  const preview = await workbook.render({ sheetName: sheet.name, range: "A1:F25", scale: 1.2, format: "png" });
  await fs.writeFile(path.join(outputDir, "v1.0_source_preview.png"), new Uint8Array(await preview.arrayBuffer()));
  console.log(JSON.stringify({ sheet: sheet.name, headerValues }, null, 2));
  process.exit(0);
}

const headerRowIndex = headerValues.findIndex((row) => row.some((cell) => /同义词|syn_list/i.test(String(cell ?? ""))));
if (headerRowIndex < 0) throw new Error("未找到同义词列。请检查工作表表头。");
const synonymColumnIndex = headerValues[headerRowIndex].findIndex((cell) => /同义词|syn_list/i.test(String(cell ?? "")));
const nodeNameColumnIndex = headerValues[headerRowIndex].findIndex((cell) => /category_name|节点名称/i.test(String(cell ?? "")));
const usedValues = await used.values;
let changedCount = 0;

for (let rowIndex = headerRowIndex + 1; rowIndex < usedValues.length; rowIndex += 1) {
  const raw = usedValues[rowIndex][synonymColumnIndex];
  if (raw === null || raw === undefined || String(raw).trim() === "") continue;
  const nodeName = String(usedValues[rowIndex][nodeNameColumnIndex] ?? "").trim();
  let sourceItems;
  let jsonEncoded = false;
  try {
    const parsed = JSON.parse(String(raw));
    if (Array.isArray(parsed)) {
      sourceItems = parsed;
      jsonEncoded = true;
    }
  } catch {
    sourceItems = undefined;
  }
  if (!sourceItems && /^\s*\[.*\]\s*$/.test(String(raw))) {
    sourceItems = [];
    for (const match of String(raw).matchAll(/'([^']*)'|"([^"]*)"/g)) {
      sourceItems.push(match[1] ?? match[2] ?? "");
    }
  }
  sourceItems ??= String(raw).split(/[，,、;；|\n\r]+/);
  const normalized = [];
  const seen = new Set();
  for (const item of sourceItems) {
    const value = String(item ?? "").trim();
    if (!value || value === nodeName || seen.has(value)) continue;
    seen.add(value);
    normalized.push(value);
  }
  const sourceNormalized = sourceItems.map((item) => String(item ?? "").trim());
  const semanticChanged = normalized.length !== sourceNormalized.length
    || normalized.some((item, index) => item !== sourceNormalized[index]);
  const nextValue = jsonEncoded || /^\s*\[.*\]\s*$/.test(String(raw))
    ? JSON.stringify(normalized)
    : normalized.join("、");
  if (semanticChanged) {
    usedValues[rowIndex][synonymColumnIndex] = nextValue;
    changedCount += 1;
  }
}

const synonymRange = sheet.getRangeByIndexes(
  headerRowIndex + 1,
  synonymColumnIndex,
  usedValues.length - headerRowIndex - 1,
  1,
);
synonymRange.values = usedValues.slice(headerRowIndex + 1).map((row) => [row[synonymColumnIndex]]);

sheet.freezePanes.freezeRows(1);
sheet.getRange(`A1:A${usedValues.length}`).format.columnWidth = 14;
sheet.getRange(`B1:B${usedValues.length}`).format.columnWidth = 28;
sheet.getRange(`C1:C${usedValues.length}`).format.columnWidth = 24;
sheet.getRange(`D1:D${usedValues.length}`).format.columnWidth = 34;
sheet.getRange(`E1:E${usedValues.length}`).format.columnWidth = 52;
sheet.getRange(`F1:F${usedValues.length}`).format.columnWidth = 46;
sheet.getRange("A1:F1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  rowHeight: 28,
};

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const verify = await workbook.inspect({
  kind: "table",
  range: `${sheet.name}!A1:F20`,
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 6,
  maxChars: 4000,
});
console.log(verify.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const preview = await workbook.render({ sheetName: sheet.name, range: "A1:F25", scale: 1.2, format: "png" });
await fs.writeFile(path.join(outputDir, "v1.1_final_preview.png"), new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({ outputPath, changedCount, sheet: sheet.name }, null, 2));
