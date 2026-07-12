import { useIsFetching, useIsMutating } from "@tanstack/react-query";

/**
 * A slim indeterminate bar that rides the top edge of the screen whenever ANY
 * query or mutation is in flight. It's the app-wide "we heard you, it's
 * working" signal — so an action whose result takes a beat (a scene search, an
 * analysis submit, an AOI save) never looks like a dead/ghost button. Purely
 * presentational; it reads react-query's global in-flight counts and shows
 * nothing when the app is idle.
 */
export function GlobalActivityBar() {
  const fetching = useIsFetching();
  const mutating = useIsMutating();
  const busy = fetching + mutating > 0;

  if (!busy) return null;
  return <div className="activity-bar" role="progressbar" aria-label="Loading" aria-busy="true" />;
}
