#!/usr/bin/env node
// Validate generated audit CSVs with the bundled artifact-tool parser.
import fs from "node:fs/promises";
import path from "node:path";
const artifactToolModule = process.env.ARTIFACT_TOOL_MODULE || "@oai/artifact-tool";
const { Workbook } = await import(artifactToolModule);

const [reportDirArg, previewArg] = process.argv.slice(2);
if (!reportDirArg) {
  throw new Error("usage: validate_audit_csvs.mjs <report-dir> [preview.png]");
}

const reportDir = path.resolve(reportDirArg);
const files = (await fs.readdir(reportDir)).filter((name) => name.endsWith(".csv")).sort();
const validation = [];
for (const name of files) {
  const fullPath = path.join(reportDir, name);
  const csvText = await fs.readFile(fullPath, "utf8");
  const workbook = await Workbook.fromCSV(csvText, { sheetName: "Data" });
  const sheet = workbook.worksheets.getItem("Data");
  const inspected = await workbook.inspect({
    kind: "sheet",
    include: "id,name,values",
    sheetId: sheet.id,
    range: "A1:Z8",
  });
  validation.push({
    file: name,
    bytes: Buffer.byteLength(csvText, "utf8"),
    imported: true,
    previewInspection: inspected,
  });
  if (previewArg && (name === "03_candidate_dataset_matrix.csv" || name === "06_casinolimit_final_technique_matrix.csv")) {
    const blob = await workbook.render({
      sheetName: "Data",
      range: name === "06_casinolimit_final_technique_matrix.csv" ? "A1:V8" : "A1:M10",
      autoCrop: "all",
      scale: 1,
      format: "png",
    });
    const arrayBuffer = await blob.arrayBuffer();
    await fs.mkdir(path.dirname(path.resolve(previewArg)), { recursive: true });
    await fs.writeFile(path.resolve(previewArg), new Uint8Array(arrayBuffer));
  }
}

const outPath = path.join(reportDir, "csv_artifact_tool_validation.json");
await fs.writeFile(outPath, `${JSON.stringify({ status: "ok", files: validation }, null, 2)}\n`, "utf8");
process.stdout.write(`${JSON.stringify({ status: "ok", csvCount: files.length, output: outPath })}\n`);
