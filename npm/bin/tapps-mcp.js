#!/usr/bin/env node

/**
 * tapps-mcp npm wrapper
 *
 * Delegates to the Python tapps-mcp package. Checks for Python
 * installation, installs tapps-mcp via pip/uv if needed, then
 * forwards all arguments to `tapps-mcp`.
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

function isTappsMCPInstalled(python) {
  try {
    execSync(`${python} -c "import tapps_mcp"`, { stdio: ["pipe", "pipe", "pipe"] });
    return true;
  } catch {
    return false;
  }
}

function installTappsMCP(installer) {
  console.log("Installing tapps-mcp...");
  try {
    if (installer === "uv") {
      execSync("uv pip install tapps-mcp", { stdio: "inherit" });
    } else {
      execSync("pip install tapps-mcp", { stdio: "inherit" });
    }
    return true;
  } catch (err) {
    console.error("Failed to install tapps-mcp:", err.message);
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

if (!isTappsMCPInstalled(python)) {
  const installer = findInstaller();
  if (!installer) {
    console.error("Error: Neither uv nor pip found. Install one to continue.");
    process.exit(1);
  }
  if (!installTappsMCP(installer)) {
    process.exit(1);
  }
}

// Forward all args to tapps-mcp CLI (no shell to prevent injection)
const args = process.argv.slice(2);
const child = spawn("tapps-mcp", args, {
  stdio: "inherit",
  shell: process.platform === "win32",
});

child.on("error", (err) => {
  console.error("Failed to start tapps-mcp:", err.message);
  process.exit(1);
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
