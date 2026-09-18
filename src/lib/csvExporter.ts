import { Activity, Facility, AnalysisResult } from './dataAnalyzer';

export function escapeCsv(text: string): string {
  // Escape double quotes by doubling them and wrap in quotes if needed
  if (text.includes('"') || text.includes(',') || text.includes('\n') || text.includes('\r')) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export function formatActivitiesToCsv(activities: Activity[]): string {
  const headers = [
    'Name',
    'Occurrence Count',
    'Percentage',
    'Municipalities',
    'Municipality Count',
    'Activity IDs',
    'Activity ID Count',
    'Has Parent Relationships',
    'Parent Relationships Count',
    'Has Child Relationships',
    'Child Relationships Count',
    'Active Instances',
    'Inactive Instances',
    'Total Instances',
    'Description Count',
    'Descriptions',
    'Parent-Child Details',
    'Child-Parent Details'
  ];

  let csv = headers.join(',') + '\n';

  for (const activity of activities) {
    const activeInstances = activity.activity_details.filter(d => d.active === 1).length;
    const inactiveInstances = activity.activity_details.filter(d => d.active === 0).length;
    
    // Format parent-child relationships with details
    const parentChildDetails = activity.parent_relationships.map(rel => 
      `${rel.municipality}: "${rel.name}" (ID:${rel.id}) → "${rel.parent_name}" (ID:${rel.parent_id})`
    ).join('; ');
    
    // Format child-parent relationships with details
    const childParentDetails = activity.child_relationships.map(rel => 
      `${rel.municipality}: "${rel.name}" (ID:${rel.id}) → "${rel.child_name}" (ID:${rel.child_id})`
    ).join('; ');
    
    const row = [
      escapeCsv(activity.name),
      activity.occurrence_count.toString(),
      activity.percentage.toFixed(2),
      escapeCsv(activity.municipalities.join('; ')),
      activity.municipalities.length.toString(),
      escapeCsv(activity.activity_ids.join('; ')),
      activity.activity_ids.length.toString(),
      activity.has_parent_relationships.toString(),
      activity.parent_relationships.length.toString(),
      activity.has_child_relationships.toString(),
      activity.child_relationships.length.toString(),
      activeInstances.toString(),
      inactiveInstances.toString(),
      activity.activity_details.length.toString(),
      activity.descriptions.length.toString(),
      escapeCsv(activity.descriptions.join('; ')),
      escapeCsv(parentChildDetails),
      escapeCsv(childParentDetails)
    ];
    csv += row.join(',') + '\n';
  }

  return csv;
}

export function formatFacilitiesToCsv(facilities: Facility[]): string {
  const headers = [
    'Name',
    'Occurrence Count',
    'Percentage',
    'Municipalities',
    'Municipality Count',
    'Is Unique',
    'Is Common',
    'Facility IDs',
    'Facility ID Count',
    'Active Instances',
    'Inactive Instances',
    'Total Instances'
  ];

  let csv = headers.join(',') + '\n';

  for (const facility of facilities) {
    const activeInstances = facility.facility_details.filter(d => d.active === 1).length;
    const inactiveInstances = facility.facility_details.filter(d => d.active === 0).length;
    
    const row = [
      escapeCsv(facility.name),
      facility.occurrence_count.toString(),
      facility.percentage.toFixed(2),
      escapeCsv(facility.municipalities.join('; ')),
      facility.municipalities.length.toString(),
      facility.is_unique.toString(),
      facility.is_common.toString(),
      escapeCsv(facility.facility_ids.join('; ')),
      facility.facility_ids.length.toString(),
      activeInstances.toString(),
      inactiveInstances.toString(),
      facility.facility_details.length.toString()
    ];
    csv += row.join(',') + '\n';
  }

  return csv;
}

export function formatSummaryStatsToCsv(data: AnalysisResult): string {
  const headers = ['Metric', 'Activities', 'Facilities'];
  let csv = headers.join(',') + '\n';

  const metrics = [
    ['Universal (100%)', data.activities.summary_stats.universal_activities, data.facilities.summary_stats.universal_facilities],
    ['Common (75%+)', data.activities.summary_stats.common_activities_75_plus, data.facilities.summary_stats.common_facilities_75_plus],
    ['Frequent (50%+)', data.activities.summary_stats.frequent_activities_50_plus, data.facilities.summary_stats.frequent_facilities_50_plus],
    ['Rare (25%+)', data.activities.summary_stats.rare_activities_25_plus, data.facilities.summary_stats.rare_facilities_25_plus],
    ['Unique (<25%)', data.activities.summary_stats.unique_activities, data.facilities.summary_stats.unique_facilities],
    ['Total Unique', data.activities.total_unique_activities, data.facilities.total_unique_facilities]
  ];

  for (const [metric, activityCount, facilityCount] of metrics) {
    csv += `${escapeCsv(metric.toString())},${activityCount},${facilityCount}\n`;
  }

  return csv;
}

export function formatMunicipalityStatsToCsv(data: AnalysisResult): string {
  const headers = ['Municipality', 'Activity Count', 'Facility Count'];
  let csv = headers.join(',') + '\n';

  // Count activities and facilities per municipality
  const municipalityStats = new Map<string, { activities: number; facilities: number }>();

  // Initialize all municipalities
  for (const municipality of data.metadata.municipality_list) {
    municipalityStats.set(municipality, { activities: 0, facilities: 0 });
  }

  // Count activities per municipality
  for (const activity of data.activities.all_activities) {
    for (const municipality of activity.municipalities) {
      const stats = municipalityStats.get(municipality);
      if (stats) {
        stats.activities++;
      }
    }
  }

  // Count facilities per municipality
  for (const facility of data.facilities.all_facilities) {
    for (const municipality of facility.municipalities) {
      const stats = municipalityStats.get(municipality);
      if (stats) {
        stats.facilities++;
      }
    }
  }

  // Generate CSV rows
  const sortedMunicipalities = Array.from(municipalityStats.entries())
    .sort(([a], [b]) => a.localeCompare(b));

  for (const [municipality, stats] of sortedMunicipalities) {
    csv += `${escapeCsv(municipality)},${stats.activities},${stats.facilities}\n`;
  }

  return csv;
}

export function downloadCsv(content: string, filename: string): void {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}