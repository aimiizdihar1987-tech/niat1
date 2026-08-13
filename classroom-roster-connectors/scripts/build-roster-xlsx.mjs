import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const workingDir = process.cwd();
const outputDir = path.resolve(workingDir, "..");
const outputPath = path.join(outputDir, "classroom_roster_3_kelas.xlsx");
const previewPath = path.join(outputDir, "working", "classroom_roster_preview.png");

const rosterSlots = [
  [1, "3 Delima", null, "advanced", true, "classroom_invite_confirmed_by_user"],
  [2, "3 Delima", null, "intermediate", true, "classroom_invite_confirmed_by_user"],
  [3, "3 Delima", null, "lower_achiever", true, "classroom_invite_confirmed_by_user"],
  [4, "3 Zamrud", null, "advanced", true, "classroom_invite_confirmed_by_user"],
  [5, "3 Zamrud", null, "intermediate", true, "classroom_invite_confirmed_by_user"],
  [6, "3 Zamrud", null, "lower_achiever", true, "classroom_invite_confirmed_by_user"],
  [7, "3 Berlian", null, "advanced", true, "classroom_invite_confirmed_by_user"],
  [8, "3 Berlian", null, "intermediate", true, "classroom_invite_confirmed_by_user"],
  [9, "3 Berlian", null, "lower_achiever", true, "classroom_invite_confirmed_by_user"],
];

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Roster Kelas");
sheet.showGridLines = false;

sheet.getRange("A1:G1").merge();
sheet.getRange("A1").values = [["TEMPLAT ROSTER CLASSROOM - 3 KELAS"]];
sheet.getRange("A2:G2").merge();
sheet.getRange("A2").values = [[
  "Masukkan alamat e-mel dalam ruang kuning. ID DELIMa sebenar tidak disimpan dalam fail yang dijana ini.",
]];

sheet.getRange("A4:F4").values = [["Jumlah Slot", null, "E-mel Diisi", null, "Baki", null]];
sheet.getRange("B4").formulas = [["=COUNTA(A8:A16)"]];
sheet.getRange("D4").formulas = [["=COUNTA(C8:C16)"]];
sheet.getRange("F4").formulas = [["=B4-D4"]];

sheet.getRange("A7:G7").values = [[
  "Bil.",
  "Kelas",
  "E-mel Akaun (Isi Sendiri)",
  "Tahap Pencapaian",
  "Aktif",
  "Sumber",
  "Status",
]];
sheet.getRange("A8:F16").values = rosterSlots;
sheet.getRange("G8").formulas = [["=IF(C8=\"\",\"BELUM DIISI\",\"SEDIA SYNC\")"]];
sheet.getRange("G8:G16").fillDown();

const table = sheet.tables.add("A7:G16", true, "ClassroomRosterImport");
table.style = "TableStyleMedium2";
table.showBandedRows = true;
table.showFilterButton = true;

sheet.getRange("A18:G18").merge();
sheet.getRange("A18").values = [[
  "Privasi: isi alamat sendiri selepas membuka fail. Jangan commit atau kongsi salinan yang telah diisi.",
]];
sheet.getRange("A20:G20").merge();
sheet.getRange("A20").values = [[
  "Import: gunakan lajur Kelas, E-mel, Tahap, Aktif dan Sumber untuk Supabase atau Google Cloud Firestore.",
]];

sheet.getRange("A1:G1").format = {
  fill: "#102F4F",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
sheet.getRange("A1:G1").format.rowHeight = 34;
sheet.getRange("A2:G2").format = {
  fill: "#FFF4CC",
  font: { color: "#71541A", italic: true },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange("A2:G2").format.rowHeight = 32;

for (const rangeAddress of ["A4:B4", "C4:D4", "E4:F4"]) {
  sheet.getRange(rangeAddress).format = {
    fill: "#E8F1F5",
    font: { color: "#183F65", bold: true },
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#BED0DD" },
  };
}
sheet.getRange("A4:F4").format.rowHeight = 28;
sheet.getRange("B4,D4,F4").format = {
  fill: "#FFFFFF",
  font: { color: "#102F4F", bold: true, size: 12 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};

sheet.getRange("A7:G7").format = {
  fill: "#167D8D",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange("A7:G7").format.rowHeight = 30;
sheet.getRange("A8:B16").format.horizontalAlignment = "center";
sheet.getRange("D8:G16").format.horizontalAlignment = "center";
sheet.getRange("C8:C16").format = {
  fill: "#FFF8DB",
  font: { color: "#5D4A17" },
  numberFormat: "@",
  horizontalAlignment: "left",
};

sheet.getRange("B8:B16").dataValidation = {
  rule: { type: "list", values: ["3 Delima", "3 Zamrud", "3 Berlian"] },
};
sheet.getRange("D8:D16").dataValidation = {
  rule: { type: "list", values: ["advanced", "intermediate", "lower_achiever"] },
};
sheet.getRange("E8:E16").dataValidation = {
  rule: { type: "list", values: [true, false] },
};

sheet.getRange("D8:D16").conditionalFormats.add("containsText", {
  text: "advanced",
  format: { fill: "#E5F4EB", font: { color: "#337554", bold: true } },
});
sheet.getRange("D8:D16").conditionalFormats.add("containsText", {
  text: "intermediate",
  format: { fill: "#E8F0FB", font: { color: "#3269AA", bold: true } },
});
sheet.getRange("D8:D16").conditionalFormats.add("containsText", {
  text: "lower_achiever",
  format: { fill: "#FAE9E7", font: { color: "#A94845", bold: true } },
});
sheet.getRange("G8:G16").conditionalFormats.add("containsText", {
  text: "SEDIA SYNC",
  format: { fill: "#DFF4E7", font: { color: "#26734E", bold: true } },
});
sheet.getRange("G8:G16").conditionalFormats.add("containsText", {
  text: "BELUM DIISI",
  format: { fill: "#FFF0D8", font: { color: "#9A6717", bold: true } },
});

sheet.getRange("A18:G18").format = {
  fill: "#FBE9E7",
  font: { color: "#923E39", bold: true },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange("A18:G18").format.rowHeight = 30;
sheet.getRange("A20:G20").format = {
  fill: "#E9F3FA",
  font: { color: "#315D7C" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange("A20:G20").format.rowHeight = 30;

sheet.getRange("A8:A16").format.columnWidth = 8;
sheet.getRange("B8:B16").format.columnWidth = 16;
sheet.getRange("C8:C16").format.columnWidth = 34;
sheet.getRange("D8:D16").format.columnWidth = 20;
sheet.getRange("E8:E16").format.columnWidth = 10;
sheet.getRange("F8:F16").format.columnWidth = 36;
sheet.getRange("G8:G16").format.columnWidth = 17;
sheet.getRange("A8:G16").format.rowHeight = 25;
sheet.freezePanes.freezeRows(7);

const keyCheck = await workbook.inspect({
  kind: "table",
  range: "Roster Kelas!A1:G20",
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 7,
  maxChars: 12000,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
  maxChars: 3000,
});

const preview = await workbook.render({
  sheetName: "Roster Kelas",
  range: "A1:G20",
  scale: 1.4,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

console.log(JSON.stringify({ outputPath, previewPath, sheetCount: 1, slots: rosterSlots.length }, null, 2));
console.log(keyCheck.ndjson);
console.log(errors.ndjson);
