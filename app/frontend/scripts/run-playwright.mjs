import { spawnSync } from 'node:child_process';
import { existsSync, realpathSync } from 'node:fs';
import { join } from 'node:path';
import process from 'node:process';

const supportedMajorVersions = new Set([18, 20, 22]);
const currentMajor = Number.parseInt(process.versions.node.split('.')[0] ?? '', 10);
const playwrightCli = join(process.cwd(), 'node_modules', 'playwright', 'cli.js');

function normalizeLocalProxyEnv(env) {
  const next = { ...env };
  for (const key of ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']) {
    delete next[key];
  }
  next.NO_PROXY = mergeNoProxy(next.NO_PROXY);
  next.no_proxy = mergeNoProxy(next.no_proxy);
  return next;
}

function mergeNoProxy(value) {
  const entries = new Set(
    String(value ?? '')
      .split(',')
      .map((entry) => entry.trim())
      .filter(Boolean)
  );
  entries.add('127.0.0.1');
  entries.add('localhost');
  return Array.from(entries).join(',');
}

function findFallbackNode() {
  if (process.platform === 'win32') return null;

  const fallback = '/usr/bin/node';
  if (!existsSync(fallback)) return null;

  const currentPath = realpathSync(process.execPath);
  const fallbackPath = realpathSync(fallback);
  if (fallbackPath === currentPath) return null;

  const result = spawnSync(fallback, ['-p', 'process.versions.node.split(".")[0]'], {
    encoding: 'utf8'
  });
  const major = Number.parseInt(result.stdout.trim(), 10);
  return supportedMajorVersions.has(major) ? fallback : null;
}

function run(nodePath) {
  const result = spawnSync(nodePath, [playwrightCli, ...process.argv.slice(2)], {
    cwd: process.cwd(),
    env: normalizeLocalProxyEnv(process.env),
    stdio: 'inherit'
  });
  process.exit(result.status ?? 1);
}

if (supportedMajorVersions.has(currentMajor)) {
  run(process.execPath);
}

const fallbackNode = findFallbackNode();
if (fallbackNode) {
  run(fallbackNode);
}

console.error(
  `Playwright E2E requires Node 18, 20, or 22. Current Node is ${process.versions.node}.`
);
process.exit(1);
