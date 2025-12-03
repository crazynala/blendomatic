type ConfigOptionValue = {
  label: string;
  value: string;
  suffixes: string[];
};

type ConfigOptionGroup = {
  label: string;
  defaultValue: string;
  values: ConfigOptionValue[];
};

export type ConfigOptions = Record<string, ConfigOptionGroup>;

type CategorizedSuffix = {
  category: string;
  optionValue: string;
};

const COLLAR_SUFFIXES: Record<string, string[]> = {
  Band: ["band_collar"],
  Regular: ["reg_collar"],
  "Button-down": ["button_collar", "buttondown_collar", "bd_collar"],
};

const PLACKET_SUFFIXES: Record<string, string[]> = {
  Regular: ["placket-reg", "placket_regular"],
  Hidden: ["placket-hidden", "placket_hidden"],
};

const SLEEVE_SUFFIXES: Record<string, string[]> = {
  Long: ["Body_LS", "sleeve_long"],
  Short: ["Body_SS", "sleeve_short"],
};

export const CONFIG_OPTIONS: ConfigOptions = {
  collar: {
    label: "Collar",
    defaultValue: "Regular",
    values: Object.entries(COLLAR_SUFFIXES).map(([label, suffixes]) => ({
      label,
      value: label,
      suffixes,
    })),
  },
  placket: {
    label: "Placket",
    defaultValue: "Regular",
    values: Object.entries(PLACKET_SUFFIXES).map(([label, suffixes]) => ({
      label,
      value: label,
      suffixes,
    })),
  },
  sleeves: {
    label: "Sleeves",
    defaultValue: "Long",
    values: Object.entries(SLEEVE_SUFFIXES).map(([label, suffixes]) => ({
      label,
      value: label,
      suffixes,
    })),
  },
};

const SUFFIX_LOOKUP = new Map<string, CategorizedSuffix>();
for (const [category, config] of Object.entries(CONFIG_OPTIONS)) {
  for (const option of config.values) {
    for (const suffix of option.suffixes) {
      SUFFIX_LOOKUP.set(suffix, { category, optionValue: option.value });
    }
  }
}

export function categorizeSuffix(suffix: string): CategorizedSuffix | null {
  return SUFFIX_LOOKUP.get(suffix) ?? null;
}

export const LAYER_PRIORITY = ["base", "sleeves", "placket", "collar"] as const;
