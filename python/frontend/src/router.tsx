import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  Link,
} from "@tanstack/react-router";
import { LlmStatus } from "@/components/llm-status";
import { ThemeToggle } from "@/components/theme-toggle";
import { useHealth } from "@/hooks/use-health";
import { triggerRun, stopRun } from "@/lib/api";
import { Play, Square, Activity } from "lucide-react";
import { DashboardPage } from "@/routes/dashboard";
import { EntriesPage } from "@/routes/entries";
import { EntryDetailPage } from "@/routes/entry-detail";
import { SettingsPage } from "@/routes/settings";

// Root layout
function RootLayout() {
  const { data: health } = useHealth();

  return (
    <div className="min-h-screen bg-bg">
      <header className="border-b border-border bg-bg-card">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <Activity className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold text-text">FTP Agent</h1>
            {health && (
              <span className="rounded-md bg-bg-inset px-2 py-0.5 text-xs text-text-muted">
                v{health.version}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <LlmStatus />
            <button
              onClick={() => triggerRun(true)}
              className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover"
            >
              <Play className="h-4 w-4" />
              Run (Dry)
            </button>
            <button
              onClick={() => stopRun()}
              className="flex items-center gap-1.5 rounded-lg border border-border bg-bg-card px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-bg-inset"
            >
              <Square className="h-4 w-4" />
              Stop
            </button>
          </div>
        </div>
        <div className="mx-auto max-w-7xl px-6">
          <nav className="flex gap-6 text-sm">
            <Link
              to="/"
              className="border-b-2 pb-2 font-medium transition-colors"
              activeProps={{ className: "border-primary text-primary" }}
              inactiveProps={{ className: "border-transparent text-text-muted hover:text-text-secondary" }}
            >
              Dashboard
            </Link>
            <Link
              to="/entries"
              className="border-b-2 pb-2 font-medium transition-colors"
              activeProps={{ className: "border-primary text-primary" }}
              inactiveProps={{ className: "border-transparent text-text-muted hover:text-text-secondary" }}
            >
              Entries
            </Link>
            <Link
              to="/settings"
              className="border-b-2 pb-2 font-medium transition-colors"
              activeProps={{ className: "border-primary text-primary" }}
              inactiveProps={{ className: "border-transparent text-text-muted hover:text-text-secondary" }}
            >
              Settings
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 p-6">
        <Outlet />
      </main>
    </div>
  );
}

// Route definitions
const rootRoute = createRootRoute({ component: RootLayout });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: DashboardPage,
});

const entriesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/entries",
  component: EntriesPage,
});

const entryDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/entries/$entryId",
  component: EntryDetailPage,
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: SettingsPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  entriesRoute,
  entryDetailRoute,
  settingsRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
