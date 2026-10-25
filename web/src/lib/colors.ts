// Player identity colours: saturated pixel inks that stay legible on cream paper.
// Everything else on the site is blue; these appear only where players must be told apart.
export const playerColors = [
  "#1f4fff",
  "#f2542d",
  "#0e9f6e",
  "#c81d7a",
  "#d69a00",
  "#7b3fe4",
  "#0b8ca8",
  "#5c6b00",
];
export const playerColor = (index: number) => playerColors[index % playerColors.length];
