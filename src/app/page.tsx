'use client';

import { useState, useEffect, useMemo } from 'react';
import styles from './page.module.css';
import { formatActivitiesToCsv, formatFacilitiesToCsv, formatSummaryStatsToCsv, formatMunicipalityStatsToCsv, downloadCsv } from '@/lib/csvExporter';
import { buildActivityTree, renderTree } from '@/lib/treeBuilder';

interface Activity {
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
}

interface Facility {
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
}

interface DataStructure {
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

export default function Home() {
  const [data, setData] = useState<DataStructure | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'activities' | 'facilities'>('activities');
  const [searchTerm, setSearchTerm] = useState('');
  const [minPercentage, setMinPercentage] = useState(0);
  const [selectedMunicipality, setSelectedMunicipality] = useState('');
  const [sortBy, setSortBy] = useState<'percentage' | 'name' | 'municipalities'>('percentage');
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        console.log('Fetching fresh data from API...');
        const response = await fetch('/api/analyze');
        
        if (!response.ok) {
          throw new Error(`API error: ${response.status} ${response.statusText}`);
        }
        
        const jsonData = await response.json();
        setData(jsonData);
        console.log('Data loaded successfully:', jsonData.metadata);
      } catch (error) {
        console.error('Error loading data:', error);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const filteredData = useMemo(() => {
    if (!data) return { activities: [], facilities: [] };

    const filterItems = (items: (Activity | Facility)[]) => {
      return items.filter(item => {
        const matchesSearch = item.name.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesPercentage = item.percentage >= minPercentage;
        const matchesMunicipality = !selectedMunicipality || item.municipalities.includes(selectedMunicipality);
        return matchesSearch && matchesPercentage && matchesMunicipality;
      });
    };

    const sortItems = (items: (Activity | Facility)[]) => {
      return [...items].sort((a, b) => {
        switch (sortBy) {
          case 'name':
            return a.name.localeCompare(b.name);
          case 'municipalities':
            return b.occurrence_count - a.occurrence_count || a.name.localeCompare(b.name);
          case 'percentage':
          default:
            return b.percentage - a.percentage || a.name.localeCompare(b.name);
        }
      });
    };

    return {
      activities: sortItems(filterItems(data.activities.all_activities)),
      facilities: sortItems(filterItems(data.facilities.all_facilities))
    };
  }, [data, searchTerm, minPercentage, selectedMunicipality, sortBy]);

  const toggleExpanded = (id: string) => {
    setExpandedItems(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };


  const handleExportActivitiesCsv = () => {
    if (!data) return;
    const csv = formatActivitiesToCsv(filteredData.activities as Activity[]);
    const filename = `activities-${data.metadata.analysis_date}-${filteredData.activities.length}items.csv`;
    downloadCsv(csv, filename);
  };

  const handleExportFacilitiesCsv = () => {
    if (!data) return;
    const csv = formatFacilitiesToCsv(filteredData.facilities as Facility[]);
    const filename = `facilities-${data.metadata.analysis_date}-${filteredData.facilities.length}items.csv`;
    downloadCsv(csv, filename);
  };

  const handleExportSummaryStatsCsv = () => {
    if (!data) return;
    const csv = formatSummaryStatsToCsv(data);
    const filename = `summary-stats-${data.metadata.analysis_date}.csv`;
    downloadCsv(csv, filename);
  };

  const handleExportMunicipalityStatsCsv = () => {
    if (!data) return;
    const csv = formatMunicipalityStatsToCsv(data);
    const filename = `municipality-stats-${data.metadata.analysis_date}.csv`;
    downloadCsv(csv, filename);
  };

  if (loading) {
    return (
      <div className={styles.container}>
        <header className={styles.header}>
          <h1>Norwegian Municipality Activity & Facility Data Explorer</h1>
          <p>Fetching fresh data from booking systems...</p>
        </header>
        <div className={styles.loading}>
          <div>🔄 Fetching data from Norwegian municipalities...</div>
          <div style={{ fontSize: '14px', marginTop: '10px', opacity: 0.8 }}>
            This may take 30-60 seconds as we fetch data from multiple booking systems
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>Error loading data</div>
      </div>
    );
  }

  const currentData = activeTab === 'activities' ? filteredData.activities : filteredData.facilities;

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1>Norwegian Municipality Activity & Facility Data Explorer</h1>
        <p>Live analysis of {data.metadata.total_municipalities} municipalities • Last updated: {data.metadata.analysis_date}</p>
        {data.metadata.failed_fetches > 0 && (
          <div style={{ fontSize: '14px', marginTop: '5px', opacity: 0.9 }}>
            ⚠️ {data.metadata.failed_fetches} municipality data source(s) unavailable
          </div>
        )}
      </header>

      <div className={styles.statsGrid}>
        <div className={styles.statCard}>
          <div className={styles.statNumber}>{data.metadata.total_municipalities}</div>
          <div>Municipalities</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statNumber}>{data.activities.total_unique_activities}</div>
          <div>Unique Activities</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statNumber}>{data.facilities.total_unique_facilities}</div>
          <div>Unique Facilities</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statNumber}>
            {data.activities.summary_stats.universal_activities + data.facilities.summary_stats.universal_facilities}
          </div>
          <div>Universal Items</div>
        </div>
      </div>

      <div className={styles.controls}>
        <div className={styles.controlGroup}>
          <label>Search:</label>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search activities or facilities..."
          />
        </div>
        <div className={styles.controlGroup}>
          <label>Min Occurrence:</label>
          <select value={minPercentage} onChange={(e) => setMinPercentage(Number(e.target.value))}>
            <option value={0}>All items</option>
            <option value={100}>Universal (100%)</option>
            <option value={75}>Common (75%+)</option>
            <option value={50}>Frequent (50%+)</option>
            <option value={25}>Occasional (25%+)</option>
          </select>
        </div>
        <div className={styles.controlGroup}>
          <label>Municipality:</label>
          <select value={selectedMunicipality} onChange={(e) => setSelectedMunicipality(e.target.value)}>
            <option value="">All municipalities</option>
            {data.metadata.municipality_list.map(municipality => (
              <option key={municipality} value={municipality}>
                {municipality.charAt(0).toUpperCase() + municipality.slice(1)}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.controlGroup}>
          <label>Sort by:</label>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as 'percentage' | 'name' | 'municipalities')}>
            <option value="percentage">Occurrence %</option>
            <option value="name">Name (A-Z)</option>
            <option value="municipalities">Municipality count</option>
          </select>
        </div>
      </div>

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'activities' ? styles.active : ''}`}
          onClick={() => setActiveTab('activities')}
        >
          Activities ({filteredData.activities.length})
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'facilities' ? styles.active : ''}`}
          onClick={() => setActiveTab('facilities')}
        >
          Facilities ({filteredData.facilities.length})
        </button>
      </div>

      <div className={styles.exportControls}>
        <div className={styles.exportGroup}>
          <span>Export CSV:</span>
          <button 
            className={styles.exportButton}
            onClick={handleExportActivitiesCsv}
            disabled={filteredData.activities.length === 0}
          >
            Activities ({filteredData.activities.length})
          </button>
          <button 
            className={styles.exportButton}
            onClick={handleExportFacilitiesCsv}
            disabled={filteredData.facilities.length === 0}
          >
            Facilities ({filteredData.facilities.length})
          </button>
          <button 
            className={styles.exportButton}
            onClick={handleExportSummaryStatsCsv}
          >
            Summary Stats
          </button>
          <button 
            className={styles.exportButton}
            onClick={handleExportMunicipalityStatsCsv}
          >
            Municipality Stats
          </button>
        </div>
      </div>

      <div className={styles.content}>
        {currentData.length === 0 ? (
          <div className={styles.noResults}>No {activeTab} match your criteria</div>
        ) : (
          <div className={styles.itemList}>
            {currentData.map((item, index) => {
              const itemId = `${activeTab}-${index}`;
              const isExpanded = expandedItems.has(itemId);
              
              return (
                <div key={itemId} className={styles.itemCard}>
                  <div 
                    className={styles.itemHeader}
                    onClick={() => toggleExpanded(itemId)}
                  >
                    <div className={styles.itemName}>
                      <h3>{item.name}</h3>
                      {activeTab === 'activities' && (item as Activity).descriptions.length > 1 && (
                        <small>+{(item as Activity).descriptions.length - 1} descriptions</small>
                      )}
                      {activeTab === 'activities' && (item as Activity).activity_details.length > 0 && (
                        <small>{(item as Activity).activity_details.length} instance{(item as Activity).activity_details.length !== 1 ? 's' : ''}</small>
                      )}
                      {activeTab === 'facilities' && (item as Facility).facility_details.length > 0 && (
                        <small>{(item as Facility).facility_details.length} instance{(item as Facility).facility_details.length !== 1 ? 's' : ''}</small>
                      )}
                    </div>
                    
                    <div className={styles.itemStats}>
                      <div className={styles.percentageBar}>
                        <div 
                          className={styles.percentageFill} 
                          style={{ width: `${item.percentage}%` }}
                        />
                        <div className={styles.percentageText}>
                          {item.percentage.toFixed(1)}%
                        </div>
                      </div>
                      <div className={styles.occurrenceCount}>
                        {item.occurrence_count}/{data.metadata.total_municipalities}
                      </div>
                    </div>
                    
                    <div className={styles.municipalities}>
                      {item.municipalities.slice(0, 3).map(municipality => (
                        <span key={municipality} className={styles.municipalityTag}>
                          {municipality}
                        </span>
                      ))}
                      {item.municipalities.length > 3 && (
                        <span className={styles.municipalityTag}>
                          +{item.municipalities.length - 3} more
                        </span>
                      )}
                    </div>
                    
                    <div className={styles.expandIcon}>
                      {isExpanded ? '▼' : '▶'}
                    </div>
                  </div>
                  
                  {isExpanded && (
                    <div className={styles.expandedContent}>
                      <div className={styles.section}>
                        <h4>Full Municipality List</h4>
                        <div className={styles.allMunicipalities}>
                          {item.municipalities.map(municipality => (
                            <span key={municipality} className={styles.municipalityTag}>
                              {municipality}
                            </span>
                          ))}
                        </div>
                      </div>
                      
                      {activeTab === 'activities' && (
                        <>
                          {(item as Activity).descriptions.length > 0 && (
                            <div className={styles.section}>
                              <h4>Descriptions</h4>
                              <div className={styles.descriptions}>
                                {(item as Activity).descriptions.map((desc, i) => (
                                  <div key={i} className={styles.description}>
                                    {desc}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          
                          <div className={styles.section}>
                            <h4>Activity IDs</h4>
                            <p>{(item as Activity).activity_ids.join(', ') || 'None'}</p>
                          </div>
                          
                          {(item as Activity).activity_details.length > 0 && (
                            <div className={styles.section}>
                              <h4>Activity Instances</h4>
                              {(item as Activity).activity_details.map((detail, i) => (
                                <div key={i} className={styles.location}>
                                  <strong>{detail.municipality}</strong><br />
                                  ID: {detail.id}<br />
                                  {detail.parent_id && <span>Parent ID: {detail.parent_id}<br /></span>}
                                  Status: {detail.active ? 'Active' : 'Inactive'}
                                </div>
                              ))}
                            </div>
                          )}
                          
                          {(item as Activity).has_parent_relationships && (
                            <div className={styles.section}>
                              <h4>Parent Relationships</h4>
                              <p>Has {(item as Activity).parent_relationships.length} parent relationship(s)</p>
                              {(item as Activity).parent_relationships.map((rel, i) => (
                                <div key={i} className={styles.location}>
                                  <strong>{rel.municipality}</strong><br />
                                  Child: &quot;{rel.name}&quot; (ID: {rel.id})<br />
                                  → Parent: &quot;{rel.parent_name}&quot; (ID: {rel.parent_id})
                                </div>
                              ))}
                            </div>
                          )}
                          
                          {(item as Activity).has_child_relationships && (
                            <div className={styles.section}>
                              <h4>Activity Hierarchy Tree</h4>
                              <p>Shows {(item as Activity).child_relationships.length} child relationship(s) across municipalities</p>
                              {(() => {
                                const completeData = {
                                  all_activity_details: data.metadata.all_activity_details,
                                  parent_child_map: data.metadata.parent_child_map
                                };
                                const trees = buildActivityTree(item as Activity, completeData);
                                return Object.entries(trees).map(([municipality, roots]) => (
                                  <div key={municipality} className={styles.treeContainer}>
                                    <h5 className={styles.municipalityTitle}>{municipality}</h5>
                                    <pre className={styles.treeDisplay}>
                                      {renderTree(roots)}
                                    </pre>
                                  </div>
                                ));
                              })()}
                            </div>
                          )}
                        </>
                      )}
                      
                      {activeTab === 'facilities' && (
                        <>
                          <div className={styles.section}>
                            <h4>Facility IDs</h4>
                            <p>{(item as Facility).facility_ids.join(', ') || 'None'}</p>
                          </div>
                          
                          {(item as Facility).facility_details.length > 0 && (
                            <div className={styles.section}>
                              <h4>Facility Instances</h4>
                              {(item as Facility).facility_details.map((detail, i) => (
                                <div key={i} className={styles.location}>
                                  <strong>{detail.municipality}</strong><br />
                                  ID: {detail.id}<br />
                                  Status: {detail.active ? 'Active' : 'Inactive'}
                                </div>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
