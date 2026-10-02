import { Suspense } from "react";
import { Loading } from "@/components/ui";
import { TradeDesk } from "./TradeDesk";

export const metadata = { title: "Trade · Local Energy Market" };

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <TradeDesk />
    </Suspense>
  );
}
