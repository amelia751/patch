"use client";

/**
 * FileIcon - VS Code-style file type icons using simple-icons brand logos.
 *
 * Renders beautiful inline SVGs with official brand colors for 90+ file types.
 * Falls back to Lucide FileCode icon for unknown types.
 *
 * Usage:
 *   <FileIcon filename="app.py" size={14} />
 *   <FileIcon filename="Dockerfile" className="flex-shrink-0" />
 */

import {
  siPython, siTypescript, siJavascript, siDocker, siGo, siRust,
  siRuby, siPhp, siSwift, siKotlin, siDart, siCplusplus, siC,
  siHtml5, siCss, siJson, siYaml, siMarkdown, siGnubash, siReact,
  siVuedotjs, siSvelte, siTailwindcss, siNodedotjs, siFlask,
  siDjango, siToml, siPostgresql, siMysql, siGraphql, siDotnet,
  siLua, siR, siPerl, siHaskell, siElixir, siErlang, siScala,
  siTerraform, siNginx,
  siDotenv, siGit, siEslint, siYarn, siPnpm, siSvg, siXml,
  siPrettier, siEditorconfig, siJest, siVitest, siMocha,
  siWebpack, siVite, siRollupdotjs, siEsbuild, siBabel, siPostcss,
  siGithubactions, siApache,
} from "simple-icons";
import { FileCode } from "lucide-react";

// ============================================================================
// Icon data type
// ============================================================================

interface SimpleIconData {
  path: string;
  hex: string;
  title: string;
}

interface FileIconInfo {
  icon: SimpleIconData;
  colorOverride?: string; // Optional hex color override (without #)
}

// ============================================================================
// Extension → icon mapping
// ============================================================================

const EXT_ICON_MAP: Record<string, FileIconInfo> = {
  // Python
  py: { icon: siPython },
  pyw: { icon: siPython },
  pyi: { icon: siPython },
  pyx: { icon: siPython },
  // TypeScript
  ts: { icon: siTypescript },
  tsx: { icon: siReact },
  mts: { icon: siTypescript },
  cts: { icon: siTypescript },
  // JavaScript
  js: { icon: siJavascript },
  jsx: { icon: siReact },
  mjs: { icon: siJavascript },
  cjs: { icon: siJavascript },
  // Web
  html: { icon: siHtml5 },
  htm: { icon: siHtml5 },
  css: { icon: siCss },
  scss: { icon: siCss },
  sass: { icon: siCss },
  less: { icon: siCss },
  // Data
  json: { icon: siJson },
  yaml: { icon: siYaml },
  yml: { icon: siYaml },
  toml: { icon: siToml },
  // Markdown
  md: { icon: siMarkdown, colorOverride: "5B8DEE" }, // Nice blue for docs
  mdx: { icon: siMarkdown, colorOverride: "5B8DEE" },
  // Shell
  sh: { icon: siGnubash },
  bash: { icon: siGnubash },
  zsh: { icon: siGnubash },
  fish: { icon: siGnubash },
  // Systems
  go: { icon: siGo },
  rs: { icon: siRust },
  c: { icon: siC },
  h: { icon: siC },
  cpp: { icon: siCplusplus },
  cc: { icon: siCplusplus },
  cxx: { icon: siCplusplus },
  hpp: { icon: siCplusplus },
  // JVM
  kt: { icon: siKotlin },
  kts: { icon: siKotlin },
  scala: { icon: siScala },
  // Mobile
  swift: { icon: siSwift },
  dart: { icon: siDart },
  // Scripting
  rb: { icon: siRuby },
  php: { icon: siPhp },
  lua: { icon: siLua },
  r: { icon: siR },
  pl: { icon: siPerl },
  pm: { icon: siPerl },
  // Functional
  hs: { icon: siHaskell },
  ex: { icon: siElixir },
  exs: { icon: siElixir },
  erl: { icon: siErlang },
  // .NET
  cs: { icon: siDotnet },
  fs: { icon: siDotnet },
  vb: { icon: siDotnet },
  // Frameworks
  vue: { icon: siVuedotjs },
  svelte: { icon: siSvelte },
  // DevOps / Config
  dockerfile: { icon: siDocker },
  tf: { icon: siTerraform },
  hcl: { icon: siTerraform },
  // Database
  sql: { icon: siPostgresql },
  graphql: { icon: siGraphql },
  gql: { icon: siGraphql },
  // Environment / Config
  env: { icon: siDotenv },
  xml: { icon: siXml },
  svg: { icon: siSvg },
  // Nginx / Apache
  conf: { icon: siNginx },
};

// ============================================================================
// Full-filename → icon mapping (checked before extension)
// ============================================================================

