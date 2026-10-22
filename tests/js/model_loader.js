"use strict";
// Loads ../../Model.js into a fresh vm context so its top-level declarations
// (QML `.pragma library` style, no module.exports) become readable properties
// without a QML engine. The only translation needed is dropping the
// QML-only `.pragma library` line, which Node cannot parse.

const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");

function loadModelJs() {
  const file = path.join(__dirname, "..", "..", "Model.js");
  const src = fs.readFileSync(file, "utf8").replace(/^\.pragma\s+library\s*$/m, "");
  const sandbox = {};
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: file });
  return sandbox;
}

module.exports = { loadModelJs };
