#!/usr/bin/env node

import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createInterface } from "node:readline/promises";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const INSTALLER = join(ROOT, "scripts", "install.py");
const CORE_PROJECT = join(ROOT, "skills", "empirical-macro");
const HOSTS = ["generic", "trae", "codex", "claude-code", "openai4s"];
const DEFAULT_TARGETS = {
  trae: join(homedir(), ".trae", "skills"),
  codex: join(homedir(), ".agents", "skills"),
  "claude-code": join(homedir(), ".claude", "skills"),
};

const HELP = `用法:
  npx empirical-macro-skills [install|uninstall] --host <host> [选项]

宿主:
  generic | trae | codex | claude-code | openai4s

选项:
  --target-root <path>       普通 Agent 的 Skills 目录
  --manifest <path>          普通 Agent 卸载清单
  --openai4s-project <path>  OpenAI4S 项目目录
  --scope <personal|project> OpenAI4S 安装范围，默认 personal
  --project-id <id>          OpenAI4S project scope 标识
  --dry-run                  只检查，不写入
  --yes                      跳过交互确认
  --help                     显示帮助
`;

function parseArguments(argv) {
  const options = {
    operation: "install",
    host: null,
    targetRoot: null,
    manifest: null,
    openai4sProject: null,
    scope: "personal",
    projectId: null,
    dryRun: false,
    yes: false,
    help: false,
  };
  const values = [...argv];
  if (values[0] === "install" || values[0] === "uninstall") {
    options.operation = values.shift();
  }
  while (values.length > 0) {
    const flag = values.shift();
    if (flag === "--dry-run") {
      options.dryRun = true;
    } else if (flag === "--yes") {
      options.yes = true;
    } else if (flag === "--help" || flag === "-h") {
      options.help = true;
    } else if (flag === "--host") {
      options.host = requireValue(flag, values);
    } else if (flag === "--target-root") {
      options.targetRoot = requireValue(flag, values);
    } else if (flag === "--manifest") {
      options.manifest = requireValue(flag, values);
    } else if (flag === "--openai4s-project") {
      options.openai4sProject = requireValue(flag, values);
    } else if (flag === "--scope") {
      options.scope = requireValue(flag, values);
    } else if (flag === "--project-id") {
      options.projectId = requireValue(flag, values);
    } else {
      throw new Error(`未知参数: ${flag}`);
    }
  }
  return options;
}

function requireValue(flag, values) {
  const value = values.shift();
  if (!value || value.startsWith("--")) {
    throw new Error(`${flag} 缺少参数值`);
  }
  return value;
}

async function promptForMissingOptions(options) {
  if (options.host) {
    return options;
  }
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    throw new Error("非交互环境必须提供 --host");
  }
  const prompt = createInterface({ input: process.stdin, output: process.stdout });
  try {
    process.stdout.write("选择安装宿主:\n");
    HOSTS.forEach((host, index) => {
      process.stdout.write(`  ${index + 1}. ${host}\n`);
    });
    const selected = (await prompt.question("请输入序号: ")).trim();
    const index = Number.parseInt(selected, 10) - 1;
    if (!Number.isInteger(index) || !HOSTS[index]) {
      throw new Error("宿主序号无效");
    }
    options.host = HOSTS[index];
    if (options.host === "generic" && !options.targetRoot) {
      options.targetRoot = (await prompt.question("Skills 目标目录: ")).trim();
    }
    if (options.host === "openai4s" && !options.openai4sProject) {
      options.openai4sProject = (
        await prompt.question("OpenAI4S 项目目录: ")
      ).trim();
    }
    if (!options.dryRun && !options.yes) {
      const confirmed = (await prompt.question("确认执行安装？[y/N] ")).trim();
      if (!/^y(?:es)?$/i.test(confirmed)) {
        throw new Error("用户取消安装");
      }
    }
    return options;
  } finally {
    prompt.close();
  }
}

function validateOptions(options) {
  if (!HOSTS.includes(options.host)) {
    throw new Error(`不支持的宿主: ${options.host}`);
  }
  if (!["personal", "project"].includes(options.scope)) {
    throw new Error("--scope 只能是 personal 或 project");
  }
  if (options.host === "openai4s") {
    if (options.operation === "uninstall") {
      throw new Error("OpenAI4S 请使用平台 Skills UI 或 SkillVersionService 卸载");
    }
    if (!options.dryRun && !options.openai4sProject) {
      throw new Error("OpenAI4S 安装必须提供 --openai4s-project");
    }
    if (options.scope === "project" && !options.projectId) {
      throw new Error("OpenAI4S project scope 必须提供 --project-id");
    }
    return;
  }
  options.targetRoot ??= DEFAULT_TARGETS[options.host];
  if (!options.targetRoot) {
    throw new Error(`${options.host} 必须提供 --target-root`);
  }
  if (options.operation === "uninstall" && !options.manifest) {
    throw new Error("卸载必须提供 --manifest");
  }
}

function pythonCommand(options) {
  const project =
    options.host === "openai4s" && options.openai4sProject
      ? resolve(options.openai4sProject)
      : CORE_PROJECT;
  const installerArgs = [
    INSTALLER,
    options.operation,
    "--host",
    options.host,
  ];
  if (options.host === "openai4s") {
    installerArgs.push("--scope", options.scope);
    if (options.projectId) {
      installerArgs.push("--project-id", options.projectId);
    }
  } else {
    installerArgs.push("--target-root", resolve(options.targetRoot));
    if (options.manifest) {
      installerArgs.push("--manifest", resolve(options.manifest));
    }
  }
  if (options.dryRun) {
    installerArgs.push("--dry-run");
  }
  return [
    "run",
    "--isolated",
    "--project",
    project,
    "--locked",
    "--no-dev",
    "python",
    ...installerArgs,
  ];
}

async function main() {
  let options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(HELP);
    return 0;
  }
  options = await promptForMissingOptions(options);
  validateOptions(options);
  if (!options.yes && !options.dryRun && !process.stdin.isTTY) {
    throw new Error("非交互安装必须提供 --yes");
  }
  const result = spawnSync("uv", pythonCommand(options), {
    cwd: ROOT,
    env: process.env,
    stdio: "inherit",
  });
  if (result.error) {
    throw new Error(`无法启动 uv: ${result.error.message}`);
  }
  return result.status ?? 1;
}

try {
  process.exitCode = await main();
} catch (error) {
  process.stderr.write(`安装失败: ${error.message}\n`);
  process.exitCode = 1;
}
