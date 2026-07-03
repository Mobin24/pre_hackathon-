// Lightweight class-name merge (shadcn pattern).
// No clsx/tailwind-merge dep — just filter + join. Good enough for hackathon.

export function cn(...inputs) {
  return inputs
    .flat()
    .filter((x) => typeof x === 'string' && x.length > 0)
    .join(' ');
}