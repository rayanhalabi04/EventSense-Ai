import { BrandMark } from "@/components/layout/brand-mark";
import { SidebarNav } from "@/components/layout/sidebar";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTenant } from "@/hooks/queries";
import { useAuth } from "@/hooks/use-auth";
import { humanize, initials } from "@/lib/format";
import { LogOut, Menu } from "lucide-react";
import { useState } from "react";

export function Topbar() {
  const { user, logout } = useAuth();
  const { data: tenant } = useTenant();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-border bg-background/85 px-4 backdrop-blur lg:px-8">
      <div className="flex items-center gap-3">
        {/* Mobile menu */}
        <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu">
              <Menu />
            </Button>
          </DialogTrigger>
          <DialogContent className="left-0 top-0 h-full max-w-[17rem] translate-x-0 translate-y-0 rounded-none border-r bg-sidebar p-0">
            <div className="flex h-16 items-center border-b border-sidebar-border px-5">
              <BrandMark tone="dark" />
            </div>
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </DialogContent>
        </Dialog>

        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">
            {tenant?.name ?? "EventSense AI"}
          </p>
          <p className="text-xs text-muted-foreground">Operations workspace</p>
        </div>
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex items-center gap-2 rounded-full p-1 pr-2 transition-colors hover:bg-secondary"
          >
            <Avatar>
              <AvatarFallback>{user ? initials(user.full_name) : "ES"}</AvatarFallback>
            </Avatar>
            <span className="hidden text-left sm:block">
              <span className="block text-sm font-medium leading-tight text-foreground">
                {user?.full_name ?? "Account"}
              </span>
              <span className="block text-xs leading-tight text-muted-foreground">
                {user ? humanize(user.role) : ""}
              </span>
            </span>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel>
            <span className="block text-sm font-medium text-foreground">{user?.full_name}</span>
            <span className="block truncate text-xs font-normal text-muted-foreground">
              {user?.email}
            </span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
            <LogOut /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
