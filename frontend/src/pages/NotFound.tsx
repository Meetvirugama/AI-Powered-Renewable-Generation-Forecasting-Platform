import { Link, useLocation } from "react-router";
import Panel from "../components/common/Panel";

/**
 * Any path the router does not know.
 *
 * With no catch-all route, an unknown URL rendered an empty page -- no sidebar,
 * no message, nothing to click. Vercel's rewrite sends every path to the app, so
 * the app has to answer for the ones it does not recognise.
 */
export default function NotFound() {
  const { pathname } = useLocation();

  return (
    <div className="grid gap-[var(--gap-section)]">
      <Panel title="Page not found">
        <div className="flex flex-col gap-3">
          <p className="text-[14px] text-text">
            There is no page at <span className="font-mono text-text-muted">{pathname}</span>.
          </p>
          <Link
            to="/"
            className="inline-flex w-fit items-center rounded-[var(--radius-control)] bg-accent px-4 py-2 text-[13px] font-medium text-on-accent"
          >
            Go to Overview
          </Link>
        </div>
      </Panel>
    </div>
  );
}
