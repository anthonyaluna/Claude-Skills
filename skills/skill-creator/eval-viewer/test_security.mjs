import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const viewer = readFileSync(new URL("./viewer.html", import.meta.url), "utf8");

function extractFunction(name, nextFunctionName) {
  const start = viewer.indexOf("function " + name + "(");
  assert.notEqual(start, -1, name + " should exist");
  const end = viewer.indexOf("function " + nextFunctionName + "(", start + 1);
  assert.notEqual(end, -1, nextFunctionName + " should follow " + name);
  return viewer.slice(start, end);
}

test("grading summary values are escaped before insertion into HTML", () => {
  const escapeHtml = extractFunction("escapeHtml", "switchView");
  const renderGrades = extractFunction("renderGrades", "toggleGrades");
  const gradesSection = { style: {} };
  const gradesContent = { classList: { remove() {} }, innerHTML: "" };
  const gradesArrow = { classList: { remove() {} } };
  const elements = {
    "grades-section": gradesSection,
    "grades-content": gradesContent,
    "grades-arrow": gradesArrow,
  };
  const document = {
    getElementById(id) {
      return elements[id];
    },
    createElement() {
      let textContent = "";
      return {
        set textContent(value) {
          textContent = String(value);
        },
        get innerHTML() {
          return textContent
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;");
        },
      };
    },
  };
  const context = { document };

  vm.runInNewContext(
    escapeHtml + "\n" + renderGrades + "\nthis.renderGrades = renderGrades;",
    context
  );

  context.renderGrades({
    grading: {
      summary: {
        pass_rate: 0.5,
        passed: "<img src=x onerror=alert(1)>",
        failed: 1,
        total: 2,
      },
      expectations: [],
    },
  });

  assert.match(gradesContent.innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(gradesContent.innerHTML, /<img\b/i);
});

test("benchmark metadata and deltas are escaped before insertion into HTML", () => {
  const escapeHtml = extractFunction("escapeHtml", "switchView");
  const benchmarkStart = viewer.indexOf("function renderBenchmark()");
  const benchmarkEnd = viewer.indexOf("// ---- Start ----", benchmarkStart);
  assert.notEqual(benchmarkStart, -1, "renderBenchmark should exist");
  assert.notEqual(benchmarkEnd, -1, "viewer start marker should follow renderBenchmark");
  const renderBenchmark = viewer.slice(benchmarkStart, benchmarkEnd);
  const elements = {
    "view-tabs": { style: {} },
    "benchmark-content": { innerHTML: "" },
  };
  const context = {
    document: {
      getElementById(id) {
        return elements[id];
      },
    },
    EMBEDDED_DATA: {
      benchmark: {
        metadata: {
          skill_name: "<img src=x onerror=alert(1)>",
          timestamp: "<img src=x onerror=alert(1)>",
          evals_run: ["<img src=x onerror=alert(1)>"],
          runs_per_configuration: "<img src=x onerror=alert(1)>",
        },
        run_summary: { delta: { pass_rate: "<img src=x onerror=alert(1)>" } },
        notes: [],
        runs: [],
      },
    },
  };

  vm.runInNewContext(
    escapeHtml + "\n" + renderBenchmark + "\nthis.renderBenchmark = renderBenchmark;",
    context
  );
  context.renderBenchmark();

  assert.match(elements["benchmark-content"].innerHTML, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(elements["benchmark-content"].innerHTML, /<img\b/i);
});

test("spreadsheet cell values are rendered as text rather than generated HTML", () => {
  const appendOutputNotice = extractFunction("appendOutputNotice", "renderOutputs");
  const renderXlsx = extractFunction("renderXlsx", "renderGrades");
  const payload = "<img src=x onerror=alert(1)>";
  const created = [];
  let sheetToHtmlCalled = false;
  const document = {
    createElement(tagName) {
      const element = {
        tagName,
        children: [],
        style: {},
        appendChild(child) {
          this.children.push(child);
        },
      };
      created.push(element);
      return element;
    },
  };
  const context = {
    document,
    atob() {
      return "x";
    },
    XLSX: {
      read() {
        return {
          SheetNames: ["Sheet1"],
          Sheets: { Sheet1: { "!ref": "A1", A1: { w: payload, v: payload } } },
        };
      },
      utils: {
        decode_range() {
          return { s: { r: 0, c: 0 }, e: { r: 0, c: 0 } };
        },
        encode_cell() {
          return "A1";
        },
        sheet_to_html() {
          sheetToHtmlCalled = true;
          return "<table><tr><td>" + payload + "</td></tr></table>";
        },
      },
    },
  };
  const container = {
    children: [],
    textContent: "",
    appendChild(child) {
      this.children.push(child);
    },
  };

  vm.runInNewContext(
    appendOutputNotice + "\n" + renderXlsx + "\nthis.renderXlsx = renderXlsx;",
    context
  );
  context.renderXlsx(container, "AA==");

  assert.equal(created.some(element => typeof element.innerHTML === "string"), false);
  assert.equal(sheetToHtmlCalled, false);
  const cell = created.find(element => element.tagName === "td");
  assert.ok(cell, "a table cell should be rendered");
  assert.equal(cell.textContent, payload);
});

test("small merged spreadsheet cells remain available in the preview", () => {
  const appendOutputNotice = extractFunction("appendOutputNotice", "renderOutputs");
  const renderXlsx = extractFunction("renderXlsx", "renderGrades");
  const created = [];
  const document = {
    createElement(tagName) {
      const element = {
        tagName,
        children: [],
        style: {},
        appendChild(child) {
          this.children.push(child);
        },
      };
      created.push(element);
      return element;
    },
  };
  const context = {
    document,
    atob() {
      return "x";
    },
    XLSX: {
      read() {
        return {
          SheetNames: ["Sheet1"],
          Sheets: {
            Sheet1: {
              "!ref": "A1:B2",
              "!merges": [{ s: { r: 0, c: 0 }, e: { r: 0, c: 1 } }],
              "0:0": { w: "Merged value", v: "Merged value" },
            },
          },
        };
      },
      utils: {
        decode_range() {
          return { s: { r: 0, c: 0 }, e: { r: 1, c: 1 } };
        },
        encode_cell({ r, c }) {
          return `${r}:${c}`;
        },
      },
    },
  };
  const container = { children: [], appendChild(child) { this.children.push(child); } };

  vm.runInNewContext(
    appendOutputNotice + "\n" + renderXlsx + "\nthis.renderXlsx = renderXlsx;",
    context
  );
  context.renderXlsx(container, "AA==");

  const cells = created.filter(element => element.tagName === "td");
  assert.equal(cells.length, 3);
  assert.equal(cells[0].textContent, "Merged value");
  assert.equal(cells[0].colSpan, 2);
});

test("spreadsheet preview limits parser rows and rendered cells", () => {
  const appendOutputNotice = extractFunction("appendOutputNotice", "renderOutputs");
  const renderXlsx = extractFunction("renderXlsx", "renderGrades");
  const created = [];
  let readOptions;
  let encodeCalls = 0;
  const document = {
    createElement(tagName) {
      const element = {
        tagName,
        children: [],
        style: {},
        appendChild(child) {
          this.children.push(child);
        },
      };
      created.push(element);
      return element;
    },
  };
  const context = {
    document,
    atob() {
      return "x";
    },
    XLSX: {
      read(_raw, options) {
        readOptions = options;
        return {
          SheetNames: ["Sheet1", "Sheet2"],
          Sheets: {
            Sheet1: { "!ref": "A1:XFD20000", "!merges": [{ s: { r: 0, c: 0 }, e: { r: 19999, c: 16383 } }] },
          },
        };
      },
      utils: {
        decode_range() {
          return { s: { r: 0, c: 0 }, e: { r: 19999, c: 16383 } };
        },
        encode_cell({ r, c }) {
          encodeCalls++;
          return `${r}:${c}`;
        },
      },
    },
  };
  const container = {
    children: [],
    textContent: "",
    appendChild(child) {
      this.children.push(child);
    },
  };

  vm.runInNewContext(
    appendOutputNotice + "\n" + renderXlsx + "\nthis.renderXlsx = renderXlsx;",
    context
  );
  context.renderXlsx(container, "AA==");

  assert.deepEqual({ ...readOptions }, {
    type: "array",
    sheets: 0,
    sheetRows: 20,
    cellHTML: false,
    cellFormula: false,
    cellStyles: false,
  });
  assert.equal(created.filter(element => element.tagName === "td").length, 10000);
  assert.ok(encodeCalls <= 10000, "merge and cell traversal should stay within the preview budget");
  assert.ok(created.some(element => /preview is limited/i.test(element.textContent)));
});

test("oversized spreadsheets skip base64 decoding and parsing", () => {
  const appendOutputNotice = extractFunction("appendOutputNotice", "renderOutputs");
  const renderXlsx = extractFunction("renderXlsx", "renderGrades");
  const created = [];
  let atobCalled = false;
  let readCalled = false;
  const document = {
    createElement(tagName) {
      const element = { tagName, textContent: "" };
      created.push(element);
      return element;
    },
  };
  const context = {
    document,
    atob() {
      atobCalled = true;
      return "x";
    },
    XLSX: {
      read() {
        readCalled = true;
        return { SheetNames: [], Sheets: {} };
      },
    },
  };
  const container = { children: [], appendChild(child) { this.children.push(child); } };

  vm.runInNewContext(
    appendOutputNotice + "\n" + renderXlsx + "\nthis.renderXlsx = renderXlsx;",
    context
  );
  context.renderXlsx(container, "A".repeat(7 * 1024 * 1024));

  assert.equal(atobCalled, false);
  assert.equal(readCalled, false);
  assert.ok(created.some(element => /exceeds 5 MiB/i.test(element.textContent)));
});

test("PDF output uses the download link without embedding a document frame", () => {
  const appendOutputNotice = extractFunction("appendOutputNotice", "renderOutputs");
  const renderOutputs = extractFunction("renderOutputs", "renderXlsx");
  const created = [];
  const container = {
    children: [],
    innerHTML: "",
    appendChild(child) {
      this.children.push(child);
    },
  };
  const context = {
    document: {
      createElement(tagName) {
        const element = {
          tagName,
          children: [],
          appendChild(child) {
            this.children.push(child);
          },
        };
        created.push(element);
        return element;
      },
      getElementById() {
        return container;
      },
    },
    getDownloadUri(file) {
      return file.data_uri;
    },
  };
  const file = { name: "result.pdf", type: "pdf", data_uri: "data:application/pdf;base64,AA==" };

  vm.runInNewContext(
    appendOutputNotice + "\n" + renderOutputs + "\nthis.renderOutputs = renderOutputs;",
    context
  );
  context.renderOutputs({ outputs: [file] });

  assert.equal(created.some(element => element.tagName === "iframe"), false);
  assert.ok(created.some(element => element.tagName === "p" && /download to view/i.test(element.textContent)));
  const download = created.find(element => element.tagName === "a");
  assert.equal(download.href, file.data_uri);
  assert.equal(download.download, file.name);
});

test("previous PDF output uses the download link without embedding a document frame", () => {
  const appendOutputNotice = extractFunction("appendOutputNotice", "renderOutputs");
  const renderPrevOutputs = extractFunction("renderPrevOutputs", "togglePrevOutputs");
  const created = [];
  const section = { style: {} };
  const content = {
    children: [],
    innerHTML: "",
    style: {},
    classList: { remove() {} },
    appendChild(child) {
      this.children.push(child);
    },
  };
  const arrow = { classList: { remove() {} } };
  const elements = {
    "prev-outputs-section": section,
    "prev-outputs-content": content,
    "prev-outputs-arrow": arrow,
  };
  const context = {
    document: {
      createElement(tagName) {
        const element = {
          tagName,
          children: [],
          style: {},
          appendChild(child) {
            this.children.push(child);
          },
        };
        created.push(element);
        return element;
      },
      getElementById(id) {
        return elements[id];
      },
    },
    EMBEDDED_DATA: {
      previous_outputs: {
        "run-1": [{ name: "previous.pdf", type: "pdf", data_uri: "data:application/pdf;base64,AA==" }],
      },
    },
    getDownloadUri(file) {
      return file.data_uri;
    },
  };

  vm.runInNewContext(
    appendOutputNotice + "\n" + renderPrevOutputs + "\nthis.renderPrevOutputs = renderPrevOutputs;",
    context
  );
  context.renderPrevOutputs({ id: "run-1" });

  assert.equal(created.some(element => element.tagName === "iframe"), false);
  assert.ok(created.some(element => element.tagName === "p" && /download to view/i.test(element.textContent)));
  const download = created.find(element => element.tagName === "a");
  assert.equal(download.href, "data:application/pdf;base64,AA==");
  assert.equal(download.download, "previous.pdf");
});
