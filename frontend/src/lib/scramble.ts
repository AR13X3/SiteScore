// "Decoding" text: characters settle left to right out of random glyphs.

const GLYPHS = "abcdefghijklmnopqrstuvwxyz0123456789/_-=+<>[]{}#$%*";

/**
 * The text at `progress` (0..1) through the decode. Characters before the settled point
 * are final; a short band after it flickers through glyphs; the rest is blank, so the
 * line grows as it resolves. Spaces and punctuation that frame the text stay put.
 */
export function scrambleFrame(text: string, progress: number, rand: () => number = Math.random): string {
  const n = text.length;
  const settled = Math.floor(Math.max(0, Math.min(1, progress)) * n);
  const band = Math.max(3, Math.round(n * 0.25));
  let out = "";
  for (let i = 0; i < n; i++) {
    const c = text[i];
    if (i < settled || c === " ") out += c;
    else if (i < settled + band) out += GLYPHS[Math.floor(rand() * GLYPHS.length)];
    else out += " ";
  }
  return out;
}

/**
 * Every number in `text` counted up to `progress` (0..1, eased), keeping its decimals
 * and thousands separators: "0 of 25", "60%", "0.70", "86,700 rows".
 */
export function countFrame(text: string, progress: number): string {
  const p = Math.max(0, Math.min(1, progress));
  const e = 1 - (1 - p) ** 3;
  return text.replace(/\d[\d,]*(?:\.\d+)?/g, (m) => {
    const decimals = (m.split(".")[1] ?? "").length;
    const v = Number.parseFloat(m.replace(/,/g, "")) * e;
    return m.includes(",")
      ? v.toLocaleString("en-AU", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
      : v.toFixed(decimals);
  });
}
