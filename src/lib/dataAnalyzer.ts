import { FetchedMunicipalityData } from './dataFetcher';

export interface Activity {
  name: string;
  occurrence_count: number;
  percentage: number;
  municipalities: string[];
  descriptions: string[];
  has_parent_relationships: boolean;
  parent_relationships: Array<{
    municipality: string;
    parent_id: number;
    parent_name: string;
    id: number;
    name: string;
  }>;
  has_child_relationships: boolean;
  child_relationships: Array<{
    municipality: string;
    child_id: number;
    child_name: string;
    id: number;
    name: string;
  }>;
  activity_ids: number[];
  activity_details: Array<{
    municipality: string;
    id: number;
    parent_id: number | null;
    active: number;
  }>;
  resource_count: number;
}

export interface Facility {
  name: string;
  occurrence_count: number;
  percentage: number;
  municipalities: string[];
  facility_ids: number[];
  facility_details: Array<{
    municipality: string;
    id: number;
    active: number;
  }>;
  is_unique: boolean;
  is_common: boolean;
  resource_count: number;
}

export interface AnalysisResult {
  metadata: {
    analysis_date: string;
    total_municipalities: number;
    municipality_list: string[];
    successful_fetches: number;
    failed_fetches: number;
    all_activity_details: { [key: number]: { name: string, municipality: string, parent_id: number | null, active: number } };
    parent_child_map: { [key: number]: Array<{ id: number, name: string, municipality: string }> };
  };
  activities: {
    total_unique_activities: number;
    summary_stats: {
      universal_activities: number;
      common_activities_75_plus: number;
      frequent_activities_50_plus: number;
      rare_activities_25_plus: number;
      unique_activities: number;
    };
    all_activities: Activity[];
  };
  facilities: {
    total_unique_facilities: number;
    summary_stats: {
      universal_facilities: number;
      common_facilities_75_plus: number;
      frequent_facilities_50_plus: number;
      rare_facilities_25_plus: number;
      unique_facilities: number;
    };
    all_facilities: Facility[];
  };
}

