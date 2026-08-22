/** Intensity color scale for the Day Band: clean spruce, sand midpoint, smog
 *  amber. Values are normalized within the visible 24h window; exact numbers
 *  always appear in the cell tooltip, so color is never the only channel. */
const STOPS: [number, number, number][] = [
  [14, 133, 99],   // #0e8563 clean
  [217, 201, 106], // #d9c96a mid
  [197, 90, 20],   // #c55a14 dirty
];

export function intensityColor(value: number, min: number, max: number): string {
  const t = max > min ? (value - min) / (max - min) : 0.5;
  const seg = t < 0.5 ? 0 : 1;
  const local = (t - seg * 0.5) * 2;
  const [a, b] = [STOPS[seg], STOPS[seg + 1]];
  const mix = (i: number) => Math.round(a[i] + (b[i] - a[i]) * Math.min(Math.max(local, 0), 1));
  return `rgb(${mix(0)} ${mix(1)} ${mix(2)})`;
}
