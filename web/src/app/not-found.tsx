import Link from "next/link";

export default function NotFound() {
  return (
    <div className="border border-panel-etch bg-panel-raised p-6">
      <div className="legend">404</div>
      <p className="mt-2 text-sm text-label">There is nothing at this address.</p>
      <Link href="/" className="mt-3 inline-block text-sm text-label underline decoration-panel-etch underline-offset-2">
        Go to the control room
      </Link>
    </div>
  );
}