export function analyzeData(fetchedData: FetchedMunicipalityData[]): AnalysisResult {
  const successfulData = fetchedData.filter(d => d.data !== null);
  const totalMunicipalities = successfulData.length;
  
  // Build activity ID to name lookup map
  const activityIdToName = new Map<number, string>();
  
  // Analyze activities
  const activityData = new Map<string, {
    municipalities: string[];
    descriptions: Set<string>;
    parent_relationships: Array<{ municipality: string; parent_id: number; parent_name: string; id: number; name: string }>;
    child_relationships: Array<{ municipality: string; child_id: number; child_name: string; id: number; name: string }>;
    activity_ids: Set<number>;
    activity_details: Array<{ municipality: string; id: number; parent_id: number | null; active: number }>;
    resource_ids: Set<string>;
  }>();

  // Analyze facilities
  const facilityData = new Map<string, {
    municipalities: string[];
    facility_ids: Set<number>;
    facility_details: Array<{ municipality: string; id: number; active: number }>;
    resource_ids: Set<string>;
  }>();

  // First pass: build activity ID to name lookup and parent-child map
  const parentChildMap = new Map<number, Array<{ id: number; name: string; municipality: string }>>();
  const allActivityDetails = new Map<number, { name: string, municipality: string, parent_id: number | null, active: number }>();
  
  for (const municipalityData of successfulData) {
    const { name: municipality, data } = municipalityData;
    if (!data) continue;
    
    for (const activity of data.activities || []) {
      if (activity.name?.trim()) {
        activityIdToName.set(activity.id, activity.name.trim());
        
        // Store all activity details for tree building
        allActivityDetails.set(activity.id, {
          name: activity.name.trim(),
          municipality,
          parent_id: activity.parent_id,
          active: activity.active
        });
        
        // Build parent-child mapping
        if (activity.parent_id) {
          if (!parentChildMap.has(activity.parent_id)) {
            parentChildMap.set(activity.parent_id, []);
          }
          parentChildMap.get(activity.parent_id)!.push({
            id: activity.id,
            name: activity.name.trim(),
            municipality
          });
        }
      }
    }
  }

  for (const municipalityData of successfulData) {
    const { name: municipality, data } = municipalityData;
    if (!data) continue;

    // Build local (per-municipality) lookups from bookable resources to the
    // activities/facilities they're tagged with. IDs are only unique within
    // a single municipality's dataset, so these maps must not be shared
    // across municipalities.
    const activityResourceIds = new Map<number, Set<number>>();
    for (const resource of data.resources || []) {
      if (resource.activity_id == null) continue;
      if (!activityResourceIds.has(resource.activity_id)) {
        activityResourceIds.set(resource.activity_id, new Set());
      }
      activityResourceIds.get(resource.activity_id)!.add(resource.id);
    }
    for (const link of data.resource_activities || []) {
      if (!activityResourceIds.has(link.activity_id)) {
        activityResourceIds.set(link.activity_id, new Set());
      }
      activityResourceIds.get(link.activity_id)!.add(link.resource_id);
    }

    const facilityResourceIds = new Map<number, Set<number>>();
    for (const link of data.resource_facilities || []) {
      if (!facilityResourceIds.has(link.facility_id)) {
        facilityResourceIds.set(link.facility_id, new Set());
      }
      facilityResourceIds.get(link.facility_id)!.add(link.resource_id);
    }

    // Process activities
    for (const activity of data.activities || []) {
      const name = activity.name?.trim();
      if (!name) continue;

      if (!activityData.has(name)) {
        activityData.set(name, {
          municipalities: [],
          descriptions: new Set(),
          parent_relationships: [],
          child_relationships: [],
          activity_ids: new Set(),
          activity_details: [],
          resource_ids: new Set(),
        });
      }

      const activityInfo = activityData.get(name)!;
      activityInfo.municipalities.push(municipality);
      activityInfo.activity_ids.add(activity.id);
      activityInfo.activity_details.push({
        municipality,
        id: activity.id,
        parent_id: activity.parent_id,
        active: activity.active,
      });

      for (const resourceId of activityResourceIds.get(activity.id) || []) {
        activityInfo.resource_ids.add(`${municipality}:${resourceId}`);
      }

      if (activity.description?.trim()) {
        activityInfo.descriptions.add(activity.description.trim());
      }
      
      if (activity.parent_id) {
        const parentName = activityIdToName.get(activity.parent_id) || `Unknown (ID: ${activity.parent_id})`;
        activityInfo.parent_relationships.push({
          municipality,
          parent_id: activity.parent_id,
          parent_name: parentName,
          id: activity.id,
          name: name,
        });
      }
      
      // Add child relationships for this activity
      const children = parentChildMap.get(activity.id) || [];
      for (const child of children) {
        // Only add if the child activity name exists in our activity data
        if (activityData.has(child.name)) {
          activityInfo.child_relationships.push({
            municipality: child.municipality,
            child_id: child.id,
            child_name: child.name,
            id: activity.id,
            name: name,
          });
        }
      }
    }

    // Process facilities
    for (const facility of data.facilities || []) {
      const name = facility.name?.trim();
      if (!name) continue;

      if (!facilityData.has(name)) {
        facilityData.set(name, {
          municipalities: [],
          facility_ids: new Set(),
          facility_details: [],
          resource_ids: new Set(),
        });
      }

      const facilityInfo = facilityData.get(name)!;
      facilityInfo.municipalities.push(municipality);
      facilityInfo.facility_ids.add(facility.id);
      facilityInfo.facility_details.push({
        municipality,
        id: facility.id,
        active: facility.active,
      });

      for (const resourceId of facilityResourceIds.get(facility.id) || []) {
        facilityInfo.resource_ids.add(`${municipality}:${resourceId}`);
      }
    }
  }

  // Convert to final format
  const activities: Activity[] = Array.from(activityData.entries()).map(([name, info]) => {
    const uniqueMunicipalities = [...new Set(info.municipalities)];
    const occurrenceCount = uniqueMunicipalities.length;
    const percentage = (occurrenceCount / totalMunicipalities) * 100;

    return {
      name,
      occurrence_count: occurrenceCount,
      percentage,
      municipalities: uniqueMunicipalities.sort(),
      descriptions: Array.from(info.descriptions).sort(),
      has_parent_relationships: info.parent_relationships.length > 0,
      parent_relationships: info.parent_relationships,
      has_child_relationships: info.child_relationships.length > 0,
      child_relationships: info.child_relationships,
      activity_ids: Array.from(info.activity_ids).sort(),
      activity_details: info.activity_details,
      resource_count: info.resource_ids.size,
    };
  }).sort((a, b) => b.percentage - a.percentage || a.name.localeCompare(b.name));

  const facilities: Facility[] = Array.from(facilityData.entries()).map(([name, info]) => {
    const uniqueMunicipalities = [...new Set(info.municipalities)];
    const occurrenceCount = uniqueMunicipalities.length;
    const percentage = (occurrenceCount / totalMunicipalities) * 100;

    return {
      name,
      occurrence_count: occurrenceCount,
      percentage,
      municipalities: uniqueMunicipalities.sort(),
      facility_ids: Array.from(info.facility_ids).sort(),
      facility_details: info.facility_details,
      is_unique: occurrenceCount === 1,
      is_common: occurrenceCount >= (totalMunicipalities * 0.5),
      resource_count: info.resource_ids.size,
    };
  }).sort((a, b) => b.percentage - a.percentage || a.name.localeCompare(b.name));

  // Calculate summary stats
  const getActivityStats = (activities: Activity[]) => ({
    universal_activities: activities.filter(a => a.percentage === 100).length,
    common_activities_75_plus: activities.filter(a => a.percentage >= 75 && a.percentage < 100).length,
    frequent_activities_50_plus: activities.filter(a => a.percentage >= 50 && a.percentage < 75).length,
    rare_activities_25_plus: activities.filter(a => a.percentage >= 25 && a.percentage < 50).length,
    unique_activities: activities.filter(a => a.percentage < 25).length,
  });

  const getFacilityStats = (facilities: Facility[]) => ({
    universal_facilities: facilities.filter(f => f.percentage === 100).length,
    common_facilities_75_plus: facilities.filter(f => f.percentage >= 75 && f.percentage < 100).length,
    frequent_facilities_50_plus: facilities.filter(f => f.percentage >= 50 && f.percentage < 75).length,
    rare_facilities_25_plus: facilities.filter(f => f.percentage >= 25 && f.percentage < 50).length,
    unique_facilities: facilities.filter(f => f.percentage < 25).length,
  });

  // Convert Maps to plain objects for JSON serialization
  const allActivityDetailsObj: { [key: number]: { name: string, municipality: string, parent_id: number | null, active: number } } = {};
  for (const [id, details] of allActivityDetails) {
    allActivityDetailsObj[id] = details;
  }
  
  const parentChildMapObj: { [key: number]: Array<{ id: number, name: string, municipality: string }> } = {};
  for (const [parentId, children] of parentChildMap) {
    parentChildMapObj[parentId] = children;
  }

  return {
    metadata: {
      analysis_date: new Date().toISOString().split('T')[0],
      total_municipalities: totalMunicipalities,
      municipality_list: successfulData.map(d => d.name.toLowerCase()).sort(),
      successful_fetches: successfulData.length,
      failed_fetches: fetchedData.length - successfulData.length,
      all_activity_details: allActivityDetailsObj,
      parent_child_map: parentChildMapObj,
    },
    activities: {
      total_unique_activities: activities.length,
      summary_stats: getActivityStats(activities),
      all_activities: activities,
    },
    facilities: {
      total_unique_facilities: facilities.length,
      summary_stats: getFacilityStats(facilities),
      all_facilities: facilities,
    },
  };
}