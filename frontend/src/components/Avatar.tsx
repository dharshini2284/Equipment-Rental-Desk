// Coloured initials for members and items. The colour is picked from the text, so the
// same member or category always gets the same colour.

const HUES = [160, 200, 250, 290, 330, 20, 40, 100];

function hueFor(text: string): number {
  let hash = 0;
  for (const char of text) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return HUES[Math.abs(hash) % HUES.length] ?? HUES[0]!;
}

function initials(text: string): string {
  const words = text.split(/\s+/).filter((word) => /^[A-Za-z]/.test(word));
  return (
    words
      .slice(0, 2)
      .map((word) => word[0]!.toUpperCase())
      .join("") || "?"
  );
}

interface Props {
  label: string;
  /** Text that decides the colour; defaults to the label. Items use their category. */
  colorKey?: string;
  size?: "sm" | "md" | "lg";
}

export function Avatar({ label, colorKey, size = "md" }: Props) {
  const hue = hueFor(colorKey ?? label);
  return (
    <span
      className={`avatar avatar-${size}`}
      style={{ background: `hsl(${hue} 70% 92%)`, color: `hsl(${hue} 55% 30%)` }}
      aria-hidden="true"
    >
      {initials(label)}
    </span>
  );
}
