import type { CanonicalProvider } from "@/lib/canonical-types";

export interface ProviderPresentation {
  color: string;
  logo?: string;
}

export const providerPresentation: Record<string, ProviderPresentation> = {
  kourier: { color: "#1F704C", logo: "/kourier.svg" },
  electronhub: { color: "#A242FB", logo: "/electron.svg" },
  fireworks: { color: "#F97316", logo: "/fireworks.svg" },
};

const fallbackPalette = ["#60A5FA", "#F472B6", "#A78BFA", "#34D399"];

export function presentationFor(provider: CanonicalProvider, index = 0): CanonicalProvider & ProviderPresentation {
  const known = providerPresentation[provider.id];
  return { ...provider, color: known?.color ?? fallbackPalette[index % fallbackPalette.length], logo: known?.logo };
}
