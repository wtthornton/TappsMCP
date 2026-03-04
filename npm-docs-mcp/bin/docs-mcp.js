#!/usr/bin/env node

/**
 * docs-mcp npm wrapper
 *
 * Delegates to the Python docs-mcp package. Checks for Python
 * installation, installs docs-mcp via pip/uv if needed, then
 * forwards all arguments to `docsmcp`.
 */

const { execSync, spawn } = require("child_process");

function findPython() {
  for (const cmd of ["python3", "python"]) {
    try {
      const version = execSync(`${cmd} --version`, { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] }).trim();
      const match = version.match(/Python (\d+)\.(\d+)/);
      if (match && parseInt(match[1]) >= 3 && parseInt(match[2]) >= 12) {
        return cmd;
      }
    } catch {
      // not found, try next
    }
  }
  return null;
}

function findInstaller() {
  // Prefer uv for speed
  try {
    execSync("uv --version", { stdio: ["pipe", "pipe", "pipe"] });
    return "uv";
  } catch {
    // fall through
  }
  try {
    execSync("pip --version", { stdio: ["pipe", "pipe", "pipe"] });
    return "pip";
  } catch {
    return null;
  }
}

function isDocsMCPInstalled(python) {
  try {
    execSync(`${python} -c "import docs_mcp"`, { stdio: ["pipe", "pipe", "pipe"] });
    return true;
  } catch {
    return false;
  }
}

function installDocsMCP(installer) {
  console.log("Installing docs-mcp...");
  try {
    if (installer === "uv") {
      execSync("uv pip install docs-mcp", { stdio: "inherit" });
    } else {
      execSync("pip install docs-mcp", { stdio: "inherit" });
    }
    return true;
  } catch (err) {
    console.error("Failed to install docs-mcp:", err.message);
    return false;
  }
}

// Main
const python = findPython();
if (!python) {
  console.error("Error: Python 3.12+ is required but not found.");
  console.error("Install Python from https://www.python.org/downloads/");
  process.exit(1);
}

if (!isDocsMCPInstalled(python)) {
  const installer = findInstaller();
  if (!installer) {
    console.error("Error: Neither uv nor pip found. Install one to continue.");
    process.exit(1);
  }
  if (!installDocsMCP(installer)) {
    process.exit(1);
  }
}

// Forward all args to docsmcp CLI (no shell to prevent injection)
const args = process.argv.slice(2);
const child = spawn("docsmcp", args, {
  stdio: "inherit",
  shell: process.platform === "win32",
});

child.on("error", (err) => {
  console.error("Failed to start docsmcp:", err.message);
  process.exit(1);
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
