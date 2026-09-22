const paths: Record<string, string> = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  pulse: "M2 12h5l3-8 4 16 3-8h5",
  layers: "m12 3 10 5-10 5L2 8z M2 12l10 5 10-5 M2 16l10 5 10-5",
  clock: "M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  bolt: "m13 2-9 12h7l-1 8 10-12h-7z",
  arrow: "M5 12h14 m-5-5 5 5-5 5",
  down: "m6 9 6 6 6-6",
  plus: "M12 5v14 M5 12h14",
  search: "m21 21-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  check: "m5 12 4 4L19 6",
  x: "m6 6 12 12 M6 18 18 6",
  shield: "m12 3 9 4v6c0 5-9 9-9 9s-9-4-9-9V7z m-4 9 3 3 5-6",
  code: "m8 5-7 7 7 7 m8-14 7 7-7 7 m-3-16-2 18",
  log: "M4 3h16v18H4z M8 7h8 M8 12h8 M8 17h5",
  external: "M14 3h7v7 M21 3 10 14 M10 3H3v18h18v-7",
  logout: "M9 3H3v18h6 M9 12h12 m-5-5 5 5-5 5",
  retry: "M3 11a9 9 0 1 1 2 7 M3 4v7h7",
  alert: "m12 3 10 18H2z M12 9v5 M12 17v1",
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M20 21v-2a4 4 0 0 0-3-4 M16 3a4 4 0 0 1 0 8",
};
export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.pulse} />
    </svg>
  );
}
