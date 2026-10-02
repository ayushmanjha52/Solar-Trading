import { Evidence } from "./Evidence";

export const metadata = { title: "Settlement evidence · Local Energy Market" };

export default function Page({ params }: { params: { g: string } }) {
  return <Evidence g={Number(params.g)} />;
}
