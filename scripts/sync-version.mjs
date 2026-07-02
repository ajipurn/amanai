#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const mode = process.argv.includes("--check") ? "check" : "write";

function fail(message) {
  console.error(`amanai version sync: ${message}`);
  process.exitCode = 1;
}

function readFile(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function writeFile(relativePath, content) {
  fs.writeFileSync(path.join(root, relativePath), content);
}

function check(label, actual, expected) {
  if (actual !== expected) {
    fail(`${label} is ${actual}, expected ${expected}`);
  }
}

function updateJsonVersion(relativePath, version, extraUpdates = () => {}) {
  const json = JSON.parse(readFile(relativePath));
  if (mode === "check") {
    check(relativePath, json.version, version);
    extraUpdates(json, true);
    return;
  }

  json.version = version;
  extraUpdates(json, false);
  writeFile(relativePath, `${JSON.stringify(json, null, 2)}\n`);
  console.log(`synced ${relativePath}`);
}

const version = readFile("VERSION").trim();
if (!/^[0-9]+\.[0-9]+\.[0-9]+$/.test(version)) {
  fail(`VERSION must be x.y.z, got ${JSON.stringify(version)}`);
  process.exit();
}

const pythonPath = "packages/sdk-python/amanai/__init__.py";
const pythonSource = readFile(pythonPath);
const pythonMatch = pythonSource.match(/^__version__ = "([^"]+)"$/m);
if (!pythonMatch) {
  fail(`could not find __version__ in ${pythonPath}`);
} else if (mode === "check") {
  check(pythonPath, pythonMatch[1], version);
} else {
  writeFile(pythonPath, pythonSource.replace(/^__version__ = "[^"]+"$/m, `__version__ = "${version}"`));
  console.log(`synced ${pythonPath}`);
}

updateJsonVersion("packages/sdk-node/package.json", version);
updateJsonVersion("packages/sdk-node/package-lock.json", version, (json, checkOnly) => {
  if (!json.packages || !json.packages[""]) {
    fail("packages/sdk-node/package-lock.json is missing packages[\"\"]");
    return;
  }
  if (checkOnly) {
    check("packages/sdk-node/package-lock.json packages[\"\"].version", json.packages[""].version, version);
    return;
  }
  json.packages[""].version = version;
});

const badgeUrl = `https://img.shields.io/badge/release-${version}-f97316?style=flat-square&labelColor=3f3f46`;
const readmePath = "README.md";
const readmeSource = readFile(readmePath);
const badgePattern =
  /https:\/\/img\.shields\.io\/(?:pypi\/v\/amanai\?style=flat-square&label=release&color=f97316&labelColor=3f3f46|badge\/release-[0-9]+\.[0-9]+\.[0-9]+-f97316\?style=flat-square&labelColor=3f3f46)/;

if (mode === "check") {
  if (!readmeSource.includes(badgeUrl)) {
    fail(`${readmePath} release badge is not ${badgeUrl}`);
  }
} else if (!badgePattern.test(readmeSource)) {
  fail(`could not find release badge in ${readmePath}`);
} else {
  writeFile(readmePath, readmeSource.replace(badgePattern, badgeUrl));
  console.log(`synced ${readmePath}`);
}

if (process.exitCode) {
  process.exit();
}
