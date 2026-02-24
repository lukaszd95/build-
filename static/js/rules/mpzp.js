// static/js/rules/mpzp.js
// Rulebook: MPZP / WZ — MVP: coverage max + PBC min

export const mpzpRules = [
  {
    id: "MPZP_COVERAGE_MAX",
    group: "MPZP/WZ",
    title: "MPZP/WZ — Maks. powierzchnia zabudowy (coverage)",
    version: "MVP-1",
    enabledByDefault: true,
    params: {
      coverageMaxPercent: 30
    },
    text: `Maksymalny udział powierzchni zabudowy w powierzchni działki (coverage).
MVP: Jeżeli footprint budynku przekracza limit, silnik skaluje footprint w dół.`,
    ui: {
      togglable: true,
      editableParams: [
        { key: "coverageMaxPercent", label: "Maks. pow. zabudowy [%]", min: 0, max: 100, step: 1 }
      ]
    },
    tags: ["coverage", "mpzp"]
  },
  {
    id: "MPZP_PBC_MIN",
    group: "MPZP/WZ",
    title: "MPZP/WZ — Min. powierzchnia biologicznie czynna (PBC)",
    version: "MVP-1",
    enabledByDefault: true,
    params: {
      pbcMinPercent: 30
    },
    text: `Minimalny udział powierzchni biologicznie czynnej (PBC).
MVP: PBC = Pow. działki − Pow. zabudowy (bez uwzględnienia utwardzeń).
Jeżeli PBC jest za mała, silnik skaluje footprint w dół.`,
    ui: {
      togglable: true,
      editableParams: [
        { key: "pbcMinPercent", label: "Min. PBC [%]", min: 0, max: 100, step: 1 }
      ]
    },
    tags: ["pbc", "bio", "mpzp"]
  }
];
