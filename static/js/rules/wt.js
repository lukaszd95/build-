// static/js/rules/wt.js

export const wtRules = [
  {
    id: "WT_12",
    title: "WT §12 – Odległość od granicy działki",
    enabledByDefault: true,

    // Parametry, które MUSZĄ istnieć, bo main.js i UI je czytają
    params: {
      distWithOpeningsM: 4,     // ściana z oknami / drzwiami
      distWithoutOpeningsM: 3   // ściana bez okien / drzwi
    },

    text:
`§ 12. [Odległość od granicy z sąsiednią działką budowlaną]
1. Jeżeli z przepisów § 13, § 19, § 23, § 36, § 40, § 60 i § 271–273 lub przepisów odrębnych
nie wynikają inne wymagania, budynek na działce budowlanej należy sytuować w odległości
od granicy tej działki nie mniejszej niż:
1) 4 m — w przypadku budynku zwróconego ścianą z oknami lub drzwiami w stronę tej granicy,
2) 3 m — w przypadku budynku zwróconego ścianą bez okien lub drzwi w stronę tej granicy,
(…)
— przy czym każdą płaszczyznę powstałą w wyniku załamania lub uskoku ściany traktuje się jako oddzielną ścianę.`
  }
];
