"use client";

interface PrismReelBrandingProps {
  size?: "sm" | "md";
  showSlogan?: boolean;
}

export default function PrismReelBranding({ size = "md", showSlogan = true }: PrismReelBrandingProps) {
  const titleSize = size === "sm" ? "text-lg" : "text-xl";

  return (
    <div>
      <div className="flex flex-col justify-center">
        <div className="flex items-baseline gap-0">
          <span className={`font-mono ${titleSize} font-bold tracking-tight text-foreground`}>
            PRISM
          </span>
          <span className={`font-mono ${titleSize} font-black tracking-tight text-primary`}>
            REEL
          </span>
        </div>
        {size !== "sm" && (
          <span className="font-mono text-[0.6875rem] text-text-muted tracking-[0.2em] uppercase -mt-0.5">
            Studio
          </span>
        )}
      </div>
      {showSlogan && (
        <p className="font-mono atelier-display text-[0.5rem] text-text-muted tracking-[0.15em] text-center mt-2.5 uppercase">
          Render Noise into Narrative
        </p>
      )}
    </div>
  );
}
