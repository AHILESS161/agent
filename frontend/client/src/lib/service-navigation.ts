export type ServiceTool = "reply" | "compare";

function applicationId(value: string | null): number | undefined {
  if (!value || !/^\d+$/.test(value)) return undefined;
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : undefined;
}

/** Support direct hash links and queries moved before the hash by wouter. */
export function readServiceRoute(location: string, search: string) {
  const queryStart = location.indexOf("?");
  const path = queryStart === -1 ? location : location.slice(0, queryStart);
  const params = new URLSearchParams(queryStart === -1 ? search : location.slice(queryStart + 1));
  const tool: ServiceTool = params.get("tool") === "compare" ? "compare" : "reply";
  const caseMatch = path.match(/^\/applications\/(\d+)\/?$/);

  // Queries can remain in the browser URL after leaving services. Only a
  // service page or an actual application page provides application context.
  const selectedApplicationId = path === "/services"
    ? applicationId(params.get("application"))
    : caseMatch ? applicationId(caseMatch[1]) : undefined;

  return { path, tool, applicationId: selectedApplicationId };
}

export function serviceHref(tool: ServiceTool, selectedApplicationId?: number): string {
  const params = new URLSearchParams({ tool });
  if (selectedApplicationId && Number.isSafeInteger(selectedApplicationId) && selectedApplicationId > 0) {
    params.set("application", String(selectedApplicationId));
  }
  return `/services?${params}`;
}
