import { useState } from "react";
import { useAuth, useFetcher } from "@asunset/web-sdk";
import { useQuery } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Mail } from "lucide-react";

import { api } from "@/api";
import { useT } from "@/lib/useT";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function UserCombobox({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (email: string) => void;
  disabled?: boolean;
}) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const auth = useAuth();
  const f = useFetcher();
  const membersQ = useQuery({
    queryKey: ["org-members"],
    queryFn: () => api.listOrgMembers(f),
    enabled: open && !!auth.user,
    staleTime: 60_000,
  });

  const members = membersQ.data ?? [];
  const trimmed = query.trim();
  const isValidEmail = EMAIL_RE.test(trimmed);
  const alreadyInList = members.some(
    (m) => m.user.email.toLowerCase() === trimmed.toLowerCase(),
  );
  const showFreeText = trimmed.length > 0 && isValidEmail && !alreadyInList;

  const selectedMember = value
    ? members.find((m) => m.user.email.toLowerCase() === value.toLowerCase())
    : undefined;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className="h-10 w-full justify-between font-normal"
        >
          {value ? (
            <span className="flex min-w-0 items-center gap-2">
              {selectedMember ? (
                <Avatar className="size-5">
                  <AvatarFallback className="text-[10px]">
                    {initials(selectedMember.user.display_name)}
                  </AvatarFallback>
                </Avatar>
              ) : (
                <Mail className="size-4 text-muted-foreground" />
              )}
              <span className="truncate">
                {selectedMember?.user.display_name ?? value}
              </span>
            </span>
          ) : (
            <span className="text-muted-foreground">
              {t("combobox.trigger")}
            </span>
          )}
          <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[--radix-popover-trigger-width] p-0"
        align="start"
      >
        <Command shouldFilter={true}>
          <CommandInput
            placeholder={t("combobox.search")}
            value={query}
            onValueChange={setQuery}
          />
          <CommandList>
            <CommandEmpty>
              {membersQ.isLoading
                ? t("combobox.loading")
                : showFreeText
                  ? null
                  : t("combobox.noMatches")}
            </CommandEmpty>
            {members.length > 0 && (
              <CommandGroup heading={t("combobox.groupMembers")}>
                {members.map((m) => (
                  <CommandItem
                    key={m.user.id}
                    value={`${m.user.display_name} ${m.user.email}`}
                    onSelect={() => {
                      onChange(m.user.email);
                      setOpen(false);
                    }}
                  >
                    <Avatar className="size-6">
                      <AvatarFallback className="text-[10px]">
                        {initials(m.user.display_name)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sm">
                        {m.user.display_name}
                      </span>
                      <span className="truncate text-xs text-muted-foreground">
                        {m.user.email}
                      </span>
                    </div>
                    <Check
                      className={cn(
                        "size-4",
                        value.toLowerCase() === m.user.email.toLowerCase()
                          ? "opacity-100"
                          : "opacity-0",
                      )}
                    />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {showFreeText && (
              <CommandGroup heading={t("combobox.groupInvite")}>
                <CommandItem
                  value={trimmed}
                  onSelect={() => {
                    onChange(trimmed);
                    setOpen(false);
                  }}
                >
                  <Mail className="size-4 text-muted-foreground" />
                  <span className="truncate">
                    {t("combobox.inviteLabel", { email: trimmed })}
                  </span>
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("");
}
