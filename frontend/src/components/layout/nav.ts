import {
  ClipboardList,
  FileText,
  Inbox,
  LayoutDashboard,
  type LucideIcon,
  ScrollText,
  ShieldAlert,
  TestTubeDiagonal,
} from "lucide-react";

interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  /** Show this item only to managers/admins. */
  managerOnly?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", to: "/", icon: LayoutDashboard },
  { label: "Inbox", to: "/inbox", icon: Inbox },
  { label: "Documents", to: "/documents", icon: FileText },
  { label: "Tasks", to: "/tasks", icon: ClipboardList },
  { label: "Escalations", to: "/escalations", icon: ShieldAlert },
  { label: "Audit Logs", to: "/audit-logs", icon: ScrollText, managerOnly: true },
  { label: "Evaluation", to: "/evaluation", icon: TestTubeDiagonal },
];
