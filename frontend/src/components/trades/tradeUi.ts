/**
 * Shared presentation helpers for the Trades page (trades, partners, ROI, waivers).
 *
 * Design language: flat surfaces, hairline dividers, color reserved for meaning
 * (position, grade, gain/loss). Keep these helpers the single source of truth so
 * every sub-tab renders positions, grades and signed numbers identically.
 */

/** Text-only position color (no pill backgrounds). */
export function positionTextClass(pos: string | null | undefined): string {
  switch ((pos || '').toUpperCase()) {
    case 'QB':
      return 'text-rose-300';
    case 'RB':
      return 'text-emerald-300';
    case 'WR':
      return 'text-sky-300';
    case 'TE':
      return 'text-amber-300';
    case 'K':
      return 'text-purple-300';
    case 'PICK':
      return 'text-violet-300';
    default:
      return 'text-slate-400';
  }
}

/** Letter-grade tile colors (text + subtle tinted background). */
export function gradeTileClass(grade: string | null | undefined): string {
  const g = (grade || '').toUpperCase();
  if (g.startsWith('A')) return 'text-emerald-300 bg-emerald-500/10';
  if (g.startsWith('B')) return 'text-sky-300 bg-sky-500/10';
  if (g.startsWith('C')) return 'text-amber-300 bg-amber-500/10';
  if (!g) return 'text-slate-500 bg-slate-800/60';
  return 'text-rose-300 bg-rose-500/10';
}

/** Signed number formatting with a real minus sign, e.g. +6.9 / −14.4. */
export function signed(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return '0';
  const abs = Math.abs(value).toFixed(digits);
  if (value > 0) return `+${abs}`;
  if (value < 0) return `\u2212${abs}`;
  return abs;
}

/** Color for a signed value: positive = turf, negative = coral, zero = muted. */
export function signedClass(value: number): string {
  if (value > 0.05) return 'text-emerald-400';
  if (value < -0.05) return 'text-rose-400';
  return 'text-slate-400';
}

export function weekLabel(week: number | null | undefined, long = false): string {
  if (week == null) return '';
  if (week === 0) return long ? 'Preseason' : 'Pre';
  return long ? `Week ${week}` : `Wk ${week}`;
}

export function shortDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

/** Strip the "Tier N – " prefix so tier labels read as plain language. */
export function tierText(label: string | null | undefined): string {
  if (!label) return '';
  return label.replace(/^Tier\s*\d+\s*[–-]\s*/i, '');
}

/** Abbreviate long player names for tight spaces: "Amon-Ra St. Brown" -> "A. St. Brown". */
export function compactName(fullName: string, max = 16): string {
  if (!fullName) return '';
  if (fullName.length <= max) return fullName;
  const parts = fullName.trim().split(/\s+/);
  if (parts.length >= 2) return `${parts[0][0]}. ${parts.slice(1).join(' ')}`;
  return fullName;
}
