// One-time generator for messages/zh-Hant.json from messages/zh.json.
// Run: node scripts/generate-zh-hant.mjs
// opencc-js is a devDependency used only by this script — not a runtime dependency.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import * as OpenCC from 'opencc-js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const srcPath = join(__dirname, '..', 'messages', 'zh.json');
const outPath = join(__dirname, '..', 'messages', 'zh-Hant.json');

const converter = OpenCC.Converter({ from: 'cn', to: 'twp' });

// Domain-specific overrides: s2twp mistranslates these in this product's
// context (film/comic production terms, not the generic tech meaning).
const PHRASE_OVERRIDES = [
    ['指令碼', '腳本'], // '脚本' here means film/comic script, not a code script
    ['型別', '類型'],   // s2twp maps '类型' to the CS-jargon '型別'; this product means the everyday '類型'
];

function convert(text) {
    let result = converter(text);
    for (const [from, to] of PHRASE_OVERRIDES) {
        result = result.split(from).join(to);
    }
    return result;
}

function walk(node) {
    if (typeof node === 'string') return convert(node);
    if (Array.isArray(node)) return node.map(walk);
    if (node !== null && typeof node === 'object') {
        const out = {};
        for (const [k, v] of Object.entries(node)) out[k] = walk(v);
        return out;
    }
    return node;
}

const zh = JSON.parse(readFileSync(srcPath, 'utf-8'));
const zhHant = walk(zh);
writeFileSync(outPath, JSON.stringify(zhHant, null, 2) + '\n', 'utf-8');
console.log(`Wrote ${outPath}`);
