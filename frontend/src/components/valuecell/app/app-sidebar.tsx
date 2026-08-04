import { ChevronDown, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { type FC, memo, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation, useNavigate } from "react-router";
import { useGetAgentList } from "@/api/agent";
import {
  Analysis,
  Conversation,
  Knowledge,
  Market,
  NewConversation,
  Portfolio,
  Setting,
} from "@/assets/svg";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar";
import AppConversationSheet from "@/components/valuecell/app/app-conversation-sheet";
import AgentAvatar from "@/components/valuecell/icon/agent-avatar";
import SvgIcon from "@/components/valuecell/icon/svg-icon";
import { cn } from "@/lib/utils";

const AppSidebar: FC = () => {
  const { t } = useTranslation();
  const { state, toggleSidebar } = useSidebar();
  const isCollapsed = state === "collapsed";
  const navigate = useNavigate();
  const pathArray = useLocation().pathname.split("/");

  const prefix = (() => {
    const subPath = pathArray[1] ?? "";
    switch (subPath) {
      case "agent":
        return `/${subPath}/${pathArray[2]}`;
      default:
        return `/${subPath}`;
    }
  })();

  const [agentMarketOpen, setAgentMarketOpen] = useState(
    pathArray[1] === "agent" || pathArray[1] === "market",
  );

  const navItems = [
    {
      id: "analysis",
      icon: Analysis,
      label: t("nav.analysis"),
      to: "/analysis",
    },
    {
      id: "portfolio",
      icon: Portfolio,
      label: t("nav.portfolio"),
      to: "/portfolio",
    },
    {
      id: "knowledge",
      icon: Knowledge,
      label: t("nav.knowledge"),
      to: "/knowledge",
    },
  ];

  const { data: agentList } = useGetAgentList({ enabled_only: "true" });
  const agentItems =
    agentList?.map((agent) => ({
      id: agent.agent_name,
      label: agent.display_name,
      to: `/agent/${agent.agent_name}`,
    })) ?? [];

  const verifyActive = (to: string) => prefix === to;
  const isAgentMarketActive =
    pathArray[1] === "market" || pathArray[1] === "agent";

  return (
    <Sidebar collapsible="icon" className="border-r">
      <SidebarHeader>
        <div
          className={cn(
            "flex items-center gap-2 px-2 pt-2 pb-1",
            isCollapsed ? "flex-col gap-3" : "flex-row justify-between",
          )}
        >
          <NavLink
            to="/home"
            className={cn(
              "flex items-center gap-2 overflow-hidden",
              isCollapsed && "justify-center",
            )}
          >
            <span
              className={cn(
                "flex shrink-0 items-center justify-center",
                isCollapsed ? "size-9" : "size-8",
              )}
            >
              <img
                src="/logo.svg"
                alt="Valor"
                className="size-full rounded-md"
              />
            </span>
            {!isCollapsed && (
              <span className="font-semibold text-base tracking-wide">
                Valor
              </span>
            )}
          </NavLink>

          <button
            type="button"
            onClick={toggleSidebar}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md",
              "text-muted-foreground transition-colors",
              "hover:bg-accent hover:text-accent-foreground",
            )}
          >
            {isCollapsed ? (
              <PanelLeftOpen size={16} />
            ) : (
              <PanelLeftClose size={16} />
            )}
          </button>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  size="lg"
                  className="font-medium text-[15px]"
                  tooltip={t("nav.newConversation")}
                  onClick={() => navigate("/home")}
                >
                  <SvgIcon name={NewConversation} className="size-4 shrink-0" />
                  <span>{t("nav.newConversation")}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>

              {navItems.map((item) => (
                <SidebarMenuItem key={item.id}>
                  <SidebarMenuButton
                    asChild
                    isActive={verifyActive(item.to)}
                    size="lg"
                    className="text-[15px]"
                    tooltip={item.label}
                  >
                    <NavLink to={item.to}>
                      <SvgIcon name={item.icon} className="size-4 shrink-0" />
                      <span>{item.label}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}

              <Collapsible
                open={agentMarketOpen}
                onOpenChange={setAgentMarketOpen}
                className="group/collapsible"
              >
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    isActive={isAgentMarketActive}
                    size="lg"
                    className="text-[15px]"
                    tooltip={t("nav.agents")}
                  >
                    <NavLink to="/market" className="flex items-center gap-2">
                      <SvgIcon name={Market} className="size-4 shrink-0" />
                      <span>{t("nav.agents")}</span>
                    </NavLink>
                  </SidebarMenuButton>

                  <CollapsibleTrigger asChild>
                    <SidebarMenuAction
                      className={cn(
                        "right-2 cursor-pointer transition-transform duration-200",
                        agentMarketOpen && "rotate-180",
                      )}
                    >
                      <ChevronDown className="size-4" />
                      <span className="sr-only">Toggle agent market</span>
                    </SidebarMenuAction>
                  </CollapsibleTrigger>

                  <CollapsibleContent>
                    <SidebarMenuSub>
                      {agentItems.map((item) => (
                        <SidebarMenuSubItem key={item.id}>
                          <SidebarMenuSubButton
                            asChild
                            isActive={verifyActive(item.to)}
                          >
                            <NavLink
                              to={item.to}
                              className="flex items-center gap-2"
                            >
                              <AgentAvatar
                                agentName={item.id}
                                className="size-5 shrink-0 rounded-full"
                              />
                              <span className="truncate">{item.label}</span>
                            </NavLink>
                          </SidebarMenuSubButton>
                        </SidebarMenuSubItem>
                      ))}
                      {!agentItems.length && (
                        <SidebarMenuSubItem>
                          <span className="px-2 py-1.5 text-muted-foreground text-xs">
                            —
                          </span>
                        </SidebarMenuSubItem>
                      )}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <AppConversationSheet>
              <SidebarMenuButton
                size="lg"
                className="text-[15px]"
                tooltip={t("nav.conversations")}
              >
                <SvgIcon name={Conversation} className="size-4 shrink-0" />
                <span>{t("nav.conversations")}</span>
              </SidebarMenuButton>
            </AppConversationSheet>
          </SidebarMenuItem>

          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              isActive={verifyActive("/setting")}
              size="lg"
              className="text-[15px]"
              tooltip={t("nav.setting")}
            >
              <NavLink to="/setting">
                <SvgIcon name={Setting} className="size-4 shrink-0" />
                <span>{t("nav.setting")}</span>
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
};

export default memo(AppSidebar);
