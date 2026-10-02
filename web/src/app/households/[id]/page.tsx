import { HouseholdDetail } from "./HouseholdDetail";

export const metadata = { title: "Household · Local Energy Market" };

export default function Page({ params }: { params: { id: string } }) {
  return <HouseholdDetail id={Number(params.id)} />;
}
