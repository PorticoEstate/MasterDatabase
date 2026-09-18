// List of municipalities and their booking system data slugs.
// Data is read from local cached files in data-explorer-app/data/searchdataall-<slug>.json
// (fetching live from *.aktiv-kommune.no isn't reachable from this network).
export const MUNICIPALITIES = [
  { name: "Alver", slug: "alver" },
  { name: "Bardu", slug: "bardu" },
  { name: "Bergen", slug: "bergen" },
  { name: "Bærum", slug: "baerum" },
  { name: "Drammen", slug: "drammen" },
  { name: "Eigersund", slug: "eigersund" },
  { name: "Kristiansand", slug: "kristiansand" },
  { name: "Kvam", slug: "kvam" },
  { name: "Larvik", slug: "larvik" },
  { name: "Sandnes", slug: "sandnes" },
  { name: "Sola", slug: "sola" },
  { name: "Stavanger", slug: "stavanger" },
  { name: "Suldal", slug: "suldal" },
  { name: "Sunnfjord", slug: "sunnfjord" },
  { name: "Time", slug: "time" },
  { name: "Øygarden", slug: "oygarden" },
  { name: "Ålesund", slug: "alesund" }
];

export interface RawMunicipalityData {
  activities: Array<{
    id: number;
    parent_id: number | null;
    name: string;
    description: string;
    active: number;
  }>;
  facilities: Array<{
    id: number;
    name: string;
    active: number;
  }>;
  buildings: Array<{
    id: number;
    name: string;
    activity_id: number;
    [key: string]: unknown;
  }>;
}