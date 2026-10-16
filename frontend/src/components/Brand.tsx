/**
 * The SiteScore mark: three cells of the opportunity map, one picked. The two ink
 * cells follow the text colour; the picked cell is the red signal.
 */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="logo">
      <path d="M10.2 4.5l5.54 3.2v6.4l-5.54 3.2-5.54-3.2V7.7z" fill="currentColor" />
      <path d="M21.8 4.5l5.54 3.2v6.4l-5.54 3.2-5.54-3.2V7.7z" fill="currentColor" />
      <path d="M16 14.7l5.54 3.2v6.4L16 27.5l-5.54-3.2v-6.4z" fill="var(--signal)" />
    </svg>
  );
}

/** Mark + wordmark. */
export function Wordmark() {
  return (
    <span className="wordmark">
      <Logo size={28} />
      <span className="wordmark__name">sitescore</span>
    </span>
  );
}
