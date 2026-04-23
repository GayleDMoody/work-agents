/**
 * Inline SVG logos for each connector — simplified official brand marks.
 * No external assets needed.
 */

const S = 24; // default size

interface P { size?: number; }

export function JiraLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <defs><linearGradient id="jg1" x1="60%" y1="0%" x2="20%" y2="100%"><stop offset="0%" stopColor="#2684FF"/><stop offset="100%" stopColor="#0052CC"/></linearGradient></defs>
      <path d="M27.1 15.1L17 5l-1 -1-9.1 9.1a1 1 0 000 1.4L14.5 22 16 20.5l-5.6-5.6L16 9.3l5.6 5.6z" fill="url(#jg1)"/>
      <path d="M16 13.5L10.4 19.1a1 1 0 000 1.4L16 26l5.6-5.6a1 1 0 000-1.4z" fill="#2684FF"/>
    </svg>
  );
}

export function LinearLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <path d="M3.5 18.9a13 13 0 009.6 9.6L3.5 18.9z" fill="#5E6AD2"/>
      <path d="M3 16.1a13 13 0 003.3 9.8L3 16.1zM6.1 26a13 13 0 009.8 3.3L6.1 26z" fill="#5E6AD2" opacity=".7"/>
      <circle cx="16" cy="16" r="8" stroke="#5E6AD2" strokeWidth="2.5" fill="none"/>
    </svg>
  );
}

export function AsanaLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <circle cx="16" cy="10" r="5" fill="#F06A6A"/>
      <circle cx="8" cy="22" r="5" fill="#F06A6A"/>
      <circle cx="24" cy="22" r="5" fill="#F06A6A"/>
    </svg>
  );
}

export function GitHubLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size}>
      <path fillRule="evenodd" clipRule="evenodd" d="M16 3C8.8 3 3 8.8 3 16c0 5.7 3.7 10.6 8.9 12.3.6.1.9-.3.9-.6v-2.2c-3.6.8-4.4-1.7-4.4-1.7-.6-1.5-1.4-1.9-1.4-1.9-1.2-.8.1-.8.1-.8 1.3.1 2 1.3 2 1.3 1.1 2 3 1.4 3.7 1.1.1-.8.5-1.4.8-1.7-2.9-.3-5.9-1.4-5.9-6.3 0-1.4.5-2.5 1.3-3.4-.1-.3-.6-1.6.1-3.3 0 0 1.1-.3 3.5 1.3a12 12 0 016.4 0c2.4-1.6 3.5-1.3 3.5-1.3.7 1.7.2 3 .1 3.3.8.9 1.3 2 1.3 3.4 0 4.9-3 6-5.9 6.3.5.4.9 1.2.9 2.4v3.5c0 .3.3.7.9.6C25.3 26.6 29 21.7 29 16c0-7.2-5.8-13-13-13z" fill="#e6edf3"/>
    </svg>
  );
}

export function GitLabLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <path d="M16 27.5L20.5 14H11.5z" fill="#E24329"/>
      <path d="M16 27.5L11.5 14H4.5z" fill="#FC6D26"/>
      <path d="M4.5 14L3 18.6 16 27.5z" fill="#FCA326"/>
      <path d="M16 27.5L20.5 14H27.5z" fill="#FC6D26"/>
      <path d="M27.5 14L29 18.6 16 27.5z" fill="#FCA326"/>
      <path d="M3 18.6L2.3 16.4a1 1 0 01.4-1.1L16 5.5l0 0L4.5 14z" fill="#E24329"/>
      <path d="M29 18.6l.7-2.2a1 1 0 00-.4-1.1L16 5.5l0 0 13 8.5z" fill="#E24329"/>
    </svg>
  );
}

export function BitbucketLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <defs><linearGradient id="bg1" x1="100%" y1="30%" x2="40%" y2="100%"><stop offset="0%" stopColor="#0052CC"/><stop offset="100%" stopColor="#2684FF"/></linearGradient></defs>
      <path d="M5 6h22a1 1 0 011 1.1l-3 19a1 1 0 01-1 .9H8a1 1 0 01-1-.9L4 7.1A1 1 0 015 6z" fill="url(#bg1)"/>
      <path d="M19.5 17.5h-7l-1-6h9z" fill="#fff" opacity=".4"/>
    </svg>
  );
}

export function AnthropicLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <path d="M19 6h4l7 20h-4.5l-1.4-4.2h-7.2L18.3 26H14z" fill="#D4A574"/>
      <path d="M9 6h4.5l7 20H16l-1.4-4.2H7.4L6 26H2z" fill="#D4A574"/>
    </svg>
  );
}

export function OpenAILogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <path d="M27 13.5a7 7 0 00-1.2-7.3 7.2 7.2 0 00-7.6-2.7A7 7 0 0013 1a7.2 7.2 0 00-6.8 5 7 7 0 00-4.7 3.4 7.2 7.2 0 00.9 8.2A7 7 0 003.6 25a7.2 7.2 0 007.6 2.7A7 7 0 0019 31a7.2 7.2 0 006.8-5 7 7 0 004.7-3.4 7.2 7.2 0 00-.9-8.2z" stroke="#10A37F" strokeWidth="1.8" fill="none"/>
      <path d="M16 10v12M11 13l5-3 5 3M11 19l5 3 5-3" stroke="#10A37F" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

