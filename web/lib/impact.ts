/** Concrete equivalents for CO2 savings. Factors in ASSUMPTIONS.md:
 *  average gasoline car ~192 g CO2/km; EPA tree seedling grown 10 years
 *  absorbs ~60 kg CO2. */
export const kmDriven = (kg: number) => kg / 0.192;
export const treeSeedlings = (kg: number) => kg / 60;

export const fmtKm = (kg: number) => {
  const km = kmDriven(kg);
  return km >= 10 ? `${Math.round(km)} km` : `${km.toFixed(1)} km`;
};