const FILENAME_ICON_MAP: Record<string, FileIconInfo> = {
  // Docker
  dockerfile: { icon: siDocker },
  "docker-compose.yml": { icon: siDocker },
  "docker-compose.yaml": { icon: siDocker },
  ".dockerignore": { icon: siDocker },
  // Node / JS ecosystem
  "package.json": { icon: siNodedotjs },
  "package-lock.json": { icon: siNodedotjs },
  "tsconfig.json": { icon: siTypescript },
  "tailwind.config.js": { icon: siTailwindcss },
  "tailwind.config.ts": { icon: siTailwindcss },
  "postcss.config.js": { icon: siPostcss },
  "postcss.config.ts": { icon: siPostcss },
  "babel.config.js": { icon: siBabel },
  "babel.config.json": { icon: siBabel },
  ".babelrc": { icon: siBabel },
  "webpack.config.js": { icon: siWebpack },
  "webpack.config.ts": { icon: siWebpack },
  "vite.config.js": { icon: siVite },
  "vite.config.ts": { icon: siVite },
  "rollup.config.js": { icon: siRollupdotjs },
  "rollup.config.ts": { icon: siRollupdotjs },
  "esbuild.config.js": { icon: siEsbuild },
  // Linters / Formatters
  ".eslintrc": { icon: siEslint },
  ".eslintrc.js": { icon: siEslint },
  ".eslintrc.json": { icon: siEslint },
  ".eslintrc.yml": { icon: siEslint },
  "eslint.config.js": { icon: siEslint },
  "eslint.config.ts": { icon: siEslint },
  ".prettierrc": { icon: siPrettier },
  ".prettierrc.json": { icon: siPrettier },
  ".prettierrc.js": { icon: siPrettier },
  "prettier.config.js": { icon: siPrettier },
  ".editorconfig": { icon: siEditorconfig },
  // Testing
  "jest.config.js": { icon: siJest },
  "jest.config.ts": { icon: siJest },
  "vitest.config.js": { icon: siVitest },
  "vitest.config.ts": { icon: siVitest },
  ".mocharc.yml": { icon: siMocha },
  // Git
  ".gitignore": { icon: siGit },
  ".gitattributes": { icon: siGit },
  ".gitmodules": { icon: siGit },
  // Environment
  ".env": { icon: siDotenv },
  ".env.local": { icon: siDotenv },
  ".env.development": { icon: siDotenv },
  ".env.production": { icon: siDotenv },
  ".env.example": { icon: siDotenv },
  // Python
  "requirements.txt": { icon: siPython },
  "setup.py": { icon: siPython },
  "setup.cfg": { icon: siPython },
  "pyproject.toml": { icon: siPython },
  "pipfile": { icon: siPython },
  "manage.py": { icon: siDjango },
  "settings.py": { icon: siDjango },
  "app.py": { icon: siFlask },
  // Ruby
  "gemfile": { icon: siRuby },
  "rakefile": { icon: siRuby },
  // Rust / Go
  "cargo.toml": { icon: siRust },
  "cargo.lock": { icon: siRust },
  "go.mod": { icon: siGo },
  "go.sum": { icon: siGo },
  // Package managers
  "yarn.lock": { icon: siYarn },
  "pnpm-lock.yaml": { icon: siPnpm },
  ".npmrc": { icon: siNodedotjs },
  ".yarnrc": { icon: siYarn },
  ".yarnrc.yml": { icon: siYarn },
  // DevOps
  "nginx.conf": { icon: siNginx },
  "main.tf": { icon: siTerraform },
  ".github": { icon: siGithubactions },
  // Apache
  ".htaccess": { icon: siApache },
  "httpd.conf": { icon: siApache },
};

// ============================================================================
// Lookup function (exported for non-component usage)
// ============================================================================

export function getFileIconInfo(filename: string): FileIconInfo | null {
  const lower = filename.toLowerCase();

  // 1. Check full filename match
  const filenameMatch = FILENAME_ICON_MAP[lower];
  if (filenameMatch) return filenameMatch;

  // 2. Check file extension
  const ext = lower.split(".").pop() || "";
  const extMatch = EXT_ICON_MAP[ext];
  if (extMatch) return extMatch;

  return null;
}

// ============================================================================
// React component
// ============================================================================

interface FileIconProps {
  /** Filename or path — only the basename is used for matching */
  filename: string;
  /** Icon size in px (default 14) */
  size?: number;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Renders the correct brand-colored SVG icon for a file type.
 * Uses simple-icons for 90+ file types, falls back to Lucide FileCode.
 */
export function FileIcon({ filename, size = 14, className = "" }: FileIconProps) {
  // Use basename for matching
  const basename = filename.split("/").pop() || filename;
  const iconInfo = getFileIconInfo(basename);

  if (iconInfo) {
    const color = iconInfo.colorOverride || iconInfo.icon.hex;
    return (
      <svg
        className={`flex-shrink-0 ${className}`}
        style={{ width: size, height: size }}
        role="img"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path d={iconInfo.icon.path} fill={`#${color}`} />
      </svg>
    );
  }

  return <FileCode className={`flex-shrink-0 ${className}`} style={{ width: size, height: size, color: "var(--text-secondary)" }} />;
}