export function SlackLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <rect x="13" y="3" width="3" height="9" rx="1.5" fill="#E01E5A"/>
      <rect x="3" y="13" width="9" height="3" rx="1.5" fill="#36C5F0"/>
      <rect x="16" y="20" width="3" height="9" rx="1.5" fill="#2EB67D"/>
      <rect x="20" y="16" width="9" height="3" rx="1.5" fill="#ECB22E"/>
      <circle cx="10" cy="10" r="2" fill="#E01E5A"/>
      <circle cx="22" cy="10" r="2" fill="#36C5F0"/>
      <circle cx="10" cy="22" r="2" fill="#2EB67D"/>
      <circle cx="22" cy="22" r="2" fill="#ECB22E"/>
    </svg>
  );
}

export function DiscordLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <path d="M25 8.3A20 20 0 0020 6.5a.1.1 0 00-.1 0 14 14 0 00-.6 1.2 18 18 0 00-5.6 0A13 13 0 0013 6.5h-.1A20 20 0 007.7 8.3 21 21 0 004 24a20 20 0 006.2 3.1.1.1 0 00.1 0 14 14 0 001.2-2 .1.1 0 000-.1 13 13 0 01-1.9-.9.1.1 0 010-.1l.4-.3a14 14 0 0012 0l.4.3a.1.1 0 010 .1 13 13 0 01-1.9.9.1.1 0 000 .1 14 14 0 001.2 2h.1A20 20 0 0028 24a21 21 0 00-3-15.7z" fill="#5865F2"/>
      <circle cx="12.5" cy="17" r="2.2" fill="#fff"/>
      <circle cx="19.5" cy="17" r="2.2" fill="#fff"/>
    </svg>
  );
}

export function TeamsLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <rect x="4" y="8" width="18" height="16" rx="2" fill="#6264A7"/>
      <text x="10" y="19.5" fontSize="9" fontWeight="800" fill="#fff" fontFamily="sans-serif">T</text>
      <circle cx="25" cy="11" r="4" fill="#7B83EB"/>
      <rect x="21" y="16" width="8" height="8" rx="1.5" fill="#7B83EB"/>
    </svg>
  );
}

export function GHActionsLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <circle cx="16" cy="16" r="4" fill="#2088FF"/>
      <circle cx="8" cy="8" r="3" fill="#79B8FF"/>
      <circle cx="24" cy="8" r="3" fill="#79B8FF"/>
      <circle cx="8" cy="24" r="3" fill="#79B8FF"/>
      <path d="M10 10l4 4M22 10l-4 4M10 22l4-4" stroke="#79B8FF" strokeWidth="1.5"/>
    </svg>
  );
}

export function JenkinsLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <circle cx="16" cy="14" r="10" fill="#D33833"/>
      <circle cx="16" cy="14" r="7" fill="#F0D6B7"/>
      <circle cx="13.5" cy="12.5" r="1.2" fill="#333"/>
      <circle cx="18.5" cy="12.5" r="1.2" fill="#333"/>
      <path d="M13 17c1.3 1.5 4.7 1.5 6 0" stroke="#333" strokeWidth="1" fill="none" strokeLinecap="round"/>
      <rect x="12" y="6" width="8" height="3" rx="1" fill="#333"/>
    </svg>
  );
}

export function DatadogLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <path d="M22 8c-2-1-5 0-6.5 1.5S14 14 14 14l-3-1c-1 2 0 5 2 6.5s5 .5 6-1l2 1c1-2 2-5 1-7.5" stroke="#632CA6" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx="18" cy="13" r="1.5" fill="#632CA6"/>
    </svg>
  );
}

export function SentryLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <path d="M17.5 5.5a2 2 0 00-3.4 0L4 24h5.8a8 8 0 018-8v-3a5 5 0 00-5 5H9.5L16 8l4 7h-2.5" stroke="#362D59" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
    </svg>
  );
}

export function NotionLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <rect x="6" y="4" width="20" height="24" rx="3" stroke="#999" strokeWidth="2"/>
      <path d="M10 9h8l-5 14h-3z" fill="#999" opacity=".6"/>
      <path d="M14 9l8 0-5 14h3z" fill="#999" opacity=".3"/>
    </svg>
  );
}

export function ConfluenceLogo({ size = S }: P) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none">
      <defs><linearGradient id="cg1" x1="0%" y1="100%" x2="100%" y2="0%"><stop offset="0%" stopColor="#0052CC"/><stop offset="100%" stopColor="#2684FF"/></linearGradient></defs>
      <path d="M5 22c1-2 2.5-4.5 7-4.5s7 3 10 3 4-1 5-2l3 4c-1 2-3 4-8 4s-7-3-10-3-4 1-5 2z" fill="url(#cg1)"/>
      <path d="M27 10c-1 2-2.5 4.5-7 4.5s-7-3-10-3-4 1-5 2L2 9.5c1-2 3-4 8-4s7 3 10 3 4-1 5-2z" fill="#2684FF"/>
    </svg>
  );
}

// Logo resolver
const LOGOS: Record<string, (p: P) => JSX.Element> = {
  jira: JiraLogo,
  linear: LinearLogo,
  asana: AsanaLogo,
  github: GitHubLogo,
  gitlab: GitLabLogo,
  bitbucket: BitbucketLogo,
  anthropic: AnthropicLogo,
  openai: OpenAILogo,
  slack: SlackLogo,
  discord: DiscordLogo,
  teams: TeamsLogo,
  github_actions: GHActionsLogo,
  jenkins: JenkinsLogo,
  datadog: DatadogLogo,
  sentry: SentryLogo,
  notion: NotionLogo,
  confluence: ConfluenceLogo,
};

export default function ConnectorLogo({ id, size = 24 }: { id: string; size?: number }) {
  const Logo = LOGOS[id];
  if (!Logo) return <span style={{ fontSize: size * 0.8 }}>?</span>;
  return <Logo size={size} />;
}
