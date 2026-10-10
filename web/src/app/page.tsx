import { Hero } from "@/components/Hero";
import { ControlRoom } from "./ControlRoom";

export default function Page() {
  return (
    <div className="space-y-12">
      <Hero />
      <ControlRoom />
    </div>
  );
}
