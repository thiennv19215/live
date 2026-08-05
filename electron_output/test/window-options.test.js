const test = require("node:test");
const assert = require("node:assert/strict");
const { fitToWorkArea, parseOptions } = require("../window-options");

test("parses a supported ratio and dimensions", () => {
  const result = parseOptions(["app", "--ratio", "4:5", "--width", "1080", "--height", "1350"]);
  assert.deepEqual(result, {
    url: "http://127.0.0.1:8765/overlay",
    ratio: "4:5",
    width: 1080,
    height: 1350,
    controlPort: 0,
  });
});

test("falls back to vertical output for an unknown ratio", () => {
  const result = parseOptions(["app", "--ratio=invalid"]);
  assert.equal(result.ratio, "9:16");
  assert.equal(result.width, 1080);
  assert.equal(result.height, 1920);
});

test("fits a portrait output inside the monitor while preserving ratio", () => {
  const result = fitToWorkArea(1080, 1920, { width: 1920, height: 1080 });
  assert.equal(result.height, 929);
  assert.equal(result.width, 522);
});
