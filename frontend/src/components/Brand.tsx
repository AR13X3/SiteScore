/** The SiteScore mark: a map pin on a solid square. Monochrome, follows the text colour. */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="logo">
      <rect width="32" height="32" rx="8" fill="currentColor" />
      <path
        d="M16 25.5s-6.5-5.8-6.5-10.8a6.5 6.5 0 0 1 13 0c0 5-6.5 10.8-6.5 10.8z"
        fill="none"
        stroke="var(--logo-ink)"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="14.6" r="2.2" fill="var(--logo-ink)" />
    </svg>
  );
}
