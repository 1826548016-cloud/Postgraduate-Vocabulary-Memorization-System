import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:\\Users\\34916\\Desktop\\2026级软件工程大数据专业绿色通道未审核名单.xlsx";
const outputDir = "D:\\word\\green_channel_fill\\output";

const names = [
  ["柴凯欣", "202615110170"],
  ["王雅琳", "202615110174"],
  ["王晨宇", "202615110066"],
  ["牛晓婷", "202615110210"],
  ["王荟钧", "202615110162"],
  ["宋欣瑜", "202615110198"],
  ["马梦格", "202615110238"],
  ["张艺宁", "202615110166"],
  ["马于晴", "202615110234"],
  ["林怡诺", "201615110038"],
  ["赵孟菲", "202615110226"],
  ["赵航", "202615110098"],
  ["杨杰", "202615110158"],
  ["李冠雨", "202615110178"],
  ["李梦兰", "202615110218"],
  ["张子轩", "202615110078"],
  ["王真真", "202615110230"],
  ["陈俊衡", "202615110090"],
  ["曹雯静", "202615110206"],
];

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getActiveWorksheet();

const startRow = 2;
const range = sheet.getRange(`E${startRow}:F${startRow + names.length - 1}`);
range.values = names;
range.format = {
  font: { name: "宋体", size: 11 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin" },
};

await fs.mkdir(outputDir, { recursive: true });

const preview = await workbook.render({
  sheetName: "Sheet1",
  autoCrop: "all",
  scale: 2,
  format: "png",
});
await fs.writeFile(`${outputDir}/preview.png`, new Uint8Array(await preview.arrayBuffer()));

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}/绿色通道未审核名单_已填写.xlsx`);

console.log("DONE", names.length, "rows written to E2:F20");
