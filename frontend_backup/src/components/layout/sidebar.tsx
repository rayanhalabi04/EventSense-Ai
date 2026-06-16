import { BrandMark } from "@/components/layout/brand-mark";
import { NAV_ITEMS } from "@/components/layout/nav";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";
import { NavLink } from "react-router-dom";

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  const isManager = user?.role === "manager" || user?.role === "platform_admin";
  const items = NAV_ITEMS.filter((item) => !item.managerOnly || isManager);

  return (
    <nav className="flex flex-1 flex-col gap-1 px-3 py-4" aria-label="Primary">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                "text-sidebar-foreground/75 hover:bg-white/5 hover:text-sidebar-foreground",
                isActive && "bg-white/10 text-sidebar-foreground shadow-sm ring-1 ring-white/5",
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={cn(
                    "h-[18px] w-[18px] shrink-0 transition-colors",
                    isActive ? "text-sidebar-accent" : "text-sidebar-muted",
                  )}
                />
                {item.label}
              </>
            )}
          </NavLink>
        );
      })}
    </nav>
  );
}

/** Static desktop sidebar (hidden on small screens; Topbar provides a mobile drawer). */
export function Sidebar() {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
      <div className="flex h-16 items-center border-b border-sidebar-border px-5">
        <BrandMark tone="dark" />
      </div>
      <SidebarNav />
      <div className="border-t border-sidebar-border px-5 py-4">
        <p className="text-xs text-sidebar-muted">
          AI assists. <span className="text-sidebar-foreground/90">Staff stays in control.</span>
        </p>
      </div>
    </aside>
  );
}
