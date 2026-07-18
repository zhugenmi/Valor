import type React from "react";
import type { FC } from "react";
import { cn } from "@/lib/utils";

type LinkButtonProps = {
  url: string;
  className?: string;
  children: React.ReactNode;
};

const LinkButton: FC<LinkButtonProps> = ({ className, url, children }) => {
  return (
    <button
      type="button"
      className={cn(
        "cursor-pointer text-sm underline underline-offset-4",
        className,
      )}
      onClick={() => window.open(url, "_blank")}
    >
      {children}
    </button>
  );
};

export default LinkButton;
