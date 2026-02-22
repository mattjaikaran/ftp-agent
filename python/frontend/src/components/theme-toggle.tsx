import { useTheme } from "@/hooks/use-theme";
import { Sun, Moon, Monitor } from "lucide-react";
import { cn } from "@/lib/cn";

const OPTIONS = [
  { value: "light" as const, icon: Sun, label: "Light" },
  { value: "dark" as const, icon: Moon, label: "Dark" },
  { value: "system" as const, icon: Monitor, label: "System" },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex items-center rounded-lg border border-border bg-bg-inset p-0.5">
      {OPTIONS.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          title={label}
          className={cn(
            "rounded-md p-1.5 transition-colors",
            theme === value
              ? "bg-bg-card text-text shadow-sm"
              : "text-text-muted hover:text-text-secondary",
          )}
        >
          <Icon className="h-3.5 w-3.5" />
        </button>
      ))}
    </div>
  );
}
