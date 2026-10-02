"use client";
import { useId } from "react";
import {
  ArrowLeftRight, Bell, Check, CircleCheck, ChevronDown, ChevronLeft, ChevronRight, Clapperboard, Clock, Copy,
  Ellipsis, House, Inbox, LogOut, Mail, Play, Plus, RefreshCw, Settings, ShieldCheck, Sparkles, TriangleAlert,
  CalendarDays, Users, X, Zap, type LucideIcon,
} from "lucide-react";

const ICONS = {
  home: House,
  calendar: CalendarDays,
  film: Clapperboard,
  bolt: Zap,
  check: Check,
  checkCircle: CircleCheck,
  users: Users,
  sparkle: Sparkles,
  settings: Settings,
  bell: Bell,
  close: X,
  back: ChevronLeft,
  chevron: ChevronRight,
  chevronDown: ChevronDown,
  more: Ellipsis,
  logout: LogOut,
  refresh: RefreshCw,
  plus: Plus,
  copy: Copy,
  play: Play,
  alert: TriangleAlert,
  inbox: Inbox,
  clock: Clock,
  swap: ArrowLeftRight,
  mail: Mail,
  shield: ShieldCheck,
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof ICONS;

export function Icon({ name, size = 20, className }: { name: IconName; size?: number; className?: string }) {
  const Cmp = ICONS[name];
  return <Cmp size={size} strokeWidth={1.9} aria-hidden="true" focusable="false" className={className} />;
}

/** The CreatorOps mark: a play button with a spark, on the brand gradient (the only gradient in the app). */
export function Logo({ size = 32 }: { size?: number }) {
  // Unique id per instance: a gradient defined inside a display:none ancestor (the hidden sidebar) cannot be referenced.
  const gid = `lg${useId().replace(/:/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0a0a0a" />
          <stop offset="1" stopColor="#e11d12" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill={`url(#${gid})`} />
      <path d="M24 17v30l23-15L24 17Z" fill="#fff" />
      <path d="M46 8l2.2 5.4 5.4 2.2-5.4 2.2L46 23.2l-2.2-5.4-5.4-2.2 5.4-2.2L46 8Z" fill="#fff" opacity=".92" />
    </svg>
  );
}
